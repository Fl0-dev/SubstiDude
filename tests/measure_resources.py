# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Sonde Windows sur corpus synthétique fixé, pas un worker ni une application.

Exécuter depuis la racine : python -B -W error tests/measure_resources.py
Chaque mesure utilise un processus neuf ; les PDF transitent par stdin en mémoire.
Les tailles/échelles ci-dessous sont des points de mesure, pas des limites produit.
"""

import argparse
import ctypes
from ctypes import wintypes
from importlib.metadata import version
from io import BytesIO
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
from time import perf_counter
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pikepdf
import pymupdf
from PIL import Image

from fixtures import FONT, KEPT, TARGET, TARGET_RECT, make_pdf, scan_image
from substidude.pdf_engine import _open_mupdf, _open_supported_structure, _pdf_objects, render_page


SAMPLES = ("native-1", "native-12", "native-49", "ocr-0.48mp", "ocr-1.92mp",
           "ocr-7.68mp", "stream-1mib", "stream-4mib", "stream-8mib")
PHASES = ("open", "streams", "render-1x", "render-2x", "pipeline")


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage",
        )
    ]


def process_memory():
    """Mémoire native et Python du processus, pas seulement les allocations tracées."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "working_set_bytes": counters.WorkingSetSize,
        "peak_working_set_bytes": counters.PeakWorkingSetSize,
        "private_bytes": counters.PrivateUsage,
        "peak_commit_bytes": counters.PeakPagefileUsage,
    }


def synthetic_sample(name):
    if name.startswith("native-"):
        return make_pdf(pages=int(name.split("-")[1])), TARGET_RECT
    if name.startswith("stream-"):
        size = int(name.split("-")[1][:-3]) * 1024 * 1024
        with pikepdf.Pdf.open(BytesIO(make_pdf())) as document:
            # Un vrai flux de commentaire décompressable ; aucune fausse dimension.
            document.pages[0].obj.Contents.append(document.make_stream(b"%" + b"X" * (size - 2) + b"\n"))
            output = BytesIO()
            document.save(output)
            return output.getvalue(), TARGET_RECT
    factor = {"ocr-0.48mp": 1, "ocr-1.92mp": 2, "ocr-7.68mp": 4}[name]
    with Image.open(BytesIO(scan_image())) as original:
        image = original.resize((600 * factor, 800 * factor), Image.Resampling.NEAREST)
    output = BytesIO()
    image.save(output, format="PNG")
    with pymupdf.open() as document:
        page = document.new_page(width=300 * factor, height=400 * factor)
        page.insert_font(fontname="noto", fontfile=str(FONT))
        page.insert_image(page.rect, stream=output.getvalue())
        for y, text in ((95, TARGET), (175, KEPT)):
            page.insert_text((40 * factor, y * factor), text, fontname="noto",
                             fontsize=16 * factor, render_mode=3)
        return document.tobytes(garbage=4, deflate=True), tuple(v * factor for v in TARGET_RECT)


def decoded_stream_sizes(source):
    """Volumes uniques décodés qpdf, y compris polices/CMap/ICC ; pas un nettoyage."""
    with pikepdf.Pdf.open(BytesIO(source), attempt_recovery=False) as document:
        groups = {"font": set(), "cmap": set(), "icc": set()}
        for obj in _pdf_objects(document.objects):
            if isinstance(obj, pikepdf.Array):
                if obj and obj[0] == pikepdf.Name.ICCBased:
                    groups["icc"].add(obj[1].objgen)
            else:
                for key, group in (("/FontFile2", "font"), ("/ToUnicode", "cmap")):
                    if key in obj:
                        groups[group].add(obj[key].objgen)
        totals = {"stream_count": 0, "decoded_total_bytes": 0, "decoded_max_bytes": 0,
                  "font_bytes": 0, "cmap_bytes": 0, "icc_bytes": 0}
        for obj in document.objects:
            if not isinstance(obj, pikepdf.Stream):
                continue
            content = obj.read_bytes()
            size = len(content)
            totals["stream_count"] += 1
            totals["decoded_total_bytes"] += size
            totals["decoded_max_bytes"] = max(totals["decoded_max_bytes"], size)
            for group, references in groups.items():
                if obj.objgen in references:
                    totals[group + "_bytes"] += size
            del content
        return totals


def probe(phase, rectangle):
    if phase == "pipeline":
        # Dépend des outils de développement ; pas une mesure du futur paquet livré.
        from test_pipeline import replace_zones

    baseline = process_memory()
    tracemalloc.start()
    source = sys.stdin.buffer.read()
    start = perf_counter()
    details = {"input_bytes": len(source)}
    if phase == "streams":
        details.update(decoded_stream_sizes(source))
    elif phase == "pipeline":
        result = replace_zones(source, [(0, rectangle, "Toto")])
        details["result_bytes"] = len(result)
    else:
        with _open_supported_structure(source), _open_mupdf(source) as document:
            details["pages"] = document.page_count
            if phase.startswith("render-"):
                scale = int(phase[-2])
                # Une seule page ; jamais toutes les pages ni de fixture structurelle géante.
                pixmap = render_page(document[0], scale)
                details["render_pixels"] = pixmap.width * pixmap.height
                details["render_sample_bytes"] = pixmap.stride * pixmap.height
    elapsed = perf_counter() - start
    _, python_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    final = process_memory()
    return {"elapsed_seconds": elapsed, "python_peak_bytes": python_peak,
            "baseline": baseline, "final": final, "details": details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--samples", nargs="+", choices=SAMPLES, default=list(SAMPLES))
    parser.add_argument("--phases", nargs="+", choices=PHASES, default=list(PHASES))
    parser.add_argument("--probe", choices=PHASES, help=argparse.SUPPRESS)
    parser.add_argument("--rectangle", nargs=4, type=float, default=TARGET_RECT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Cette sonde utilise les compteurs natifs Windows.")
    if args.probe:
        print(json.dumps(probe(args.probe, args.rectangle)))
        return
    if args.repeat < 1:
        parser.error("Le nombre de répétitions doit être positif.")
    report = {"python": platform.python_version(), "platform": platform.platform(),
              "versions": {name: version(name) for name in ("PyMuPDF", "pikepdf", "Pillow")},
              "repeat": args.repeat, "measurements": []}
    for sample in args.samples:
        source, rectangle = synthetic_sample(sample)
        for phase in args.phases:
            runs = []
            for _ in range(args.repeat):
                completed = subprocess.run(
                    [sys.executable, "-B", "-W", "error", str(Path(__file__).resolve()),
                     "--probe", phase, "--rectangle", *(str(v) for v in rectangle)],
                    input=source, capture_output=True, check=True,
                )
                runs.append(json.loads(completed.stdout))
            report["measurements"].append({
                "sample": sample, "phase": phase, "runs": runs,
                "median_seconds": statistics.median(run["elapsed_seconds"] for run in runs),
            })
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
