# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Lecteur local et aperçu des mêmes octets contrôlés que le futur export."""

from dataclasses import replace
import json
import struct
from pathlib import Path
import os
import sys

from PySide6.QtCore import QSignalBlocker, QTimer, Qt
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QTabWidget, QTextEdit, QToolBar, QVBoxLayout, QWidget,
)

from substidude.model import Session, SessionError, Substitution
from substidude.page_view import PageView
from substidude.worker import PDFJob, WorkerError


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SubstiDude — documents synthétiques uniquement")
        self.resize(1100, 800)
        self.session = self.source_path = None
        self.pages, self.page, self.zoom = [], 0, 1.0
        self.preview, self.dirty, self.busy = False, False, False
        self.visited, self.preview_revision = set(), None
        self.scroll_position = (0, 0)
        self.job, self.callback, self.generation = PDFJob(), None, None
        self.source_pixmap = None
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(400)
        self.preview_timer.timeout.connect(self.automatic_preview)
        self._closing = False
        toolbar = QToolBar("Document et navigation", self)
        self.addToolBar(toolbar)
        self.actions = []

        def action(title, shortcut, callback):
            item = QAction(title, self)
            if shortcut:
                item.setShortcut(QKeySequence(shortcut))
            item.triggered.connect(callback)
            toolbar.addAction(item)
            self.actions.append(item)
            return item

        action("Ouvrir", "Ctrl+O", self.choose_file)
        action("Page précédente", "PgUp", lambda: self.change_page(-1))
        action("Page suivante", "PgDown", lambda: self.change_page(1))
        action("Zoom −", "Ctrl+-", lambda: self.change_zoom(1 / 1.25))
        action("Zoom +", "Ctrl++", lambda: self.change_zoom(1.25))
        action("Ajuster", "Ctrl+0", self.fit_page)
        self.page_label = QLabel("Aucun document")
        toolbar.addWidget(self.page_label)
        self.cancel_button = QPushButton("Annuler le traitement")
        self.cancel_button.clicked.connect(self.cancel_work)
        toolbar.addWidget(self.cancel_button)
        self.view = PageView()
        self.result_view = PageView()
        self.result_view.setAccessibleName("Après — résultat PDF réel, lecture seule")
        self.result_label = QLabel("Après — dessinez une zone pour générer l'aperçu")
        for name in ("horizontalScrollBar", "verticalScrollBar"):
            before, after = getattr(self.view, name)(), getattr(self.result_view, name)()
            before.valueChanged.connect(after.setValue)
            after.valueChanged.connect(before.setValue)
        self.view.rectangleCreated.connect(self.add_rectangle)
        self.view.rectangleChanged.connect(self.move_rectangle)
        self.zones = QListWidget()
        self.view.rectangleSelected.connect(self.zones.setCurrentRow)
        self.zones.setAccessibleName("Substitutions — page et texte fictif")
        self.zones.currentRowChanged.connect(self.select_zone)
        self.zones.itemDoubleClicked.connect(self.go_to_zone)
        side = QWidget()
        layout = QVBoxLayout(side)
        layout.addWidget(QLabel("Substitutions (double-clic : aller à la zone)"))
        layout.addWidget(self.zones)
        form = QFormLayout()
        self.presets = QComboBox()
        self.presets.addItems(["Texte libre", "Toto", "John Doe", "Société Exemple", "12 rue Exemple, 75000 Ville", "Effacement"])
        self.presets.currentIndexChanged.connect(self.use_preset)
        form.addRow("Valeur proposée", self.presets)
        self.text = QTextEdit("Toto")
        self.text.setAccessibleName("Texte fictif de remplacement")
        self.text.setMaximumHeight(90)
        form.addRow("Remplacement", self.text)
        self.text.textChanged.connect(self.update_text)
        layout.addLayout(form)
        self.remove_button = QPushButton("Supprimer la zone")
        self.remove_button.clicked.connect(self.remove_zone)
        layout.addWidget(self.remove_button)
        delete = QShortcut(QKeySequence("Delete"), self.view, activated=self.remove_zone)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.confirmation = QCheckBox("J'ai vérifié le document")
        self.confirmation.toggled.connect(self.confirm)
        layout.addWidget(self.confirmation)
        self.export_button = QPushButton("Exporter la copie vérifiée…")
        self.export_button.clicked.connect(self.choose_export)
        layout.addWidget(self.export_button)
        self.state_label = QLabel("À vérifier")
        layout.addWidget(self.state_label)
        self.warning = QLabel(
            "Sélectionnez toute l'information ; un élément traversant la limite sera refusé.\n"
            "Avant partage, contrôlez toutes les pages : signatures, photos, QR codes, codes-barres, "
            "coordonnées, références et identifiants indirects.\n"
            "Des copies cachées peuvent subsister (limite 11B) ; aucune anonymisation exhaustive.\n"
            "Scan : remplacement en pixels, sans nouvelle couche OCR. Champs et signatures refusés."
        )
        self.warning.setWordWrap(True)
        layout.addWidget(self.warning)
        self.editor = side
        splitter = QSplitter()
        for label, view in ((QLabel("Avant — original et zones d'édition"), self.view), (self.result_label, self.result_view)):
            pane = QWidget()
            column = QVBoxLayout(pane)
            column.addWidget(label)
            column.addWidget(view)
            splitter.addWidget(pane)
        splitter.addWidget(side)
        splitter.setSizes([400, 400, 300])
        self.setCentralWidget(splitter)
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.poll)
        about = self.menuBar().addMenu("Aide").addAction("À propos / Licences")
        about.triggered.connect(self.about)
        self.sync()

    def error(self, message):
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, "Traitement refusé", message)

    def sync(self):
        for action in self.actions:
            action.setEnabled(not self.busy)
        self.cancel_button.setEnabled(self.busy)
        self.view.setEnabled(not self.busy)
        self.editor.setEnabled(not self.busy and self.session is not None)
        if self.session:
            ready = (not self.busy and self.preview and self.preview_revision == self.session.revision
                     and len(self.visited) == len(self.pages) and self.session.result is not None)
            self.confirmation.setEnabled(ready)
            with QSignalBlocker(self.confirmation):
                self.confirmation.setChecked(self.session.state in {"Vérifié par l'utilisateur", "Exporté"})
            self.state_label.setText(self.session.state)
            self.export_button.setEnabled(not self.busy and self.session.state in {"Vérifié par l'utilisateur", "Exporté"})
            self.page_label.setText(f"Page {self.page + 1}/{len(self.pages)} — {self.zoom:.0%}")

    def submit(self, operation, source=b"", callback=None, **options):
        if self.busy:
            raise WorkerError("Un traitement est déjà actif.")
        try:
            self.job.start(operation, source, **options)
        except WorkerError as error:
            if self.session:
                self.session.fail_generation(self.generation)
            self.generation = None
            self.sync()
            self.error(str(error))
            return
        self.callback = callback
        self.busy = True
        self.statusBar().showMessage("Traitement local en cours…")
        self.sync()
        self.timer.start()

    def poll(self):
        if not self.job.done:
            return
        self.timer.stop()
        callback, self.callback = self.callback, None
        operation = self.job.operation
        try:
            result = self.job.receive()
            self.busy = False
            self.sync()
            if callback:
                callback(result)
        except (WorkerError, SessionError, ValueError, KeyError, struct.error) as error:
            # Les diagnostics du worker sont déjà neutres ; pas de traceback ou chemin.
            self.busy = False
            if self.session:
                self.session.fail_generation(self.generation)
            self.generation = None
            self.preview_revision = None
            self.preview = False
            self.result_view.clear_page()
            self.result_label.setText("Après — aperçu indisponible, traitement refusé")
            self.sync()
            if operation == "export" and not isinstance(error, WorkerError):
                self.error("L'état de l'export est incertain : contrôlez la destination avant de recommencer. Aucun succès n'est annoncé.")
            elif operation == "generate":
                message = str(error) if isinstance(error, (WorkerError, SessionError)) else "Le traitement a échoué."
                self.result_label.setText("Après — " + message)
                self.result_label.setWordWrap(True)
                self.statusBar().showMessage(message)
            else:
                self.error(str(error) if isinstance(error, (WorkerError, SessionError)) else
                           "Le traitement a échoué ; aucun résultat n'est validé.")

    def cancel_work(self):
        self.preview_timer.stop()
        exporting = self.job.operation == "export"
        self.timer.stop()
        self.job.cancel()
        self.busy, self.callback = False, None
        if self.session:
            self.session.fail_generation(self.generation)
        self.generation = None
        if not self.session or self.session.result is None:
            self.preview = False
            self.preview_revision = None
            self.result_view.clear_page()
        self.sync()
        self.statusBar().showMessage("Export interrompu : contrôlez la destination, sa finalisation est incertaine."
                                    if exporting else "Traitement annulé")

    def discard_allowed(self):
        return not self.dirty or QMessageBox.question(
            self, "Modifications non exportées", "Abandonner les substitutions non exportées ?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard

    def choose_file(self):
        if not self.discard_allowed():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un PDF synthétique", "", "PDF (*.pdf)")
        if path:
            self.open_path(path)

    def open_path(self, path):
        self.submit("open", path=path, callback=lambda data: self.opened(data, path))

    def opened(self, data, path):
        self.session, self.source_path = Session(data), path
        self.pages, self.page, self.preview, self.dirty = [], 0, False, False
        self.visited.clear()
        self.view.clear_page()
        self.result_view.clear_page()
        self.source_pixmap = None
        self.preview_timer.stop()
        self.preview_revision = None
        self.scroll_position = (0, 0)
        self.zones.clear()
        self.submit("inspect", data, callback=self.inspected)

    def inspected(self, payload):
        self.pages = json.loads(payload)["pages"]
        self.render()

    def render(self):
        if not self.session or not self.pages or self.busy:
            return
        self.preview_revision = None
        self.scroll_position = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
        self.view.clear_page()
        self.result_view.clear_page()
        self.source_pixmap = None
        dpr = self.view.devicePixelRatioF()
        self.submit("render", self.session.source, page=self.page, scale=self.zoom * dpr,
                    callback=lambda payload: self.rendered(payload, dpr))

    def rendered(self, payload, dpr, result=False):
        width, height = struct.unpack_from(">II", payload)
        if len(payload) != 8 + width * height * 3:
            raise ValueError("Rendu invalide")
        image = QImage(payload[8:], width, height, width * 3, QImage.Format.Format_RGB888).copy()
        box = self.pages[self.page]["cropbox"]
        view = self.result_view if result else self.view
        view.configure(box[2] - box[0], box[3] - box[1], self.pages[self.page]["rotation"], self.zoom)
        horizontal, vertical = self.scroll_position
        zones = [(index, zone) for index, zone in enumerate(self.session.substitutions) if zone.page == self.page]
        pixmap = QPixmap.fromImage(image)
        view.set_page(pixmap, zones, not result, dpr)
        view.horizontalScrollBar().setValue(horizontal)
        view.verticalScrollBar().setValue(vertical)
        if result:
            self.preview = True
            self.preview_revision = self.session.revision
            self.visited.add(self.page)
            self.result_label.setText("Après — résultat réel à vérifier")
        else:
            self.source_pixmap = pixmap
            if self.session.result is not None:
                self.submit("render", self.session.result, page=self.page, scale=self.zoom * dpr,
                            callback=lambda data: self.rendered(data, dpr, result=True))
            elif not self.session.substitutions:
                self.result_view.configure(box[2] - box[0], box[3] - box[1], self.pages[self.page]["rotation"], self.zoom)
                self.result_view.set_page(pixmap, [], False, dpr)
                self.result_label.setText("Après — aucune substitution")
        self.sync()
        self.statusBar().showMessage("Résultat réel — à vérifier" if self.preview else "Original — zones d'édition, pas le résultat")

    def change_page(self, delta):
        if self.session and not self.busy and 0 <= self.page + delta < len(self.pages):
            self.page += delta
            self.render()

    def change_zoom(self, factor):
        if self.session and not self.busy:
            self.zoom = max(0.1, min(8, self.zoom * factor))
            self.render()

    def fit_page(self):
        if self.pages and not self.busy:
            box = self.pages[self.page]["cropbox"]
            width, height = box[2] - box[0], box[3] - box[1]
            if self.pages[self.page]["rotation"] in (90, 270):
                width, height = height, width
            self.zoom = max(0.1, min((self.view.viewport().width() - 12) / width,
                                     (self.view.viewport().height() - 12) / height))
            self.render()

    def changed(self, zones):
        selected = self.zones.currentRow()
        self.session.set_substitutions(zones)
        self.preview, self.preview_revision, self.dirty = False, None, True
        self.visited.clear()
        self.result_view.clear_page()
        self.result_label.setText("Après — calcul de l'aperçu…" if zones else "Après — dessinez une zone")
        with QSignalBlocker(self.zones):
            self.zones.clear()
            for zone in zones:
                self.zones.addItem(f"Page {zone.page + 1} — mode à déterminer — {zone.text or '(effacement)'}")
            self.zones.setCurrentRow(min(max(selected, 0), len(zones) - 1))
        if self.source_pixmap is not None:
            visible = [(index, zone) for index, zone in enumerate(zones) if zone.page == self.page]
            position = (self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value())
            self.view.set_page(self.source_pixmap, visible, True, self.view.devicePixelRatioF())
            self.view.horizontalScrollBar().setValue(position[0])
            self.view.verticalScrollBar().setValue(position[1])
            if not zones:
                self.result_view.set_page(self.source_pixmap, [], False, self.view.devicePixelRatioF())
        self.sync()
        self.preview_timer.start() if zones else self.preview_timer.stop()

    def automatic_preview(self):
        if self.busy:
            self.preview_timer.start()
        elif self.session and self.session.substitutions:
            self.generate()

    def add_rectangle(self, rect):
        try:
            zone = Substitution(self.page, rect, self.text.toPlainText())
            self.changed([*self.session.substitutions, zone])
            self.zones.setCurrentRow(len(self.session.substitutions) - 1)
        except SessionError as error:
            self.error(str(error))

    def move_rectangle(self, index, rect):
        if self.busy:
            return
        try:
            zones = list(self.session.substitutions)
            zones[index] = replace(zones[index], rectangle=rect)
            self.changed(zones)
        except SessionError as error:
            self.error(str(error))
            self.render()

    def select_zone(self, index):
        if self.session and 0 <= index < len(self.session.substitutions):
            zone = self.session.substitutions[index]
            with QSignalBlocker(self.text):
                self.text.setPlainText(zone.text)

    def go_to_zone(self):
        index = self.zones.currentRow()
        if self.session and 0 <= index < len(self.session.substitutions) and not self.busy:
            self.page = self.session.substitutions[index].page
            self.render()

    def update_text(self):
        index = self.zones.currentRow()
        if self.session and 0 <= index < len(self.session.substitutions) and not self.busy:
            try:
                zones = list(self.session.substitutions)
                zones[index] = replace(zones[index], text=self.text.toPlainText())
                self.changed(zones)
            except SessionError as error:
                self.error(str(error))

    def remove_zone(self):
        if not self.session or self.busy:
            return
        index = self.zones.currentRow()
        if index < 0:
            selected = [item.index for item in self.view.scene().selectedItems() if hasattr(item, "index")]
            index = selected[0] if selected else -1
        if 0 <= index < len(self.session.substitutions):
            self.changed([zone for n, zone in enumerate(self.session.substitutions) if n != index])

    def use_preset(self, index):
        if index:
            self.text.setPlainText("" if index == 5 else self.presets.itemText(index))

    def generate(self):
        self.preview_timer.stop()
        if not self.session or self.busy:
            return
        try:
            self.generation = self.session.begin_generation()
            self.dirty = True
            self.visited.clear()
            self.submit("generate", self.session.source, substitutions=self.session.substitutions,
                        revision=self.generation.revision, callback=self.generated)
        except (WorkerError, SessionError) as error:
            self.session.fail_generation(self.generation)
            self.generation = None
            self.error(str(error))

    def generated(self, data):
        size, = struct.unpack_from(">I", data)
        metadata = json.loads(data[4:4 + size])
        modes = metadata["modes"]
        if len(modes) != len(self.session.substitutions):
            raise ValueError("Modes incomplets")
        labels = {"native": "texte natif", "scan": "pixels", "ocr": "pixels + retrait OCR"}
        for index, (zone, mode) in enumerate(zip(self.session.substitutions, modes)):
            self.zones.item(index).setText(f"Page {zone.page + 1} — {labels[mode]} — {zone.text or '(effacement)'}")
        generation, self.generation = self.generation, None
        if self.session.accept_result(generation, data[4 + size:]):
            self.preview = True
            self.render()

    def confirm(self, checked):
        if checked:
            try:
                self.session.confirm()
            except SessionError as error:
                self.error(str(error))
        elif self.session:
            self.session.unconfirm()
        self.sync()

    def choose_export(self):
        if not self.session or self.busy:
            return
        try:
            data = self.session.confirmed_bytes()
            target, _ = QFileDialog.getSaveFileName(self, "Exporter une copie — dossier local non synchronisé",
                "substidude-export.pdf", "PDF (*.pdf)", options=QFileDialog.Option.DontConfirmOverwrite)
            if not target:
                return
            if (Path(target).resolve() == Path(self.source_path).resolve()
                    or (Path(target).exists() and os.path.samefile(target, self.source_path))):
                self.error("Le fichier source ou un de ses alias ne peut pas être remplacé.")
                return
            overwrite = Path(target).exists()
            if overwrite and QMessageBox.question(self, "Remplacer la destination ?",
                "Remplacer le fichier de destination existant par la copie vérifiée ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                return
            data = self.session.begin_export()
            self.dirty = True
            self.submit("export", data, path=target, source_path=self.source_path, overwrite=overwrite,
                        revision=self.session.revision, callback=lambda response: self.exported(response, data))
        except (WorkerError, SessionError, OSError):
            self.error("L'export n'est pas disponible ou le chemin est refusé.")

    def exported(self, response, data):
        if response != b"exported":
            raise ValueError("Réponse d'export invalide")
        self.session.mark_exported(data)
        self.dirty = False
        self.sync()
        self.statusBar().showMessage("Copie exportée — pas de garantie d'anonymisation exhaustive")

    def about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("À propos / Licences — hors ligne")
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        heading = QLabel("SubstiDude — version de développement, documents synthétiques uniquement.\n"
                         "Copyright (C) 2026 Girard Florian. AGPL-3.0-only ; aucune garantie.\n"
                         "Sources : https://github.com/Fl0-dev/SubstiDude\n"
                         "Paquet non publié : les sources exactes et notices de distribution restent à qualifier.")
        heading.setWordWrap(True)
        heading.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(heading)
        tabs = QTabWidget()
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            text = QTextEdit()
            text.setReadOnly(True)
            try:
                text.setPlainText((root / filename).read_text(encoding="utf-8"))
            except OSError:
                text.setPlainText("Texte absent du paquet ; distribution non qualifiée.")
            tabs.addTab(text, filename)
        layout.addWidget(tabs)
        close = QPushButton("Fermer")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def closeEvent(self, event):
        if not self.discard_allowed():
            event.ignore()
            return
        if self.job.operation == "export":
            QMessageBox.warning(self, "Export interrompu", "La destination peut déjà avoir été finalisée. Contrôlez-la avant de recommencer ; aucun succès n'est annoncé.")
        self.cancel_work()
        event.accept()
