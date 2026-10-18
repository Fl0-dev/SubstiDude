# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Frontières démontrées, pas de recherche de toutes les copies visuellement similaires."""

from io import BytesIO
import unittest
from unittest.mock import patch
import zlib

import pikepdf
import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageFont

from fixtures import FONT, TARGET_RECT, image_variant_pdf
from substidude.pdf_engine import PDFError, check_image_reuse, classify_zone, repeated_image_occurrences
import test_independent
import test_pipeline


class ImageBoundaryTests(unittest.TestCase):
    def image_from_page(self, data, number=0, *, raw_rgb=False):
        with pikepdf.Pdf.open(BytesIO(data)) as document:
            obj, = {obj.objgen: obj for obj in document.pages[number].get_images().values()}.values()
            if raw_rgb:
                # Lecture des nombres de composantes de la fixture, pas conversion de profil.
                obj.ColorSpace = pikepdf.Name.DeviceRGB
            with pikepdf.PdfImage(obj).as_pil_image() as image:
                return image.convert("RGB")

    def test_transformed_copies_are_not_exact_repetitions(self):
        for variant in ("pixel", "crop", "resize", "jpeg"):
            with self.subTest(variant=variant):
                source = image_variant_pdf(variant, pair=True)
                with pymupdf.open(stream=source) as document:
                    self.assertEqual([], repeated_image_occurrences(document))
                original = self.image_from_page(source)
                other = self.image_from_page(source, 1)
                self.assertNotEqual(test_pipeline.image_key(original), test_pipeline.image_key(other))
                if variant == "pixel":
                    # La donnée ciblée est exactement identique : le seul pixel changé est ailleurs.
                    self.assertEqual(original.crop((70, 140, 520, 210)).tobytes(),
                                     other.crop((70, 140, 520, 210)).tobytes())
                elif variant == "crop":
                    self.assertEqual(original.crop((70, 140, 520, 210)).tobytes(),
                                     other.crop((50, 140, 500, 210)).tobytes())
                elif variant == "resize":
                    restored = other.resize(original.size, Image.Resampling.NEAREST)
                    self.assertEqual(original.tobytes(), restored.tobytes())

    def test_unqualified_multi_image_raster_edit_is_refused(self):
        original_info = pymupdf.Page.get_image_info

        def metadata_only(page, **options):
            self.assertFalse(options.get("hashes"))
            self.assertFalse(options.get("xrefs"))
            return original_info(page, **options)

        for variant in ("pixel", "crop", "resize", "jpeg"):
            with self.subTest(variant=variant):
                source = image_variant_pdf(variant, pair=True)
                with pymupdf.open(stream=source) as document:
                    before = document.tobytes(no_new_id=True)
                    with patch.object(pymupdf.Page, "get_image_info", metadata_only):
                        with self.assertRaisesRegex(PDFError, "plusieurs|Plusieurs"):
                            check_image_reuse(document, 0, TARGET_RECT)
                    self.assertEqual(before, document.tobytes(no_new_id=True))
                with patch.object(pymupdf.Page, "replace_image") as replace:
                    with self.assertRaisesRegex(PDFError, "plusieurs|Plusieurs"):
                        test_pipeline.replace_zones(source, [(0, TARGET_RECT, "Toto")])
                    replace.assert_not_called()

    def test_single_gray_rgb_and_jpeg_image_qualification(self):
        for variant in ("gray", "rgb", "icc", "jpeg"):
            with self.subTest(variant=variant):
                source = image_variant_pdf(variant)
                self.assertEqual("scan", classify_zone(source, 0, TARGET_RECT))
                zones = [(0, TARGET_RECT, "Toto")]
                result = test_pipeline.replace_zones(source, zones)
                self.assertEqual("", test_pipeline.PipelineTests().assert_local_render(source, result, zones))
                expected = self.image_from_page(source)
                draw = ImageDraw.Draw(expected)
                draw.rectangle((70, 140, 519, 209), fill="white")
                draw.text((72, 142), "Toto", font=ImageFont.truetype(str(FONT), 28), fill="black", anchor="lt")
                test_independent.IndependentTests().assert_cleaned_images(result, expected)
                with pikepdf.Pdf.open(BytesIO(source)) as original, pikepdf.Pdf.open(BytesIO(result)) as document:
                    image, = [obj for obj in document.objects if isinstance(obj, pikepdf.Stream)
                              and obj.get("/Subtype") == pikepdf.Name.Image]
                    self.assertNotEqual(pikepdf.Name.DCTDecode, image.get("/Filter"))
                    original_image, = original.pages[0].get_images().values()
                    self.assertEqual(original_image.BitsPerComponent, image.BitsPerComponent)
                    if variant == "icc":
                        self.assertEqual(pikepdf.Name.ICCBased, image.ColorSpace[0])
                        self.assertEqual(original_image.ColorSpace[1].read_bytes(), image.ColorSpace[1].read_bytes())
                    else:
                        self.assertEqual(original_image.ColorSpace, image.ColorSpace)

    def test_unknown_profile_is_refused_before_transformation(self):
        source = image_variant_pdf("profile")
        with self.assertRaisesRegex(PDFError, "profil|couleur"):
            classify_zone(source, 0, TARGET_RECT)
        with patch.object(pymupdf.Page, "replace_image") as replace:
            with self.assertRaisesRegex(PDFError, "profil|couleur"):
                test_pipeline.replace_zones(source, [(0, TARGET_RECT, "Toto")])
            replace.assert_not_called()

    def test_unqualified_image_parameters_are_refused(self):
        for feature in ("intent", "interpolation", "predictor", "filter-chain"):
            with self.subTest(feature=feature):
                with pikepdf.Pdf.open(BytesIO(image_variant_pdf("rgb"))) as document:
                    obj, = document.pages[0].get_images().values()
                    if feature == "intent":
                        obj.Intent = pikepdf.Name.Perceptual
                    elif feature == "interpolation":
                        obj.Interpolate = True
                    elif feature == "predictor":
                        obj.DecodeParms = pikepdf.Dictionary(Predictor=1)
                    else:
                        obj.write(zlib.compress(obj.read_raw_bytes()), filter=pikepdf.Array([
                            pikepdf.Name.FlateDecode, pikepdf.Name.FlateDecode,
                        ]))
                    output = BytesIO()
                    document.save(output, stream_decode_level=pikepdf.StreamDecodeLevel.none,
                                  compress_streams=False)
                    source = output.getvalue()
                with self.assertRaisesRegex(PDFError, "paramètres|encodage"):
                    classify_zone(source, 0, TARGET_RECT)

    def test_equal_pixels_do_not_prove_color_profile_preservation(self):
        source = image_variant_pdf("profile")
        # Reproduction sans garde : réencoder les mêmes nombres RGB ne préserve
        # pas nécessairement le rendu d'un profil ICC d'entrée non qualifié.
        with pymupdf.open(stream=source) as document:
            xref = document[0].get_images()[0][0]
            with Image.open(BytesIO(document.extract_image(xref)["image"])) as image:
                rgb = image.convert("RGB")
            encoded = BytesIO()
            rgb.save(encoded, format="PNG")
            document[0].replace_image(xref, stream=encoded.getvalue())
            result = document.tobytes(garbage=4)
        self.assertEqual(self.image_from_page(source, raw_rgb=True).tobytes(),
                         self.image_from_page(result, raw_rgb=True).tobytes())
        before, *_ = test_independent.render_and_extract(source)
        after, *_ = test_independent.render_and_extract(result)
        difference = ImageChops.difference(before, after)
        difference.paste((0, 0, 0), (70, 140, 520, 210))
        self.assertIsNotNone(difference.getbbox())


if __name__ == "__main__":
    unittest.main()
