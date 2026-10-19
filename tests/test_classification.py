# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Reconnaissance expérimentale uniquement, sans transformation ni export."""

import hashlib
import unittest

import pymupdf

from fixtures import TARGET_RECT, auxiliary_pdf, make_pdf, repeated_images_pdf, zone_case_pdf
from substidude.pdf_engine import PDFError, classify_zone


class ClassificationTests(unittest.TestCase):
    def test_modes_crop_and_rotation_without_mutating_source(self):
        for kind in ("native", "scan", "ocr", "mixed"):
            for rotation in (0, 90, 180, 270):
                for cropped in (False, True):
                    source = make_pdf(kind, rotation=rotation, cropped=cropped)
                    before = hashlib.sha256(source).digest()
                    rect = pymupdf.Rect(TARGET_RECT)
                    if cropped:
                        rect += (-10, -20, -10, -20)
                    with self.subTest(kind=kind, rotation=rotation, cropped=cropped):
                        self.assertEqual("native" if kind == "mixed" else kind,
                                         classify_zone(source, 0, rect))
                        if kind == "mixed":
                            self.assertEqual("scan", classify_zone(source, 0, rect + (0, 200, 0, 200)))
                        self.assertEqual(before, hashlib.sha256(source).digest())

    def test_ambiguous_or_unqualified_structures_are_refused(self):
        for feature in ("visible-overlay", "text-overlap", "transparent-text", "hidden-text",
                        "mask", "vector", "clip", "shear", "image-rotation", "mirror",
                         "image-scale", "two-images", "invisible-native", "text-clip",
                        "unknown-operator", "missing-resources", "invalid-xobject"):
            with self.subTest(feature=feature):
                source = zone_case_pdf(feature)
                with self.assertRaises(PDFError) as caught:
                    classify_zone(source, 0, TARGET_RECT)
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertNotIn("AUTRE-TEXTE", str(caught.exception))
        # Extension native qualifiée : ce cas n'est plus un refus de page
        # systématique. Les Form raster/masques/ambiguïtés restent refusés.
        self.assertEqual("native", classify_zone(zone_case_pdf("nested"), 0, TARGET_RECT))

    def test_invalid_and_empty_zones_are_refused(self):
        source = make_pdf()
        for page, rect in ((-1, TARGET_RECT), (1, TARGET_RECT), (0.5, TARGET_RECT),
                           (0, (0, 0, 0, 10)), (0, (-1, 0, 30, 30)),
                           (0, (0, 0, float("inf"), 10)), (0, (270, 300, 290, 350)),
                           (0, None), (0, (0, 0, 1)), (0, "SECRET-INVALIDE"),
                           (True, TARGET_RECT)):
            with self.subTest(page=page, rectangle=rect), self.assertRaises(PDFError):
                classify_zone(source, page, rect)

    def test_zone_crossing_native_and_scan_regions_is_refused(self):
        with self.assertRaisesRegex(PDFError, "image|superposition"):
            classify_zone(make_pdf("mixed"), 0, (35, 70, 260, 305))

    def test_repeated_image_is_not_classified_as_editable(self):
        for separate in (False, True):
            source = repeated_images_pdf(separate_objects=separate)
            with self.subTest(separate=separate), self.assertRaisesRegex(PDFError, "réutilisée"):
                classify_zone(source, 0, TARGET_RECT)

    def test_invisible_text_is_not_assumed_to_be_native(self):
        with self.assertRaisesRegex(PDFError, "invisible|natif"):
            classify_zone(zone_case_pdf("invisible-native"), 0, TARGET_RECT)

    def test_image_transform_refusals_reach_the_transform_guard(self):
        for feature in ("shear", "image-rotation", "mirror", "image-scale"):
            with self.subTest(feature=feature), self.assertRaisesRegex(PDFError, "transformation"):
                classify_zone(zone_case_pdf(feature), 0, TARGET_RECT)

    def test_other_pages_and_input_preflight(self):
        self.assertEqual("native", classify_zone(make_pdf(pages=2), 1, TARGET_RECT))
        for source in (b"", b"not a PDF", make_pdf(pages=50), make_pdf(encrypted=True),
                       auxiliary_pdf("actualtext")):
            with self.subTest(size=len(source)), self.assertRaises(PDFError):
                classify_zone(source, 0, TARGET_RECT)


if __name__ == "__main__":
    unittest.main()
