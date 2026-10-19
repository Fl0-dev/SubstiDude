# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Recette GUI automatisée de développement, gelable sans QtTest ni PDFium.

Entrées : quatre fixtures synthétiques native/scan/ocr/mixed.pdf générées par
les tests dans un dossier temporaire. Aucun outil de test ni moteur importé
dans le parent. Pilote les méthodes de la fenêtre réelle et ses callbacks.
Ne remplace pas la recette humaine des gestes, des dialogues ou du poste cible.
"""

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import sys
from time import monotonic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    options = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QTimer, qVersion
    from PySide6.QtWidgets import QApplication
    from substidude.window import Window

    application = QApplication([])
    application.setQuitOnLastWindowClosed(False)

    class Recipe:
        def __init__(self):
            self.window = Window()
            self.errors, self.checks = [], []
            self.window.error = self.errors.append
            self.kinds = iter(("native", "scan", "ocr", "mixed"))
            self.started, self.stage = monotonic(), "next"
            self.passed = False
            self.result = None
            self.timer = QTimer()
            self.timer.setInterval(20)
            self.timer.timeout.connect(self.advance)
            self.timer.start()

        def stop(self, passed):
            self.passed = passed
            self.timer.stop()
            self.window.cancel_work()
            self.window.dirty = False
            self.window.close()
            application.quit()

        def advance(self):
            try:
                if self.errors or monotonic() - self.started > 90:
                    raise AssertionError("Recette interrompue.")
                if self.window.busy:
                    return
                if self.stage == "next":
                    kind = next(self.kinds, None)
                    if kind is None:
                        if any(name in sys.modules for name in ("pymupdf", "pikepdf", "PIL", "pypdfium2")):
                            raise AssertionError("Moteur importé dans le parent.")
                        self.stop(True)
                        return
                    self.kind = kind
                    self.path = options.directory / (kind + ".pdf")
                    self.destination = options.directory / (kind + "-gui-export.pdf")
                    if self.destination.exists():
                        raise AssertionError("La recette ne remplace aucune sortie existante.")
                    self.original = self.path.read_bytes()
                    self.window.open_path(str(self.path))
                    self.stage = "opened"
                elif self.stage == "opened":
                    self.window.text.setPlainText("Société Élodie")
                    rect = (35, 270, 260, 305) if self.kind == "mixed" else (35, 70, 260, 105)
                    self.window.add_rectangle(rect)
                    self.stage = "edited"
                elif self.stage == "edited":
                    if self.window.preview_timer.isActive():
                        return
                    self.stage = "previewed"
                elif self.stage == "previewed":
                    if not self.window.preview or not self.window.confirmation.isEnabled():
                        raise AssertionError("Résultat non prévisualisé.")
                    self.window.confirmation.setChecked(True)
                    self.result = self.window.session.begin_export()
                    self.window.dirty = True
                    self.window.submit("export", self.result, path=str(self.destination),
                        source_path=str(self.path), revision=self.window.session.revision,
                        callback=lambda response: self.window.exported(response, self.result))
                    self.stage = "exported"
                elif self.stage == "exported":
                    if (self.window.session.state != "Exporté" or self.window.dirty
                            or self.destination.read_bytes() != self.result
                            or self.path.read_bytes() != self.original):
                        raise AssertionError("Export non vérifié.")
                    self.checks.append(self.kind + "-window-open-edit-preview-confirm-export")
                    self.stage = "next"
            except Exception:
                self.stop(False)

    recipe = Recipe()
    application.exec()
    print(json.dumps({"passed": recipe.passed, "checks": recipe.checks,
                      "frozen": bool(getattr(sys, "frozen", False)), "qt": qVersion(),
                      "parent_without_pdf_engines": not any(
                          name in sys.modules for name in ("pymupdf", "pikepdf", "PIL", "pypdfium2")),
                      "human_recipe": False}))
    return 0 if recipe.passed else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
