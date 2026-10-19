# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Girard Florian

"""Vue Qt : pixels affichés et rectangles canoniques, sans import PDF."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPen, QTransform
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsView


def page_transform(width, height, rotation, zoom):
    if rotation == 90:
        return QTransform(0, zoom, -zoom, 0, height * zoom, 0)
    if rotation == 180:
        return QTransform(-zoom, 0, 0, -zoom, width * zoom, height * zoom)
    if rotation == 270:
        return QTransform(0, -zoom, zoom, 0, 0, width * zoom)
    return QTransform(zoom, 0, 0, zoom, 0, 0)


class ZoneItem(QGraphicsRectItem):
    def __init__(self, index, rect, callback):
        super().__init__(rect)
        self.index, self.callback, self.resizing = index, callback, False
        self.setFlags(self.GraphicsItemFlag.ItemIsMovable | self.GraphicsItemFlag.ItemIsSelectable)
        self.setPen(QPen(QColor("#005ab5"), 2))
        self.setBrush(QColor(0, 90, 181, 35))
        self.setToolTip("Zone d'édition : déplacer ; coin inférieur droit pour redimensionner. Suppr pour retirer.")

    def mousePressEvent(self, event):
        self.resizing = (event.pos() - self.rect().bottomRight()).manhattanLength() < 12
        if self.resizing:
            self.setSelected(True)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing:
            rect = QRectF(self.rect().topLeft(), event.pos()).normalized()
            if rect.width() >= 2 and rect.height() >= 2:
                self.setRect(rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.resizing:
            super().mouseReleaseEvent(event)
        self.resizing = False
        self.callback(self.index, self.mapRectToScene(self.rect()))


class PageView(QGraphicsView):
    rectangleCreated = Signal(tuple)
    rectangleChanged = Signal(int, tuple)
    rectangleSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.scene().selectionChanged.connect(self.selected_rectangle)
        self.setAccessibleName("Page PDF et zones de substitution")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.width_points = self.height_points = 0
        self.matrix = QTransform()
        self.editable = False
        self.start_point = self.draft = None

    def selected_rectangle(self):
        selected = [item for item in self.scene().selectedItems() if isinstance(item, ZoneItem)]
        if selected:
            self.rectangleSelected.emit(selected[0].index)

    def configure(self, width, height, rotation, zoom):
        self.width_points, self.height_points = width, height
        self.matrix = page_transform(width, height, rotation, zoom)

    def canonical_rectangle(self, start, end):
        inverse, valid = self.matrix.inverted()
        if not valid:
            return ()
        rect = inverse.mapRect(QRectF(start, end).normalized())
        box = rect.intersected(QRectF(0, 0, self.width_points, self.height_points))
        values = tuple(round(value * 2) / 2 for value in (box.left(), box.top(), box.right(), box.bottom()))
        return values if values[2] > values[0] and values[3] > values[1] else ()

    def set_page(self, pixmap, zones, editable, dpr=1):
        self.scene().clear()
        self.draft = None
        image = self.scene().addPixmap(pixmap)
        image.setScale(1 / dpr)
        self.scene().setSceneRect(image.sceneBoundingRect())
        self.editable = editable
        if editable:
            for index, zone in zones:
                x0, y0, x1, y1 = zone.rectangle
                rect = self.matrix.mapRect(QRectF(x0, y0, x1 - x0, y1 - y0))
                self.scene().addItem(ZoneItem(index, rect, self.changed_rectangle))

    def clear_page(self):
        self.scene().clear()
        self.scene().setSceneRect(QRectF())
        self.editable = False
        self.draft = self.start_point = None

    def changed_rectangle(self, index, rectangle):
        rect = self.canonical_rectangle(rectangle.topLeft(), rectangle.bottomRight())
        if rect:
            # Laisser Qt terminer l'événement avant que le nouveau rendu
            # détruise/recrée les items de la scène.
            QTimer.singleShot(0, lambda: self.rectangleChanged.emit(index, rect))

    def mousePressEvent(self, event):
        if self.editable and event.button() == Qt.MouseButton.LeftButton and not isinstance(self.itemAt(event.position().toPoint()), ZoneItem):
            self.start_point = self.mapToScene(event.position().toPoint())
            self.draft = self.scene().addRect(QRectF(self.start_point, self.start_point), QPen(QColor("#005ab5"), 2))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.draft is not None:
            self.draft.setRect(QRectF(self.start_point, self.mapToScene(event.position().toPoint())).normalized())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.draft is not None:
            rect = self.canonical_rectangle(self.start_point, self.mapToScene(event.position().toPoint()))
            self.scene().removeItem(self.draft)
            self.draft = None
            if rect:
                self.rectangleCreated.emit(rect)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
