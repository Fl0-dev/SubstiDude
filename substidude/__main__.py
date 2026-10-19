# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

import multiprocessing
import sys


def main():
    # Ne pas importer Qt ou un moteur PDF au niveau module : spawn réimporte
    # ce point d'entrée dans l'enfant avant l'établissement du budget natif.
    from PySide6.QtWidgets import QApplication
    from substidude.window import Window
    from substidude.worker import PDFJob, WorkerError
    application = QApplication(sys.argv)
    application.setApplicationName("SubstiDude")
    window = Window()
    try:
        with PDFJob() as job:
            job.start("cleanup")
            job.receive()
    except WorkerError:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(window, "Nettoyage local", "Le nettoyage des temporaires abandonnés n'a pas pu être terminé. Aucun document n'a été envoyé.")
    window.show()
    if "--smoke-test" in sys.argv:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, window.close)
    return application.exec()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
