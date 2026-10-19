# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
from time import monotonic
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from fixtures import TARGET_RECT, make_pdf
from substidude.window import Window
from substidude.model import Substitution


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="substidude-ui-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "synthetic.pdf"
        self.path.write_bytes(make_pdf())
        self.window = Window()
        self.errors = []
        self.window.error = self.errors.append
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.window.dirty = False
        self.window.close()

    def wait(self):
        deadline = monotonic() + 20
        while (self.window.busy or self.window.preview_timer.isActive()) and monotonic() < deadline:
            QTest.qWait(20)
        self.assertFalse(self.window.busy)
        self.assertFalse(self.window.preview_timer.isActive())
        self.assertEqual([], self.errors)

    def test_open_edit_preview_confirmation_and_invalidation(self):
        self.window.open_path(str(self.path))
        self.wait()
        self.window.add_rectangle(TARGET_RECT)
        self.wait()
        self.assertEqual(1, self.window.zones.count())
        result = self.window.session.result
        self.assertTrue(self.window.preview)
        self.assertTrue(self.window.confirmation.isEnabled())
        self.window.zoom = 3
        self.window.render()
        self.wait()
        self.window.view.verticalScrollBar().setValue(120)
        position = self.window.view.verticalScrollBar().value()
        self.window.confirmation.setChecked(True)
        self.assertIs(result, self.window.session.confirmed_bytes())
        self.assertTrue(self.window.preview)
        self.assertTrue(self.window.view.editable)
        self.assertFalse(self.window.result_view.editable)
        self.assertEqual(3, self.window.zoom)
        self.assertEqual(position, self.window.view.verticalScrollBar().value())
        self.assertIs(result, self.window.session.confirmed_bytes())
        self.window.zones.setCurrentRow(0)
        self.window.text.setPlainText("Élodie")
        self.assertIsNone(self.window.session.result)
        self.assertFalse(self.window.confirmation.isChecked())
        self.assertFalse(self.window.confirmation.isEnabled())
        self.assertEqual([], self.window.result_view.scene().items())
        self.wait()
        self.assertIsNotNone(self.window.session.result)
        self.assertFalse(self.window.confirmation.isChecked())

    def test_close_confirmation_and_cancellation(self):
        self.window.open_path(str(self.path))
        self.wait()
        self.window.add_rectangle(TARGET_RECT)
        self.wait()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.close())
        self.window.generate()
        self.window.cancel_work()
        self.assertIsNone(self.window.job.process)
        self.assertIsNone(self.window.session.result)

    def test_text_edits_are_debounced_and_both_panes_remain_distinct(self):
        self.window.open_path(str(self.path))
        self.wait()
        self.assertTrue(self.window.view.scene().items())
        self.assertTrue(self.window.result_view.scene().items())
        self.window.add_rectangle(TARGET_RECT)
        self.wait()
        self.window.confirmation.setChecked(True)
        with patch.object(self.window, "generate", wraps=self.window.generate) as generate:
            for text in ("A", "AB", "ABC"):
                self.window.text.setPlainText(text)
                QTest.qWait(40)
            self.assertEqual(0, generate.call_count)
            self.assertIsNone(self.window.session.result)
            self.assertFalse(self.window.confirmation.isChecked())
            self.wait()
            self.assertEqual(1, generate.call_count)
        self.assertEqual("ABC", self.window.session.substitutions[0].text)
        self.assertTrue(self.window.view.editable)
        self.assertFalse(self.window.result_view.editable)
        self.assertTrue(self.window.view.scene().items())
        self.assertTrue(self.window.result_view.scene().items())
        self.assertEqual(self.path.read_bytes(), self.window.session.source)

    def test_automatic_preview_refusal_is_inline_not_modal(self):
        self.window.open_path(str(self.path))
        self.wait()
        self.window.add_rectangle((45, 80, 80, 90))
        self.wait()
        self.assertIsNone(self.window.session.result)
        self.assertFalse(self.window.confirmation.isEnabled())
        self.assertEqual([], self.window.result_view.scene().items())
        self.assertIn("Après —", self.window.result_label.text())
        self.assertEqual([], self.errors)

    def test_mouse_zone_selection_without_manual_settings(self):
        self.window.show()
        self.window.open_path(str(self.path))
        self.wait()
        view = self.window.view
        start, end = view.mapFromScene(QPointF(35, 70)), view.mapFromScene(QPointF(260, 105))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.wait()
        self.assertEqual(TARGET_RECT, self.window.session.substitutions[0].rectangle)
        self.window.zones.setCurrentRow(0)
        for name in ("coordinates", "font_size", "background_button", "choose_background", "toggle_button", "generate_button"):
            self.assertFalse(hasattr(self.window, name))

    def test_all_pages_must_be_previewed_and_export_is_exact(self):
        self.path.write_bytes(make_pdf(pages=2))
        self.window.open_path(str(self.path))
        self.wait()
        self.window.add_rectangle(TARGET_RECT)
        self.wait()
        self.window.generate()
        self.wait()
        self.assertFalse(self.window.confirmation.isEnabled())
        self.window.change_page(1)
        self.wait()
        self.assertTrue(self.window.confirmation.isEnabled())
        self.window.confirmation.setChecked(True)
        result = self.window.session.confirmed_bytes()
        target = Path(self.directory.name) / "copy.pdf"
        with patch("substidude.window.QFileDialog.getSaveFileName", return_value=(str(target), "PDF")):
            self.window.choose_export()
            self.wait()
        self.assertEqual(result, target.read_bytes())
        self.assertEqual("Exporté", self.window.session.state)
        self.assertFalse(self.window.dirty)

    def test_failed_page_render_does_not_leave_a_stale_editable_image(self):
        self.window.open_path(str(self.path))
        self.wait()
        self.assertTrue(self.window.view.editable)
        with patch.object(self.window.job, "receive", side_effect=ValueError("synthetic")):
            self.window.render()
            deadline = monotonic() + 15
            while self.window.busy and monotonic() < deadline:
                QTest.qWait(20)
        self.window.job.cancel()
        self.assertFalse(self.window.busy)
        self.assertFalse(self.window.view.editable)
        self.assertEqual([], self.window.view.scene().items())
        self.assertIsNone(self.window.preview_revision)

    def test_mouse_move_resize_and_remove_update_the_selected_zone(self):
        self.window.show()
        self.window.open_path(str(self.path))
        self.wait()
        self.window.add_rectangle(TARGET_RECT)
        self.wait()
        view = self.window.view
        start = view.mapFromScene(QPointF(80, 85))
        end = view.mapFromScene(QPointF(90, 90))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        QTest.qWait(30)
        self.wait()
        self.assertEqual((45, 75, 270, 110), self.window.session.substitutions[0].rectangle)
        start = view.mapFromScene(QPointF(270, 110))
        end = view.mapFromScene(QPointF(280, 120))
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        QTest.qWait(30)
        self.wait()
        self.assertEqual((45, 75, 280, 120), self.window.session.substitutions[0].rectangle)
        self.window.zones.setCurrentRow(0)
        self.window.remove_zone()
        self.wait()
        self.assertEqual((), self.window.session.substitutions)


if __name__ == "__main__":
    unittest.main()
