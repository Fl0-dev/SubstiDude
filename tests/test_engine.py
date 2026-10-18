# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import hashlib
from pathlib import Path
import tempfile
import unittest

import pymupdf

from fixtures import KEPT, TARGET, make_pdf, zero_page_pdf
from substidude.pdf_engine import MAX_FILE_BYTES, PDFError, open_pdf


class InputTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="substidude-test-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.pdf"

    def test_size_boundaries(self):
        for size, message in [(0, "vide"), (1, "valide"),
                              (MAX_FILE_BYTES - 1, "valide"), (MAX_FILE_BYTES, "10 Mo")]:
            with self.subTest(size=size):
                self.path.write_bytes(b"x" * size)
                with self.assertRaisesRegex(PDFError, message):
                    open_pdf(self.path)

    def test_page_boundaries(self):
        for count in (0, 1, 49, 50):
            with self.subTest(pages=count):
                data = make_pdf(pages=count) if count else zero_page_pdf()
                self.path.write_bytes(data)
                if count in (1, 49):
                    with open_pdf(self.path) as document:
                        self.assertEqual(count, document.page_count)
                else:
                    with self.assertRaisesRegex(PDFError, "1 à 49"):
                        open_pdf(self.path)

    def test_encrypted_pdf_is_rejected(self):
        for password in ("synthetic-user", ""):
            with self.subTest(password_required=bool(password)):
                self.path.write_bytes(make_pdf(encrypted=True, user_password=password))
                with self.assertRaisesRegex(PDFError, "chiffrés"):
                    open_pdf(self.path)

    def test_repaired_pdf_is_rejected(self):
        data = make_pdf()
        self.path.write_bytes(data[:data.index(b"\nxref\n")])
        with self.assertRaisesRegex(PDFError, "malformé"):
            open_pdf(self.path)

    def test_missing_path_is_not_disclosed(self):
        with self.assertRaises(PDFError) as caught:
            open_pdf(self.path)
        self.assertNotIn(str(self.path), str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_other_document_type_is_rejected(self):
        from fixtures import scan_image
        self.path.write_bytes(scan_image())
        with self.assertRaises(PDFError):
            open_pdf(self.path)

    def test_opened_document_is_independent_of_source(self):
        original = make_pdf()
        self.path.write_bytes(original)
        digest = hashlib.sha256(original).digest()
        with open_pdf(self.path) as document:
            document[0].insert_text((40, 250), "MODIFICATION EN MEMOIRE")
            self.assertIn("MODIFICATION", document[0].get_text())
        self.assertEqual(digest, hashlib.sha256(self.path.read_bytes()).digest())


class CorpusTests(unittest.TestCase):
    def test_content_modes(self):
        renders = {}
        for kind in ("native", "scan", "ocr", "mixed"):
            with self.subTest(kind=kind), pymupdf.open(stream=make_pdf(kind), filetype="pdf") as doc:
                self.assertFalse(doc.is_repaired)
                page = doc[0]
                self.assertEqual(0 if kind == "native" else 1, len(page.get_image_info()))
                text = page.get_text()
                for marker in (TARGET, KEPT):
                    if kind == "scan":
                        self.assertNotIn(marker, text)
                    else:
                        self.assertIn(marker, text)
                if kind == "ocr":
                    self.assertTrue(all(span["type"] == 3 for span in page.get_texttrace()))
                renders[kind] = page.get_pixmap().samples
        self.assertEqual(renders["scan"], renders["ocr"])
        self.assertNotEqual(renders["scan"], renders["native"])

    def test_rotated_and_cropped_pages(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), pymupdf.open(
                stream=make_pdf(rotation=rotation, cropped=True), filetype="pdf"
            ) as doc:
                page = doc[0]
                self.assertEqual(rotation, page.rotation)
                self.assertEqual(pymupdf.Rect(10, 20, 290, 390), page.cropbox)
                self.assertIn(TARGET, page.get_text())
                pixmap = page.get_pixmap()
                expected = (370, 280) if rotation in (90, 270) else (280, 370)
                self.assertEqual(expected, (pixmap.width, pixmap.height))


if __name__ == "__main__":
    unittest.main()
