# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

from pathlib import Path
import unittest

import pymupdf
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "substidude" / "resources" / "NotoSans-Regular.ttf"


class SetupTests(unittest.TestCase):
    def test_accented_font_in_pdf_and_pixels(self):
        text = "Société Exemple — Élodie à Noël"
        font = pymupdf.Font(fontfile=str(FONT))
        self.assertTrue(all(font.has_glyph(ord(char)) for char in text))
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_font(fontname="noto", fontfile=str(FONT))
            page.insert_text((50, 80), text, fontname="noto", fontsize=14)
            data = document.tobytes()
        with pymupdf.open(stream=data, filetype="pdf") as result:
            self.assertIn(text, result[0].get_text())
            self.assertGreater(result[0].get_pixmap().width, 0)

        image = Image.new("RGB", (600, 80), "white")
        ImageDraw.Draw(image).text(
            (10, 10), text, font=ImageFont.truetype(str(FONT), 24), fill="black"
        )
        self.assertIsNotNone(Image.eval(image.convert("L"), lambda x: 255 - x).getbbox())

    def test_project_license_and_font_notice_present(self):
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", (ROOT / "LICENSE").read_text())
        notice = (FONT.parent / "OFL.txt").read_text(encoding="utf-8")
        self.assertIn("SIL OPEN FONT LICENSE", notice)


if __name__ == "__main__":
    unittest.main()
