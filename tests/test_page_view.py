# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
import subprocess
import sys
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from substidude.page_view import PageView, page_transform


class PageViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_rotation_crop_zoom_and_hidpi_are_canonical(self):
        for rotation, point in ((0, (30, 75)), (90, (295, 30)), (180, (250, 295)), (270, (75, 250))):
            for zoom in (0.5, 1, 2):
                matrix = page_transform(280, 370, rotation, zoom)
                mapped = matrix.map(QPointF(30, 75))
                self.assertAlmostEqual(point[0] * zoom, mapped.x())
                self.assertAlmostEqual(point[1] * zoom, mapped.y())
                inverse, valid = matrix.inverted()
                self.assertTrue(valid)
                self.assertAlmostEqual(30, inverse.map(mapped).x())
                self.assertAlmostEqual(75, inverse.map(mapped).y())

    def test_selection_clamps_to_page_and_follows_half_point_grid(self):
        view = PageView()
        view.configure(280, 370, 90, 2)
        rect = view.canonical_rectangle(QPointF(-20, -30), QPointF(60.3, 100.7))
        self.assertTrue(all(value * 2 == round(value * 2) for value in rect))
        self.assertTrue(0 <= rect[0] < rect[2] <= 280)
        self.assertTrue(0 <= rect[1] < rect[3] <= 370)
        view.close()

    def test_qt_hidpi_keeps_logical_image_and_canonical_zones_aligned(self):
        script = (
            "from PySide6.QtWidgets import QApplication; from PySide6.QtGui import QPixmap; "
            "from substidude.page_view import PageView; app=QApplication([]); view=PageView(); "
            "dpr=view.devicePixelRatioF(); view.configure(300,400,0,1); "
            "pix=QPixmap(round(300*dpr),round(400*dpr)); view.set_page(pix,[],False,dpr); "
            "assert abs(view.sceneRect().width()-300)<1; "
            "assert abs(view.sceneRect().height()-400)<1; view.close()"
        )
        for scale in ("1", "1.25", "1.5", "2"):
            with self.subTest(scale=scale):
                result = subprocess.run([sys.executable, "-B", "-W", "error", "-c", script],
                    env={**os.environ, "QT_SCALE_FACTOR": scale}, capture_output=True, timeout=15)
                self.assertEqual(0, result.returncode, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
