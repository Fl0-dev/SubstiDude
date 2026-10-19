# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Diagnostic local borné, sans texte, valeurs documentaires, chemin ou flux affichés.

Lecture seule d'un fichier explicitement choisi. Par défaut, diagnostic seulement.
--check-preview permet un remplacement de test en mémoire sans écriture/export.
La synthèse structurelle ne lève aucun refus du moteur.
"""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import multiprocessing
from pathlib import Path
import sys
import re
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def inspect(sender, path, check_preview=False):
    try:
        from substidude.windows_memory import WindowsMemoryBudget
        with WindowsMemoryBudget(2 * 1024**3):
            from substidude import pdf_engine as engine
            import pikepdf

            def read():
                with open(path, "rb") as stream:
                    engine._check_file_size(stream.seek(0, 2))
                    stream.seek(0)
                    return stream.read(engine.MAX_FILE_BYTES)

            source = read()
            report = {"accepted": False, "bytes": len(source)}
            try:
                with engine._open_mupdf(source):
                    report["mupdf_without_repair"] = True
            except engine.PDFError:
                report["mupdf_without_repair"] = False
            try:
                with engine._open_supported_structure(source) as structure, engine._open_mupdf(source) as document:
                    report["accepted"] = True
                    from substidude.native import check_document, image_inventory
                    image_inventory(structure)
                    check_document(structure, document)
                    report["native_structure_qualified"] = True
                    if check_preview:
                        import pymupdf
                        from substidude.model import Substitution
                        from substidude.pipeline import transform
                        # Une zone de test entièrement déterminée localement ;
                        # aucun texte, rectangle ou PDF résultat n'est transmis.
                        candidates = []
                        for block in document[0].get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]:
                            if block["type"] == 0:
                                for line in block["lines"]:
                                    for span in line["spans"]:
                                        if span["text"].strip():
                                            candidates.append(pymupdf.Rect(span["bbox"]) + (-1, -1, 1, 1))
                        report["preview_checked"] = False
                        for rectangle in sorted(candidates, key=lambda rect: (rect.y0, rect.x0))[:10]:
                            try:
                                if engine.classify_zone(source, 0, rectangle) != "native":
                                    continue
                            except engine.PDFError:
                                continue
                            result = transform(source, [Substitution(0, tuple(rectangle), "TEST")])
                            with engine._open_mupdf(result) as preview:
                                engine.render_page(preview[0], 1)
                            report["preview_checked"] = True
                            break
            except engine.PDFError as error:
                trace = error.__traceback__
                report["guard_chain"] = []
                while trace is not None:
                    if trace.tb_frame.f_globals.get("__name__") in {"substidude.pdf_engine", "substidude.native", "substidude.pipeline"}:
                        report["guard"] = trace.tb_frame.f_code.co_name
                        report["guard_line"] = trace.tb_lineno
                        report["guard_chain"].append([trace.tb_frame.f_code.co_name, trace.tb_lineno])
                    trace = trace.tb_next
                # Ne pas sérialiser l'exception, ses variables ou son traceback.

            # Inspection descriptive distincte : aucun appel de nettoyage ou de
            # transformation, aucun contrôle de refus désactivé ou monkeypatché.
            with pikepdf.Pdf.open(BytesIO(source), attempt_recovery=False) as document:
                vocabulary = {"stream", "length", "object", "page", "content", "operator", "token", "incorrect", "damaged",
                              "invalid", "recover", "missing", "unknown", "endstream", "operand", "parse", "parsing", "error",
                              "errors", "dictionary", "unexpected", "eof", "insufficient", "expected", "ignoring", "empty",
                              "warning", "recovery", "null", "name", "array", "string", "unterminated", "offset", "xref",
                              "cross", "reference", "entry", "type", "trailer", "size", "not", "must", "be", "item", "entries",
                              "buffer", "range", "compressed", "uncompressed", "converting", "read", "may", "cause", "found",
                              "after", "before", "required", "invalid", "wrong", "data", "an", "or", "is", "the"}
                report["warning_classes"] = []
                def collect_warnings(stage):
                    for warning in document.get_warnings():
                        report["warning_classes"].append({"stage": stage,
                            "keywords": [word for word in re.findall(r"[a-z]+", warning.lower()) if word in vocabulary],
                            "standard_fields": [field for field in re.findall(r"/[A-Za-z]+", warning)
                                                if field in {"/Type", "/XRef", "/W", "/Index", "/Size", "/Root", "/Length", "/Filter", "/Prev"}]})
                collect_warnings("open")
                engine._check_stream_budgets(document)
                collect_warnings("stream-budgets")
                report["pages"] = len(document.pages)
                page_fields = {"/Type", "/Parent", "/Contents", "/Resources", "/MediaBox", "/CropBox", "/Rotate",
                               "/Metadata", "/Thumb", "/Annots", "/BleedBox", "/TrimBox", "/ArtBox", "/Group",
                               "/UserUnit", "/Tabs", "/StructParents"}
                report["page_fields"] = [{"known": sorted(set(page.obj.keys()) & page_fields),
                                          "unknown_count": len(set(page.obj.keys()) - page_fields)} for page in document.pages]
                report["page_groups"] = []
                for page in document.pages:
                    group = page.obj.get("/Group")
                    if isinstance(group, pikepdf.Dictionary):
                        report["page_groups"].append({"fields": sorted(set(group.keys()) & {"/Type", "/S", "/CS", "/I", "/K"}),
                            "unknown": len(set(group.keys()) - {"/Type", "/S", "/CS", "/I", "/K"}),
                            "isolated": group.get("/I") is True, "knockout": group.get("/K") is True,
                            "device_rgb": group.get("/CS") == pikepdf.Name.DeviceRGB})
                known_flags = ("/AcroForm", "/MarkInfo", "/StructTreeRoot", "/OutputIntents",
                               "/Perms", "/Names", "/PageLabels", "/Outlines", "/OCProperties")
                report["catalogue_flags"] = [key for key in known_flags if key in document.Root]
                fonts, images, forms = {}, 0, 0
                report["font_structures"] = []
                report["form_structures"] = []
                report["image_structures"] = []
                font_kinds = {"/Type0", "/Type1", "/TrueType", "/Type3", "/CIDFontType0", "/CIDFontType2"}
                font_fields = {"/Type", "/Subtype", "/BaseFont", "/Name", "/FirstChar", "/LastChar", "/Widths",
                               "/FontDescriptor", "/Encoding", "/ToUnicode", "/DescendantFonts", "/W", "/DW",
                               "/CIDToGIDMap", "/CIDSystemInfo"}
                for obj in document.objects:
                    if not isinstance(obj, (pikepdf.Dictionary, pikepdf.Stream)):
                        continue
                    if obj.get("/Type") == pikepdf.Name.Font:
                        kind = str(obj.get("/Subtype"))
                        kind = kind if kind in font_kinds else "other"
                        fonts[kind] = fonts.get(kind, 0) + 1
                        report["font_structures"].append({"kind": kind, "known_keys": sorted(set(obj.keys()) & font_fields),
                                                         "unknown_key_count": len(set(obj.keys()) - font_fields),
                                                         "encoding_type": ("name" if isinstance(obj.get("/Encoding"), pikepdf.Name)
                                                                           else "dictionary" if isinstance(obj.get("/Encoding"), pikepdf.Dictionary)
                                                                           else "absent-or-other"),
                                                         "cid_map_type": ("identity" if obj.get("/CIDToGIDMap") == pikepdf.Name.Identity
                                                                          else "stream" if isinstance(obj.get("/CIDToGIDMap"), pikepdf.Stream)
                                                                          else "absent-or-other")})
                        if kind == "/TrueType":
                            widths = obj.get("/Widths")
                            report["font_structures"][-1]["width_count"] = len(widths) if isinstance(widths, pikepdf.Array) else None
                            report["font_structures"][-1]["first_char"] = obj.get("/FirstChar")
                            report["font_structures"][-1]["last_char"] = obj.get("/LastChar")
                            report["font_structures"][-1]["nested_widths"] = sum(isinstance(v, pikepdf.Array) for v in widths) if isinstance(widths, pikepdf.Array) else None
                        descriptor = obj.get("/FontDescriptor")
                        if isinstance(descriptor, pikepdf.Dictionary):
                            descriptor_fields = {"/Type", "/FontName", "/Flags", "/FontBBox", "/ItalicAngle", "/Ascent",
                                                 "/Descent", "/CapHeight", "/XHeight", "/StemV", "/StemH", "/MissingWidth",
                                                 "/AvgWidth", "/MaxWidth", "/Leading", "/FontFamily", "/FontWeight", "/FontStretch",
                                                 "/CIDSet", "/CharSet", "/FontFile", "/FontFile2", "/FontFile3"}
                            report["font_structures"][-1]["descriptor_keys"] = sorted(set(descriptor.keys()) & descriptor_fields)
                            report["font_structures"][-1]["descriptor_unknown_keys"] = len(set(descriptor.keys()) - descriptor_fields)
                    images += obj.get("/Subtype") == pikepdf.Name.Image
                    forms += obj.get("/Subtype") == pikepdf.Name.Form
                    if obj.get("/Subtype") == pikepdf.Name.Image:
                        space = obj.get("/ColorSpace")
                        spaces = {"/DeviceRGB", "/DeviceGray", "/DeviceCMYK", "/Indexed", "/ICCBased"}
                        name = str(space[0] if isinstance(space, pikepdf.Array) and space else space)
                        filters = {"/FlateDecode", "/DCTDecode", "/ASCIIHexDecode", "/JPXDecode", "/CCITTFaxDecode"}
                        encoding = str(obj.get("/Filter"))
                        report["image_structures"].append({"space": name if name in spaces else "other",
                            "filter": encoding if encoding in filters else "other-or-none", "mask": "/SMask" in obj or "/Mask" in obj,
                            "decode_parameters": bool(obj.get("/DecodeParms"))})
                    if obj.get("/Subtype") == pikepdf.Name.Form:
                        fields = {"/Type", "/Subtype", "/BBox", "/Matrix", "/Resources", "/FormType", "/Group",
                                  "/Length", "/Filter", "/DecodeParms", "/Metadata"}
                        report["form_structures"].append({"known_keys": sorted(set(obj.keys()) & fields),
                            "unknown_keys": len(set(obj.keys()) - fields)})
                        for key in ("/BBox", "/Matrix"):
                            value = obj.get(key)
                            if isinstance(value, pikepdf.Array) and len(value) in (4, 6):
                                report["form_structures"][-1][key[1:].lower()] = [float(v) for v in value]
                        group = obj.get("/Group")
                        if isinstance(group, pikepdf.Dictionary):
                            report["form_structures"][-1]["group_fields"] = sorted(set(group.keys()) & {"/Type", "/S", "/CS", "/I", "/K"})
                            report["form_structures"][-1]["group_unknown_fields"] = len(set(group.keys()) - {"/Type", "/S", "/CS", "/I", "/K"})
                        resources = obj.get("/Resources", {})
                        report["form_structures"][-1]["resource_fields"] = sorted(set(resources.keys()) & {"/Font", "/XObject", "/ProcSet", "/ExtGState", "/ColorSpace", "/Pattern", "/Shading", "/Properties"})
                report.update(font_subtypes=fonts, image_objects=images, form_objects=forms)
                operators = {"q", "Q", "cm", "BT", "ET", "Tf", "Tm", "Td", "TD", "T*", "Tj", "TJ",
                             "Tr", "Tc", "Tw", "Tz", "TL", "Ts", "Do", "w", "M", "d", "J", "j", "gs",
                             "m", "l", "c", "v", "y", "h", "re", "S", "s", "f", "f*", "B", "B*", "n",
                             "W", "W*", "rg", "RG", "g", "G", "k", "K", "cs", "CS", "sc", "SC",
                             "scn", "SCN", "BMC", "BDC", "EMC", "MP", "DP", "INLINE IMAGE"}
                report["page_operators"] = []
                for page in document.pages:
                    used = {str(item.operator) for item in pikepdf.parse_content_stream(page)}
                    report["page_operators"].append({"known": sorted(used & operators),
                                                     "unknown_count": len(used - operators)})
                report["form_operators"] = []
                for obj in document.objects:
                    if isinstance(obj, pikepdf.Stream) and obj.get("/Subtype") == pikepdf.Name.Form:
                        used = {str(item.operator) for item in pikepdf.parse_content_stream(obj)}
                        report["form_operators"].append({"known": sorted(used & operators), "unknown_count": len(used - operators)})
                collect_warnings("content-inspection")
            report["source_unchanged"] = sha256(source).digest() == sha256(read()).digest()
            sender.send_bytes(json.dumps(report).encode("ascii"))
    except Exception:
        sender.send_bytes(b'{"diagnostic":"unavailable"}')
    finally:
        sender.close()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True)
    parser.add_argument("--check-preview", action="store_true")
    arguments = parser.parse_args()
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=inspect, args=(sender, arguments.path, arguments.check_preview))
    started = monotonic()
    try:
        process.start()
        sender.close()
        if not receiver.poll(max(0, 60 - (monotonic() - started))):
            raise TimeoutError()
        payload = receiver.recv_bytes(maxlength=16_384)
        process.join(max(0, 60 - (monotonic() - started)))
        if process.is_alive() or process.exitcode != 0 or monotonic() - started >= 60:
            raise TimeoutError()
        print(payload.decode("ascii"))
    except Exception:
        print('{"diagnostic":"interrupted"}')
        sys.exit(1)
    finally:
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join()
        receiver.close()
        sender.close()
        process.close()
