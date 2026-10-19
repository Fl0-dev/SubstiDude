# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Contrôle de la sonde, sans seuil de performance ni allocation démesurée."""

from io import BytesIO
import unittest

import pikepdf

from fixtures import FONT, TARGET_RECT, make_pdf
from measure_resources import decoded_stream_sizes, process_memory, synthetic_sample
from substidude.pdf_engine import classify_zone


class ResourceMeasurementTests(unittest.TestCase):
    def test_windows_counters_are_available(self):
        counters = process_memory()
        self.assertGreater(counters["working_set_bytes"], 0)
        self.assertGreater(counters["private_bytes"], 0)
        self.assertGreaterEqual(counters["peak_working_set_bytes"], counters["working_set_bytes"])

    def test_stream_accounting_includes_font_cmap_and_profile(self):
        source = make_pdf("ocr")
        sizes = decoded_stream_sizes(source)
        self.assertEqual(FONT.stat().st_size, sizes["font_bytes"])
        with pikepdf.Pdf.open(BytesIO(source)) as document:
            cmap = document.pages[0].obj.Resources.Font.noto.ToUnicode.read_bytes()
            image, = document.pages[0].get_images().values()
            profile = image.ColorSpace[1].read_bytes()
        self.assertEqual(len(cmap), sizes["cmap_bytes"])
        self.assertEqual(len(profile), sizes["icc_bytes"])
        self.assertGreaterEqual(sizes["decoded_total_bytes"], sum(
            sizes[key] for key in ("font_bytes", "cmap_bytes", "icc_bytes")))

    def test_compressed_stream_sample_has_real_small_geometry(self):
        source, rect = synthetic_sample("stream-1mib")
        self.assertEqual(TARGET_RECT, rect)
        sizes = decoded_stream_sizes(source)
        self.assertEqual(1024 * 1024, sizes["decoded_max_bytes"])
        self.assertLess(len(source), sizes["decoded_max_bytes"])
        self.assertEqual("native", classify_zone(source, 0, rect))

    def test_scaled_scan_remains_one_real_image_at_two_pixels_per_point(self):
        source, rect = synthetic_sample("ocr-1.92mp")
        self.assertEqual("ocr", classify_zone(source, 0, rect))
        with pikepdf.Pdf.open(BytesIO(source)) as document:
            image, = document.pages[0].get_images().values()
            self.assertEqual((1200, 1600), (image.Width, image.Height))
            self.assertEqual(1, sum(obj.get("/Subtype") == pikepdf.Name.Image
                                    for obj in document.objects if isinstance(obj, pikepdf.Stream)))


if __name__ == "__main__":
    unittest.main()
