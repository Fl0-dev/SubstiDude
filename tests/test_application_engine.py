# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import unittest
from hashlib import sha256
from io import BytesIO

import pymupdf
from PIL import Image

from fixtures import TARGET, TARGET_RECT, make_pdf
from substidude.model import Substitution
from substidude.pipeline import transform
import test_pipeline
from fixtures import image_variant_pdf
from substidude.pdf_engine import PDFError


class ApplicationEngineTests(unittest.TestCase):
    def test_four_modes_with_immutable_source(self):
        for kind in ("native", "scan", "ocr", "mixed"):
            with self.subTest(kind=kind):
                source = make_pdf(kind)
                digest = sha256(source).digest()
                rect = pymupdf.Rect(TARGET_RECT) + ((0, 200, 0, 200) if kind == "mixed" else (0, 0, 0, 0))
                result = transform(source, [Substitution(0, tuple(rect), "Société Élodie")])
                text = test_pipeline.PipelineTests().assert_local_render(source, result, [(0, rect, "Société Élodie")])
                self.assertEqual(kind == "native", "Société Élodie" in text)
                if kind in ("native", "ocr"):
                    self.assertNotIn(TARGET, text)
                self.assertEqual(digest, sha256(source).digest())

    def test_multiline_with_automatic_font_size(self):
        for kind in ("native", "scan", "ocr"):
            with self.subTest(kind=kind):
                source = make_pdf(kind)
                result = transform(source, [Substitution(0, TARGET_RECT, "Toto\nÉlodie")])
                with pymupdf.open(stream=result) as document:
                    text = document[0].get_textbox(TARGET_RECT)
                    self.assertEqual("Toto\nÉlodie" if kind == "native" else "", text)
                test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Toto\nÉlodie")])

    def test_white_background_pixels_and_grayscale_preserved(self):
        for variant in ("rgb", "gray"):
            with self.subTest(variant=variant):
                source = image_variant_pdf(variant)
                result = transform(source, [Substitution(0, TARGET_RECT, "Toto")])
                with pymupdf.open(stream=result) as document:
                    image, = document[0].get_images()
                    with Image.open(BytesIO(document.extract_image(image[0])["image"])) as recovered:
                        self.assertEqual((255, 255, 255), recovered.convert("RGB").getpixel((70, 140)))
                        self.assertEqual("L" if variant == "gray" else "RGB", recovered.mode)
                test_pipeline.PipelineTests().assert_local_render(source, result, [(0, TARGET_RECT, "Toto")])

    def test_multiline_overflow_and_unrepresentable_font_are_refused(self):
        for kind in ("native", "scan", "ocr"):
            for text in (("Toto\n" * 100), "\U0010ffff"):
                with self.subTest(kind=kind, text_length=len(text)), self.assertRaises(PDFError):
                    transform(make_pdf(kind), [Substitution(0, TARGET_RECT, text)])


if __name__ == "__main__":
    unittest.main()
