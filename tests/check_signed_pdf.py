# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Recette explicite 11G avec OpenSSL local ; hors découverte unittest et hors produit.

Certificat auto-signé éphémère : preuve d'intégrité CMS, pas de confiance PKI,
de révocation, d'horodatage ou de conformité PAdES générale.
"""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

import pikepdf
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import TARGET_RECT, make_pdf
from substidude.pdf_engine import PDFError, classify_zone, open_pdf, sanitize_pdf
import test_pipeline


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(openssl, directory, *arguments, success=True):
    result = subprocess.run([openssl, *arguments], cwd=directory, capture_output=True, timeout=30)
    require((result.returncode == 0) == success, "Résultat OpenSSL inattendu.")
    return result.stdout.decode("ascii", errors="replace").strip()


def check(openssl, directory):
    version = run(openssl, directory, "version")
    # Réservation à taille fixe : aucune réécriture du PDF après signature.
    placeholder = [1111111111, 2222222222, 3333333333, 4444444444]
    with pikepdf.Pdf.open(BytesIO(make_pdf())) as document:
        signature = document.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name.Sig, Filter=pikepdf.Name.Adobe_PPKLite,
            SubFilter=pikepdf.Name("/adbe.pkcs7.detached"),
            ByteRange=placeholder, Contents=pikepdf.String(b"\x00" * 8192),
        ))
        field = document.make_indirect(pikepdf.Dictionary(
            FT=pikepdf.Name.Sig, T="synthetic-signature", V=signature,
            Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Widget,
            Rect=[0, 0, 0, 0], P=document.pages[0].obj,
        ))
        document.Root.AcroForm = pikepdf.Dictionary(Fields=[field], SigFlags=3)
        document.pages[0].obj.Annots = [field]
        output = BytesIO()
        document.save(output, object_stream_mode=pikepdf.ObjectStreamMode.disable)
    source = output.getvalue()
    contents = re.search(rb"/Contents\s*(<0{16384}>)", source)
    require(contents is not None, "Réservation de signature absente.")
    start, end = contents.span(1)
    ranges = [0, start, end, len(source) - end]
    old = ("[ " + " ".join(map(str, placeholder)) + " ]").encode()
    new = ("[ " + " ".join(map(str, ranges)) + " ]").encode()
    require(source.count(old) == 1 and len(new) <= len(old), "ByteRange ambigu.")
    source = source.replace(old, new.ljust(len(old)), 1)
    payload = source[:start] + source[end:]
    (directory / "payload.bin").write_bytes(payload)
    run(openssl, directory, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", "key.pem", "-out", "cert.pem", "-subj", "/CN=SubstiDude Synthetic",
        "-days", "1", "-sha256")
    run(openssl, directory, "cms", "-sign", "-binary", "-in", "payload.bin",
        "-signer", "cert.pem", "-inkey", "key.pem", "-outform", "DER",
        "-out", "signature.der", "-md", "sha256", "-nosmimecap")
    cms = (directory / "signature.der").read_bytes()
    require(len(cms) <= 8192, "Signature trop longue.")
    source = source[:start + 1] + cms.hex().encode().ljust(16384, b"0") + source[end - 1:]
    with pikepdf.Pdf.open(BytesIO(source), attempt_recovery=False) as document:
        require(not document.check_pdf_syntax(), "PDF signé invalide.")
        value = document.Root.AcroForm.Fields[0].V
        require(list(value.ByteRange) == ranges, "ByteRange modifié.")
        require(bytes(value.Contents) == cms.ljust(8192, b"\x00"), "CMS incorporé différent.")
    # Vérifier les octets extraits du PDF final, puis un témoin altéré.
    payload = source[:ranges[1]] + source[ranges[2]:]
    (directory / "payload.bin").write_bytes(payload)
    verify = ("cms", "-verify", "-binary", "-inform", "DER", "-in", "signature.der",
              "-content", "payload.bin", "-noverify", "-out", "verified.bin")
    run(openssl, directory, *verify)
    require((directory / "verified.bin").read_bytes() == payload, "Contenu vérifié différent.")
    (directory / "payload.bin").write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    run(openssl, directory, *verify, success=False)
    path = directory / "synthetic-signed.pdf"
    path.write_bytes(source)
    digest = sha256(source).digest()
    checks = []
    operations = {
        "open": lambda: open_pdf(path),
        "sanitize": lambda: sanitize_pdf(source),
        "classify": lambda: classify_zone(source, 0, TARGET_RECT),
        "pipeline": lambda: test_pipeline.replace_zones(source, [(0, TARGET_RECT, "Toto")]),
    }
    before = set(directory.iterdir())
    for name, operation in operations.items():
        with patch.object(pymupdf.Page, "apply_redactions") as redact:
            try:
                operation()
            except PDFError as error:
                require("signatures" in str(error) or "annotations" in str(error), "Refus inattendu.")
            else:
                raise AssertionError("Document signé accepté.")
            redact.assert_not_called()
        require(sha256(path.read_bytes()).digest() == digest, "Source modifié.")
        require(set(directory.iterdir()) == before, "Sortie inattendue.")
        checks.append(name + "-refused")
    # Le même garde doit aussi interdire une contamination des octets finaux.
    with patch("substidude.pipeline.sanitize_pdf", return_value=source):
        try:
            test_pipeline.replace_zones(make_pdf(), [(0, TARGET_RECT, "Toto")])
        except PDFError as error:
            require("signatures" in str(error) or "annotations" in str(error), "Refus final inattendu.")
        else:
            raise AssertionError("Résultat signé accepté.")
    return {"openssl": version, "cms_integrity": True, "tampered_content_rejected": True,
            "certificate_trust_checked": False, "checks": checks + ["final-result-refused"],
            "source_unchanged": True, "application": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openssl", required=True, help="Exécutable OpenSSL local déjà installé")
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="substidude-signed-") as temporary:
        report = check(str(Path(arguments.openssl).resolve()), Path(temporary))
    report["temporary_files_removed"] = not Path(temporary).exists()
    require(report["temporary_files_removed"], "Temporaires non supprimés.")
    print(json.dumps(report))
