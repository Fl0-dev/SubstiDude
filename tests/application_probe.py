# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Recette du worker dans un parent propre, depuis des fichiers synthétiques de test.

Ne génère aucun PDF et n'importe aucun outil de développement ni moteur dans le
parent. Aucun export utilisateur ; les entrées sont fournies par test_worker.py.
"""

import argparse
import json
import multiprocessing
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from substidude.model import Session, Substitution
from substidude.worker import PDFJob, SessionController


def check(directory):
    checks = []
    for kind in ("native", "scan", "ocr", "mixed"):
        with PDFJob() as job:
            job.start("open", path=str(directory / (kind + ".pdf")))
            source = job.receive()
        session = Session(source)
        rect = (35, 270, 260, 305) if kind == "mixed" else (35, 70, 260, 105)
        session.set_substitutions([Substitution(0, rect, "Société Élodie")])
        controller = SessionController(session)
        try:
            controller.generate()
            if not controller.collect():
                raise AssertionError("Résultat courant non accepté.")
            session.confirm()
            result = session.confirmed_bytes()
        finally:
            controller.close()
        if result is not session.confirmed_bytes():
            raise AssertionError("La fermeture inactive a invalidé le résultat.")
        with PDFJob() as job:
            job.start("inspect", result)
            info = json.loads(job.receive())
            if len(info["pages"]) != 1 or not info["warnings"]:
                raise AssertionError("Inspection incomplète.")
            job.start("render", result)
            rendered = job.receive()
            width, height = struct.unpack_from(">II", rendered)
            if len(rendered) != 8 + width * height * 3:
                raise AssertionError("Rendu incomplet.")
            destination = directory / (kind + "-export.pdf")
            job.start("export", result, path=str(destination), source_path=str(directory / (kind + ".pdf")))
            if job.receive() != b"exported" or destination.read_bytes() != result:
                raise AssertionError("Export synthétique non identique.")
            if (directory / (kind + ".pdf")).read_bytes() != source:
                raise AssertionError("Source synthétique modifié.")
        checks.append(kind + "-open-transform-verify-confirm-inspect-render-export")
    if any(name in sys.modules for name in ("pymupdf", "pikepdf", "PIL", "pypdfium2")):
        raise AssertionError("Un moteur ou outil de test a été importé dans le parent.")
    return {"checks": checks, "parent_without_pdf_engines": True, "synthetic_exports": True}


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    print(json.dumps(check(parser.parse_args().directory)))
