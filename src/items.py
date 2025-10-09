from __future__ import annotations
import os
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPixmap, QTextCursor
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
    """Editable text label: double-click to edit; Enter/Esc to finish."""
    def __init__(self, text: str = "m"):
        super().__init__(text)
        self.setDefaultTextColor(Qt.black)
        # Start NOT editing; allow selection & moving
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemIsFocusable
        )

    def mouseDoubleClickEvent(self, event):
        # Enter edit mode
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        # Select all text for quick overwrite
        cursor = self.textCursor()
        try:
            cursor.select(QTextCursor.Document)  # correct usage
        except Exception:
            # Fallback for older bindings: use enum namespace
            cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        # Leave edit mode
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
            self.clearFocus()  # commits text and triggers focusOutEvent
            event.accept()
            return
        super().keyPressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Only snap when not actively editing
            if self.textInteractionFlags() != Qt.TextEditorInteraction:
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
