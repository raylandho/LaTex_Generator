from __future__ import annotations
import os
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsItem, QGraphicsTextItem, QApplication
)

from constants import GRID_SIZE


def snap_to_grid(p: QPointF, grid: int = GRID_SIZE) -> QPointF:
    return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)


class PixmapItem(QGraphicsPixmapItem):
    """Movable/selectable pixmap with grid snapping."""
    def __init__(self, pix: QPixmap):
        super().__init__(pix)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setTransformationMode(Qt.SmoothTransformation)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Snap to grid unless Alt is held
            if not (QApplication.keyboardModifiers() & Qt.AltModifier):
                return snap_to_grid(value)
        return super().itemChange(change, value)


class LabelItem(QGraphicsTextItem):
    """Simple editable text label."""
    def __init__(self, text: str = "m"):
        super().__init__(text)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setDefaultTextColor(Qt.black)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Snap to grid unless Alt is held
            if not (QApplication.keyboardModifiers() & Qt.AltModifier):
                return snap_to_grid(value)
        return super().itemChange(change, value)


def load_pixmap_for(name: str, assets_dir: str) -> QPixmap:
    path = os.path.join(assets_dir, name)
    pix = QPixmap(path)
    if pix.isNull():
        # Graceful fallback: 64×64 checker if missing
        from PySide6.QtGui import QImage, QColor
        img = QImage(64, 64, QImage.Format_ARGB32)
        img.fill(QColor("#f0f0f0"))
        pix = QPixmap.fromImage(img)
    return pix
