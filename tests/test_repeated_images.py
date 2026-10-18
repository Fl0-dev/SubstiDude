# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

from io import BytesIO
import unittest

import pikepdf
import pymupdf
from PIL import Image

from fixtures import TARGET_RECT, image_dimensions_pdf, make_pdf, repeated_images_pdf
from substidude.pdf_engine import PDFError, check_image_reuse, repeated_image_occurrences


class RepeatedImageTests(unittest.TestCase):
    def test_shared_objects_and_copies_including_forms(self):
        for separate in (False, True):
            for nested in (False, True):
                for reencoded in (False, True):
                    if reencoded and not separate:
                        continue
                    with self.subTest(separate=separate, nested=nested, reencoded=reencoded):
                        data = repeated_images_pdf(
                            separate_objects=separate, nested=nested, reencoded=reencoded,
                        )
                        with pikepdf.Pdf.open(BytesIO(data), attempt_recovery=False) as check:
                            images = [obj for obj in check.objects if isinstance(obj, pikepdf.Stream)
                                      and obj.get("/Subtype") == pikepdf.Name.Image]
                            self.assertEqual(2 if separate else 1, len(images))
                            if separate:
                                self.assertNotEqual(images[0].objgen, images[1].objgen)
                                self.assertEqual(images[0].read_bytes(), images[1].read_bytes())
                                if reencoded:
                                    self.assertTrue(images[0].read_raw_bytes() != images[1].read_raw_bytes(),
                                                    "Le réencodage doit produire deux flux PDF distincts")
                        with pymupdf.open(stream=data) as document:
                            before = document.tobytes(garbage=0, no_new_id=True)
                            groups = repeated_image_occurrences(document)
                            self.assertEqual(before, document.tobytes(garbage=0, no_new_id=True))
                            self.assertEqual(1, len(groups))
                            self.assertEqual([0, 1], [number for number, _ in groups[0]])
                            for _, rect in groups[0]:
                                self.assertEqual(pymupdf.Rect(0, 0, 300, 400), rect)

    def test_multiple_occurrences_on_one_page(self):
        with pymupdf.open(stream=repeated_images_pdf(same_page=True)) as document:
            groups = repeated_image_occurrences(document)
            self.assertEqual(1, len(groups))
            self.assertEqual([0, 0], [number for number, _ in groups[0]])
            self.assertEqual(pymupdf.Rect(0, 400, 300, 800), groups[0][1][1])

    def test_unique_scan_has_no_repetition(self):
        with pymupdf.open(stream=make_pdf("scan")) as document:
            self.assertEqual([], repeated_image_occurrences(document))
            check_image_reuse(document, 0, TARGET_RECT)

    def test_local_edits_of_repeated_images_refused_without_mutation(self):
        for separate in (False, True):
            for nested in (False, True):
                with self.subTest(separate=separate, nested=nested):
                    with pymupdf.open(stream=repeated_images_pdf(
                        separate_objects=separate, nested=nested,
                    )) as document:
                        original = document.tobytes(no_new_id=True)
                        with self.assertRaisesRegex(PDFError, "pages 1, 2"):
                            check_image_reuse(document, 0, TARGET_RECT)
                        self.assertEqual(original, document.tobytes(no_new_id=True))

    def test_unrelated_page_not_blocked_by_repeated_images(self):
        with pymupdf.open(stream=repeated_images_pdf()) as document:
            document.new_page(width=300, height=400)
            check_image_reuse(document, 2, TARGET_RECT)

    def test_invalid_edit_zone_is_rejected(self):
        with pymupdf.open(stream=make_pdf("scan")) as document:
            for page, rect in ((-1, TARGET_RECT), (1, TARGET_RECT),
                               (0, (0, 0, 0, 0)), (0, (-1, 0, 10, 10)),
                               (0, (0, 0, float("inf"), 10)), (0, None),
                               (0, (0, 0, 1)), (0.5, TARGET_RECT)):
                with self.subTest(page=page, rectangle=rect), self.assertRaises(PDFError):
                    check_image_reuse(document, page, rect)

    def test_mixed_color_spaces_refused_before_pixel_hashing(self):
        from unittest.mock import patch
        with pymupdf.open(stream=make_pdf("scan")) as document:
            gray = BytesIO()
            Image.new("L", (10, 10), 255).save(gray, format="PNG")
            document[0].insert_image((0, 0, 10, 10), stream=gray.getvalue())
            original = pymupdf.Page.get_image_info

            def metadata_only(page, **options):
                self.assertFalse(options.get("hashes"))
                return original(page, **options)

            with patch.object(pymupdf.Page, "get_image_info", metadata_only):
                with self.assertRaisesRegex(PDFError, "espaces couleur"):
                    repeated_image_occurrences(document)

    def test_identical_geometry_does_not_make_different_pixels_equal(self):
        with pymupdf.open(stream=make_pdf("scan")) as document:
            page = document.new_page(width=300, height=400)
            other = BytesIO()
            Image.new("RGB", (600, 800), "white").save(other, format="PNG")
            page.insert_image(page.rect, stream=other.getvalue())
            self.assertEqual([], repeated_image_occurrences(document))

    def test_same_pixels_detected_at_a_different_display_scale(self):
        with pymupdf.open(stream=make_pdf("scan")) as document:
            xref = document[0].get_images()[0][0]
            page = document.new_page(width=300, height=400)
            page.insert_image((30, 40, 180, 240), xref=xref)
            groups = repeated_image_occurrences(document)
            self.assertEqual(1, len(groups))
            self.assertEqual(pymupdf.Rect(30, 40, 180, 240), groups[0][1][1])

    def test_masks_refused_before_pixel_hashing(self):
        from unittest.mock import patch
        with pymupdf.open(stream=image_dimensions_pdf(8, 8, mask=True)) as document:
            original = pymupdf.Page.get_image_info

            def metadata_only(page, **options):
                self.assertFalse(options.get("hashes"))
                return original(page, **options)

            with patch.object(pymupdf.Page, "get_image_info", metadata_only):
                with self.assertRaisesRegex(PDFError, "masque"):
                    repeated_image_occurrences(document)


if __name__ == "__main__":
    unittest.main()
