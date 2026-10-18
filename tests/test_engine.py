# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import hashlib
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from fixtures import FONT, KEPT, TARGET, TARGET_RECT, image_dimensions_pdf, make_pdf, zero_page_pdf
from substidude.pdf_engine import (
    MAX_FILE_BYTES, PDFError, _check_image_dimensions, open_pdf, page_to_view_matrix,
)


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

    def test_image_pixel_boundaries(self):
        _check_image_dimensions(8000, 5000)
        for width, height in ((40_000_001, 1), (8000, 5001)):
            with self.subTest(width=width, height=height):
                with self.assertRaisesRegex(PDFError, "40 mégapixels"):
                    _check_image_dimensions(width, height)
        for width, height in ((0, 10), (10, 0), (-1, 10)):
            with self.subTest(width=width, height=height):
                with self.assertRaisesRegex(PDFError, "dimensions invalides"):
                    _check_image_dimensions(width, height)

    def test_large_image_and_mask_rejected_without_extracting_pixels(self):
        for options in ({}, {"mask": True}, {"nested": True}):
            with self.subTest(options=options):
                data = image_dimensions_pdf(8000, 5001, **options)
                self.assertLess(len(data), MAX_FILE_BYTES)
                self.path.write_bytes(data)
                with patch.object(pymupdf.Page, "get_image_info", side_effect=AssertionError(
                    "Les grandes images XObject doivent être refusées avant l'inspection des pages"
                )), self.assertRaisesRegex(PDFError, "40 mégapixels"):
                    open_pdf(self.path)

    def test_inline_images_are_checked_without_hashes(self):
        # Plafond réduit pour vérifier la voie inline sans grosse allocation possible.
        self.path.write_bytes(image_dimensions_pdf(8, 8, inline=True))
        with patch("substidude.pdf_engine.MAX_IMAGE_PIXELS", 63):
            with self.assertRaisesRegex(PDFError, "40 mégapixels"):
                open_pdf(self.path)
        original = pymupdf.Page.get_image_info
        calls = []

        def inspect_images(page, **options):
            calls.append(options)
            return original(page, **options)

        with patch.object(pymupdf.Page, "get_image_info", inspect_images):
            with open_pdf(self.path) as doc:
                self.assertEqual(doc.page_count, 1)
        self.assertEqual(calls, [{"hashes": False, "xrefs": False}])


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


class CoordinateTests(unittest.TestCase):
    def test_crop_rotation_zoom_and_hidpi(self):
        # Après recadrage : point (40, 95) du MediaBox → (30, 75) du CropBox.
        # Coordonnées attendues calculées indépendamment des matrices du moteur.
        expected_points = {0: (30, 75), 90: (295, 30),
                           180: (250, 295), 270: (75, 250)}
        for rotation in expected_points:
            with pymupdf.open(stream=make_pdf(rotation=rotation, cropped=True)) as doc:
                for zoom in (0.5, 1, 2):
                    for hidpi in (1, 1.25, 1.5, 2):
                        with self.subTest(rotation=rotation, zoom=zoom, hidpi=hidpi):
                            scale = zoom * hidpi
                            matrix = page_to_view_matrix(doc[0], scale)
                            point = pymupdf.Point(30, 75) * matrix
                            expected = pymupdf.Point(expected_points[rotation]) * scale
                            self.assertLess(abs(point - expected), 0.001)
                            self.assertLess(abs(point * ~matrix - pymupdf.Point(30, 75)), 0.001)
                            rect = pymupdf.Rect(25, 50, 250, 85)
                            restored = rect * matrix * ~matrix
                            for actual, wanted in zip(restored, rect):
                                self.assertAlmostEqual(actual, wanted, places=3)

    def test_invalid_scale_is_rejected(self):
        with pymupdf.open(stream=make_pdf()) as doc:
            for scale in (0, -1, float("inf"), float("nan"), 1e-20, 1e300):
                with self.subTest(scale=scale), self.assertRaises(PDFError):
                    page_to_view_matrix(doc[0], scale)


class NativeExperimentTests(unittest.TestCase):
    """Expérience moteur sur la fixture native, pas un export utilisateur."""

    @staticmethod
    def replace_native(rotation=0, cropped=False):
        source = make_pdf(rotation=rotation, cropped=cropped)
        with pymupdf.open(stream=source) as document:
            page = document[0]
            rect = pymupdf.Rect(TARGET_RECT)
            if cropped:
                rect += (-10, -20, -10, -20)
            before = page.get_pixmap()
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_NONE,
                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                text=pymupdf.PDF_REDACT_TEXT_REMOVE,
            )
            page.insert_font(fontname="replacement", fontfile=str(FONT))
            remaining = page.insert_textbox(
                rect, "Société Élodie", fontname="replacement", fontsize=14,
            )
            if remaining < 0:
                raise AssertionError("Le remplacement de la fixture doit tenir dans la zone")
            result = document.tobytes(garbage=4, deflate=True)
            region = rect * page_to_view_matrix(page, 1)
        return source, result, before, region

    def test_native_removal_replacement_and_unchanged_pixels_outside_zone(self):
        from PIL import Image, ImageChops
        for rotation in (0, 90, 180, 270):
            for cropped in (False, True):
                with self.subTest(rotation=rotation, cropped=cropped):
                    source, result, before, region = self.replace_native(rotation, cropped)
                    with pymupdf.open(stream=result) as doc:
                        page = doc[0]
                        text = page.get_text()
                        self.assertNotIn(TARGET, text)
                        self.assertIn(KEPT, text)
                        self.assertIn("Société Élodie", text)
                        self.assertEqual(rotation, page.rotation)
                        self.assertFalse(list(page.annots() or []))
                        cropbox = page.cropbox
                        after = page.get_pixmap()
                    self.assertEqual(before.irect, after.irect)
                    original_image = Image.frombytes("RGB", (before.width, before.height), before.samples)
                    final_image = Image.frombytes("RGB", (after.width, after.height), after.samples)
                    differences = ImageChops.difference(original_image, final_image)
                    self.assertIsNotNone(differences.getbbox())
                    box = region.irect
                    differences.paste((0, 0, 0), (box.x0, box.y0, box.x1, box.y1))
                    self.assertIsNone(differences.getbbox())
                    with pymupdf.open(stream=source) as original:
                        self.assertIn(TARGET, original[0].get_text())
                        self.assertEqual(original[0].cropbox, cropbox)

    @unittest.skipUnless(shutil.which("pdftotext"), "Inspection indépendante : pdftotext absent")
    def test_independent_text_extraction(self):
        with tempfile.TemporaryDirectory(prefix="substidude-test-") as directory:
            source, result, _, _ = self.replace_native(cropped=True, rotation=90)
            extracted = []
            for name, data in (("source.pdf", source), ("result.pdf", result)):
                path = Path(directory) / name
                path.write_bytes(data)
                command = [shutil.which("pdftotext"), "-enc", "UTF-8", str(path), "-"]
                completed = subprocess.run(command, capture_output=True, check=True, timeout=15)
                extracted.append(completed.stdout.decode("utf-8"))
            self.assertIn(TARGET, extracted[0])
            self.assertNotIn(TARGET, extracted[1])
            self.assertIn(KEPT, extracted[1])
            self.assertIn("Société Élodie", extracted[1])


if __name__ == "__main__":
    unittest.main()
