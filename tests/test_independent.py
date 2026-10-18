# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Qualification indépendante des sorties synthétiques, pas audit PDF général."""

from io import BytesIO
from contextlib import closing
import unittest

import pikepdf
import pypdfium2 as pdfium
import pymupdf
from PIL import ImageChops

from fixtures import KEPT, TARGET
import test_engine
import test_raster


def render_and_extract(data, page_number=0):
    with closing(pdfium.PdfDocument(data)) as document:
        with closing(document[page_number]) as page:
            with closing(page.get_textpage()) as text_page:
                text = text_page.get_text_bounded()
            # Comparer avant/après dans PDFium, pas les pixels de deux moteurs différents.
            with closing(page.render(scale=2, may_draw_forms=False, draw_annots=False)) as bitmap:
                image = bitmap.to_pil().convert("RGB").copy()
            return image, text, page.get_size(), page.get_rotation()


def text_runs(page):
    # Les fixtures utilisent TJ ; pikepdf décode les chaînes PDF et leurs échappements.
    return [bytes(item)
            for instruction in pikepdf.parse_content_stream(page)
            if str(instruction.operator) == "TJ"
            for item in instruction.operands[0]
            if isinstance(item, pikepdf.String)]


class IndependentTests(unittest.TestCase):
    def assert_render_local(self, source, result, region):
        before, source_text, original_size, original_rotation = render_and_extract(source)
        after, text, final_size, final_rotation = render_and_extract(result)
        self.assertEqual(original_size, final_size)
        self.assertEqual(original_rotation, final_rotation)
        self.assertEqual(before.size, after.size)
        difference = ImageChops.difference(before, after)
        self.assertIsNotNone(difference.getbbox())
        extent = (region * 2).irect
        difference.paste((0, 0, 0), (extent.x0, extent.y0, extent.x1, extent.y1))
        self.assertIsNone(difference.getbbox())
        return source_text, text

    def assert_rewritten_structure(self, document):
        self.assertEqual([], document.check_pdf_syntax())
        self.assertNotIn("/Prev", document.trailer)
        self.assertNotIn("/XRefStm", document.trailer)
        self.assertFalse(document.is_encrypted)
        self.assertEqual(1, len(document.pages))
        # Ces sorties simples ne doivent pas introduire d'annotations ni de structures auxiliaires.
        self.assertFalse(document.pages[0].obj.get("/Annots", []))
        for key in ("/AcroForm", "/Metadata", "/Names", "/OpenAction", "/AA",
                    "/OCProperties", "/StructTreeRoot"):
            self.assertNotIn(key, document.Root)

    def assert_cleaned_images(self, data, expected):
        with pikepdf.Pdf.open(BytesIO(data), attempt_recovery=False) as document:
            self.assert_rewritten_structure(document)
            # pdf.objects inclut les objets non référencés, contrairement à page.images.
            images = [obj for obj in document.objects if isinstance(obj, pikepdf.Stream)
                      and obj.get("/Subtype") == pikepdf.Name.Image]
            self.assertEqual(1, len(images), "Une image résiduelle est présente")
            for obj in images:
                with pikepdf.PdfImage(obj).as_pil_image() as recovered:
                    self.assertEqual(expected.size, recovered.size)
                    self.assertEqual(expected.tobytes(), recovered.convert("RGB").tobytes())

    def test_native_with_pdfium_and_qpdf(self):
        for rotation in (0, 90, 180, 270):
            for cropped in (False, True):
                with self.subTest(rotation=rotation, cropped=cropped):
                    source, result, _, region = test_engine.NativeExperimentTests.replace_native(
                        rotation, cropped,
                    )
                    _, text = self.assert_render_local(source, result, region)
                    self.assertNotIn(TARGET, text)
                    self.assertIn(KEPT, text)
                    self.assertIn(test_raster.REPLACEMENT, text)
                    with pikepdf.Pdf.open(BytesIO(source), attempt_recovery=False) as original:
                        original_runs = text_runs(original.pages[0])
                    self.assertEqual(2, len(original_runs))
                    with pikepdf.Pdf.open(BytesIO(result), attempt_recovery=False) as document:
                        self.assert_rewritten_structure(document)
                        result_runs = b"".join(text_runs(document.pages[0]))
                        self.assertNotIn(original_runs[0], result_runs)
                        self.assertIn(original_runs[1], result_runs)

    def test_scans_ocr_and_mixed_with_pdfium_and_qpdf(self):
        for kind in ("scan", "ocr", "mixed"):
            for rotation in (0, 90, 180, 270):
                for cropped in (False, True):
                    with self.subTest(kind=kind, rotation=rotation, cropped=cropped):
                        (source, result, _, cleaned, _, _, _, region) = test_raster.replace_scan(
                            kind, rotation, cropped,
                        )
                        before, after = self.assert_render_local(source, result, region)
                        self.assertNotIn(test_raster.REPLACEMENT, after)
                        if kind == "mixed":
                            self.assertEqual(before, after)
                            self.assertIn(TARGET, after)
                        elif kind == "ocr":
                            self.assertIn(TARGET, before)
                            self.assertNotIn(TARGET, after)
                            self.assertIn(KEPT, after)
                        else:
                            self.assertEqual("", after.strip())
                        self.assert_cleaned_images(result, cleaned)

    def test_image_inspection_detects_a_hidden_original(self):
        _, result, original, cleaned, *_ = test_raster.replace_scan("scan")
        for referenced in (False, True):
            with self.subTest(referenced=referenced):
                with pymupdf.open(stream=result) as document:
                    xref = document.get_new_xref()
                    width, height = original.size
                    document.update_object(xref, (
                        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                        "/BitsPerComponent 8 /ColorSpace /DeviceRGB >>"
                    ))
                    document.update_stream(xref, original.tobytes())
                    if referenced:
                        # Récupérable mais non affiché ; sinon l'objet est entièrement inutilisé.
                        document.xref_set_key(document.pdf_catalog(), "TestHiddenImage", f"{xref} 0 R")
                    tampered = document.tobytes(garbage=0, deflate=True)
                with self.assertRaisesRegex(AssertionError, "image résiduelle"):
                    self.assert_cleaned_images(tampered, cleaned)


if __name__ == "__main__":
    unittest.main()
