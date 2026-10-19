# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Corpus historique du moteur applicatif, sans export utilisateur."""

from hashlib import sha256
from io import BytesIO
import unittest
from unittest.mock import patch

import pikepdf
import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

from fixtures import (
    FONT, KEPT, TARGET, TARGET_RECT, auxiliary_pdf, make_pdf, repeated_images_pdf,
    shared_text_pdf, zone_case_pdf,
)
from substidude.pdf_engine import (
    PDFError, page_to_view_matrix, sanitize_pdf,
)
from test_independent import render_and_extract, text_runs
import test_independent
from substidude import pipeline
from substidude.model import Substitution
from substidude.pipeline import image_key, outside_characters


REPLACEMENTS = ("Société Élodie", "Toto")
SECOND_RECT = (35, 150, 260, 185)


def replace_zones(source, zones):
    """Adaptateur du corpus historique ; tout le traitement est dans le moteur."""
    return pipeline.transform(source, [Substitution(n, tuple(rect), text) for n, rect, text in zones])


class PipelineTests(unittest.TestCase):
    def assert_local_render(self, source, result, zones, page_number=0):
        before, _, size, rotation = render_and_extract(source, page_number)
        after, text, final_size, final_rotation = render_and_extract(result, page_number)
        self.assertEqual((size, rotation), (final_size, final_rotation))
        difference = ImageChops.difference(before, after)
        self.assertIsNotNone(difference.getbbox())
        with pymupdf.open(stream=source) as original:
            matrix = page_to_view_matrix(original[page_number], 2)
            for number, rect, _ in zones:
                if number == page_number:
                    box = (pymupdf.Rect(rect) * matrix).irect
                    difference.paste((0, 0, 0), (box.x0, box.y0, box.x1, box.y1))
        self.assertIsNone(difference.getbbox())
        return text

    def test_two_zones_on_native_scan_and_ocr(self):
        for kind in ("native", "scan", "ocr"):
            for rotation in (0, 90, 180, 270):
                for cropped in (False, True):
                    with self.subTest(kind=kind, rotation=rotation, cropped=cropped):
                        source = make_pdf(kind, rotation=rotation, cropped=cropped)
                        digest = sha256(source).digest()
                        rects = [pymupdf.Rect(TARGET_RECT), pymupdf.Rect(SECOND_RECT)]
                        if cropped:
                            rects = [rect + (-10, -20, -10, -20) for rect in rects]
                        zones = [(0, rect, text) for rect, text in zip(rects, REPLACEMENTS)]
                        result = replace_zones(source, zones)
                        text = self.assert_local_render(source, result, zones)
                        self.assertNotIn(TARGET, text)
                        self.assertNotIn(KEPT, text)
                        for replacement in REPLACEMENTS:
                            self.assertEqual(kind == "native", replacement in text)
                        self.assertEqual(digest, sha256(source).digest())
                        if kind != "native":
                            expected = self.source_image(source)
                            draw = ImageDraw.Draw(expected)
                            font = ImageFont.truetype(str(FONT), 28)
                            # Calcul indépendant sur la grille connue de la fixture, sans matrice.
                            for box, replacement in zip(((70, 140, 520, 210), (70, 300, 520, 370)), REPLACEMENTS):
                                x0, y0, x1, y1 = box
                                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill="white")
                                draw.text((x0 + 2, y0 + 2), replacement, font=font, fill="black", anchor="lt")
                            test_independent.IndependentTests().assert_cleaned_images(result, expected)
                        else:
                            with pikepdf.Pdf.open(BytesIO(source)) as original, pikepdf.Pdf.open(BytesIO(result)) as final:
                                encoded = b"".join(text_runs(final.pages[0]))
                                for old_run in text_runs(original.pages[0]):
                                    self.assertNotIn(old_run, encoded)

    def source_image(self, source):
        with pikepdf.Pdf.open(BytesIO(source)) as checked:
            obj, = checked.pages[0].get_images().values()
            with pikepdf.PdfImage(obj).as_pil_image() as image:
                return image.convert("RGB")

    def test_mixed_native_and_raster_zones(self):
        source = make_pdf("mixed")
        zones = [(0, TARGET_RECT, REPLACEMENTS[0]),
                 (0, pymupdf.Rect(TARGET_RECT) + (0, 200, 0, 200), REPLACEMENTS[1])]
        result = replace_zones(source, zones)
        text = self.assert_local_render(source, result, zones)
        self.assertNotIn(TARGET, text)
        self.assertIn(KEPT, text)
        self.assertIn(REPLACEMENTS[0], text)
        self.assertNotIn(REPLACEMENTS[1], text)

    def test_native_and_scan_on_different_pages(self):
        with pymupdf.open(stream=make_pdf()) as document:
            with pymupdf.open(stream=make_pdf("scan", rotation=90, cropped=True)) as scan:
                document.insert_pdf(scan)
            source = document.tobytes()
        zones = [(0, TARGET_RECT, REPLACEMENTS[0]),
                 (1, pymupdf.Rect(TARGET_RECT) + (-10, -20, -10, -20), REPLACEMENTS[1])]
        result = replace_zones(source, zones)
        self.assertIn(REPLACEMENTS[0], self.assert_local_render(source, result, zones, 0))
        self.assertNotIn(REPLACEMENTS[1], self.assert_local_render(source, result, zones, 1))

    def test_disjoint_zones_in_one_text_object_are_refused(self):
        source, rectangles = shared_text_pdf()
        with pikepdf.Pdf.open(BytesIO(source)) as checked:
            self.assertEqual(1, len(text_runs(checked.pages[0])))
        zones = [(0, rect, text) for rect, text in zip(rectangles, ("Toto", "John Doe"))]
        digest = sha256(source).digest()
        with patch.object(pymupdf.Page, "apply_redactions") as redact:
            with self.assertRaisesRegex(PDFError, "même groupe de texte"):
                replace_zones(source, zones)
            redact.assert_not_called()
        self.assertEqual(digest, sha256(source).digest())

    def test_local_replacement_and_untouched_ocr(self):
        for kind in ("native", "scan", "ocr"):
            for replacement in ("", REPLACEMENTS[0]):
                with self.subTest(kind=kind, empty=not replacement):
                    source = make_pdf(kind)
                    zones = [(0, TARGET_RECT, replacement)]
                    result = replace_zones(source, zones)
                    text = self.assert_local_render(source, result, zones)
                    self.assertNotIn(TARGET, text)
                    self.assertEqual(kind != "scan", KEPT in text)
                    if replacement:
                        self.assertEqual(kind == "native", replacement in text)

    def test_shared_text_regression_reproduces_a_lost_neighbouring_space(self):
        source, rectangles = shared_text_pdf()
        with pymupdf.open(stream=source) as document:
            page = document[0]
            before = outside_characters(page, rectangles)
            for rect in rectangles:
                page.add_redact_annot(rect, fill=None)
            page.apply_redactions(images=0, graphics=0, text=0)
            after = outside_characters(page, rectangles)
        self.assertTrue(before - after)
        self.assertEqual({32}, {key[-2] for key in before - after})
        self.assertFalse(after - before)

    def test_unshown_images_and_fractional_pixels_are_refused(self):
        with pymupdf.open(stream=make_pdf("scan")) as document:
            copied = document.get_new_xref()
            document.update_object(copied, "<< >>")
            document.xref_copy(document[0].get_images()[0][0], copied)
            source = document.tobytes(garbage=0)
        with self.assertRaisesRegex(PDFError, "image non affichée|Plusieurs images"):
            replace_zones(source, [(0, TARGET_RECT, "Toto")])
        with self.assertRaisesRegex(PDFError, "suivre les pixels"):
            replace_zones(make_pdf("scan"), [(0, (35.1, 70, 260, 105), "Toto")])

    def test_corrupted_final_bytes_block_the_result(self):
        cleanup = sanitize_pdf

        def corrupt(data):
            with pymupdf.open(stream=cleanup(data)) as document:
                xref = document.get_new_xref()
                document.update_object(xref, "<< >>")
                document.xref_copy(document[0].get_images()[0][0], xref)
                return document.tobytes(garbage=0)

        with patch("substidude.pipeline.sanitize_pdf", corrupt):
            with self.assertRaisesRegex(PDFError, "images récupérables"):
                replace_zones(make_pdf("scan"), [(0, TARGET_RECT, "Toto")])
        with patch("substidude.pipeline.sanitize_pdf", lambda data: data):
            with self.assertRaisesRegex(PDFError, "nettoyage"):
                replace_zones(auxiliary_pdf("metadata"), [(0, TARGET_RECT, "Toto")])

    def test_refusals_before_mutation(self):
        cases = [
            (make_pdf(), [(0, TARGET_RECT, "Toto"), (0, TARGET_RECT, "Autre")], "chevauch"),
            (make_pdf(), [(0, TARGET_RECT, "X\n" * 100)], "tient"),
            (make_pdf("scan"), [(0, TARGET_RECT, "X" * 1000)], "tient"),
            (make_pdf(), [(0, TARGET_RECT, "ligne\tsuivante")], "caractères"),
            (make_pdf(), [(0, TARGET_RECT, "\U0010ffff")], "caractères"),
            (make_pdf("mixed"), [(0, TARGET_RECT, "Toto"), (0, (35, 70, 260, 305), "")], "refus|image|chevauch"),
            (repeated_images_pdf(), [(0, TARGET_RECT, ""), (1, TARGET_RECT, "")], "réutilisée"),
            (zone_case_pdf("vector"), [(0, TARGET_RECT, "")], "opérateur"),
            (zone_case_pdf("vector"), [(0, (35, 70, 100, 105), ""), (0, (150, 70, 260, 105), "")], "opérateur"),
            (zone_case_pdf("visible-overlay"), [(0, TARGET_RECT, "")], "superposition"),
            (auxiliary_pdf("actualtext"), [(0, TARGET_RECT, "")], "balisés|alternatifs"),
        ]
        for source, zones, message in cases:
            with self.subTest(message=message), patch.object(pymupdf.Page, "apply_redactions") as redact:
                with self.assertRaisesRegex(PDFError, message):
                    replace_zones(source, zones)
                redact.assert_not_called()

    def test_shared_or_partial_character_is_refused(self):
        source = make_pdf()
        with pymupdf.open(stream=source) as document:
            char = document[0].get_texttrace()[0]["chars"][0][3]
        midpoint = (char[0] + char[2]) / 2
        zones = [(0, (char[0], 70, midpoint - 0.01, 105), ""),
                 (0, (midpoint + 0.01, 70, char[2], 105), "")]
        with self.assertRaisesRegex(PDFError, "même caractère"):
            replace_zones(source, zones)
        with self.assertRaisesRegex(PDFError, "traverse"):
            replace_zones(source, zones[:1])

    def test_failed_removal_is_not_reported_as_success(self):
        def discard_redactions(page, **options):
            for annotation in list(page.annots() or []):
                page.delete_annot(annotation)
            return True

        for kind in ("native", "ocr"):
            with self.subTest(kind=kind), patch.object(pymupdf.Page, "apply_redactions", discard_redactions):
                with self.assertRaisesRegex(PDFError, "texte"):
                    replace_zones(make_pdf(kind), [(0, TARGET_RECT, "Toto")])
        with patch.object(pymupdf.Page, "replace_image"):
            with self.assertRaisesRegex(PDFError, "images récupérables"):
                replace_zones(make_pdf("scan"), [(0, TARGET_RECT, "Toto")])

    def test_cleanup_failure_does_not_disclose_document_content(self):
        with patch("substidude.pipeline.sanitize_pdf", side_effect=RuntimeError(TARGET)):
            with self.assertRaises(PDFError) as caught:
                replace_zones(make_pdf(), [(0, TARGET_RECT, "Toto")])
        self.assertNotIn(TARGET, str(caught.exception))

    def test_invisible_native_replacement_is_refused(self):
        insert = pymupdf.Page.insert_textbox

        def insert_invisible(page, *args, **options):
            return insert(page, *args, **options, render_mode=3)

        with patch.object(pymupdf.Page, "insert_textbox", insert_invisible):
            with self.assertRaisesRegex(PDFError, "natif.*visible"):
                replace_zones(make_pdf(), [(0, TARGET_RECT, "Toto")])


if __name__ == "__main__":
    unittest.main()
