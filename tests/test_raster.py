# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Expériences sur scans simples ; pas une API d'export utilisateur."""

from io import BytesIO
from math import ceil, floor
import shutil
import unittest

import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

from fixtures import FONT, KEPT, TARGET, TARGET_RECT, extract_with_pdftotext, make_pdf
from substidude.pdf_engine import page_to_view_matrix


REPLACEMENT = "Société Élodie"


def replace_scan(kind, rotation=0, cropped=False):
    source = make_pdf(kind, rotation=rotation, cropped=cropped)
    with pymupdf.open(stream=source) as document:
        page = document[0]
        before_render = page.get_pixmap()
        rect = pymupdf.Rect(TARGET_RECT)
        if kind == "mixed":
            rect += (0, 200, 0, 200)
        if cropped:
            rect += (-10, -20, -10, -20)
        info = page.get_image_info()[0]
        xref = page.get_images()[0][0]
        with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
            original = image.convert("RGB")
        width, height = original.size
        # Les fixtures n'ont ni cisaillement ni masque ; ces cas restent à qualifier.
        pixels = rect * ~pymupdf.Matrix(info["transform"]) * pymupdf.Matrix(width, height)
        box = (floor(pixels.x0), floor(pixels.y0), ceil(pixels.x1), ceil(pixels.y1))
        if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
            raise AssertionError("La sélection synthétique doit rester dans l'image")
        cleaned = original.copy()
        draw = ImageDraw.Draw(cleaned)
        draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill="white")
        font = ImageFont.truetype(str(FONT), 32)
        # Marge interne : éviter que l'interpolation du rendu déborde de la zone.
        # ponytail: 2 pixels validés à 2 px/point ; qualifier les autres échelles avant réutilisation.
        position = (box[0] + 2, box[1] + 2)
        text_box = draw.textbbox(position, REPLACEMENT, font=font, anchor="lt")
        if text_box[2] > box[2] - 2 or text_box[3] > box[3] - 2:
            raise AssertionError("Le remplacement synthétique doit tenir dans la zone")
        draw.text(position, REPLACEMENT, font=font, fill="black", anchor="lt")
        encoded = BytesIO()
        cleaned.save(encoded, format="PNG")
        page.replace_image(xref, stream=encoded.getvalue())
        expected_render = page.get_pixmap()
        if kind == "ocr":
            page.add_redact_annot(rect, fill=None)
            page.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_NONE,
                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                text=pymupdf.PDF_REDACT_TEXT_REMOVE,
            )
        result = document.tobytes(garbage=4, deflate=True)
        region = rect * page_to_view_matrix(page, 1)
    return source, result, original, cleaned, box, before_render, expected_render, region


class RasterExperimentTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pdftotext"), "Inspection indépendante : pdftotext absent")
    def test_independent_text_extraction(self):
        for kind in ("scan", "ocr", "mixed"):
            with self.subTest(kind=kind):
                source, result, *_ = replace_scan(kind, rotation=90, cropped=True)
                before = extract_with_pdftotext(source)
                after = extract_with_pdftotext(result)
                self.assertNotIn(REPLACEMENT, after)
                if kind == "scan":
                    self.assertEqual("", after.strip())
                elif kind == "ocr":
                    self.assertIn(TARGET, before)
                    self.assertNotIn(TARGET, after)
                    self.assertIn(KEPT, after)
                else:
                    self.assertEqual(before, after)

    def test_pixels_ocr_and_mixed_page(self):
        for kind in ("scan", "ocr", "mixed"):
            for rotation in (0, 90, 180, 270):
                for cropped in (False, True):
                    with self.subTest(kind=kind, rotation=rotation, cropped=cropped):
                        (source, result, original, cleaned, box, before,
                         expected, region) = replace_scan(kind, rotation, cropped)
                        difference = ImageChops.difference(original, cleaned)
                        self.assertIsNotNone(difference.getbbox())
                        difference.paste((0, 0, 0), box)
                        self.assertIsNone(difference.getbbox())
                        with pymupdf.open(stream=result) as document:
                            page = document[0]
                            self.assertEqual(rotation, page.rotation)
                            text = page.get_text()
                            self.assertNotIn(REPLACEMENT, text)
                            if kind == "mixed":
                                # Le même marqueur dans la zone native n'est pas ciblé.
                                self.assertIn(TARGET, text)
                            else:
                                self.assertNotIn(TARGET, text)
                            if kind != "scan":
                                self.assertIn(KEPT, text)
                            after = page.get_pixmap()
                            self.assertEqual(expected.samples, after.samples)
                            original_render = Image.frombytes("RGB", (before.width, before.height), before.samples)
                            final_render = Image.frombytes("RGB", (after.width, after.height), after.samples)
                            difference = ImageChops.difference(original_render, final_render)
                            self.assertIsNotNone(difference.getbbox())
                            extent = region.irect
                            difference.paste((0, 0, 0), (extent.x0, extent.y0, extent.x1, extent.y1))
                            self.assertIsNone(difference.getbbox())

                            # Inspecter tous les objets image, pas seulement ceux affichés.
                            images = [xref for xref in range(1, document.xref_length())
                                      if document.xref_get_key(xref, "Subtype") == ("name", "/Image")]
                            self.assertEqual(len(images), 1)
                            for xref in images:
                                with Image.open(BytesIO(document.extract_image(xref)["image"])) as recovered:
                                    self.assertEqual(original.size, recovered.size)
                                    self.assertEqual(cleaned.tobytes(), recovered.convert("RGB").tobytes())
                            cropbox = page.cropbox
                        with pymupdf.open(stream=source) as original_doc:
                            self.assertEqual(original_doc[0].cropbox, cropbox)
                            if kind == "ocr":
                                self.assertIn(TARGET, original_doc[0].get_text())


if __name__ == "__main__":
    unittest.main()
