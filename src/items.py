from __future__ import annotations
import os
from PySide6.QtCore import Qt, QPointF, QRegularExpression
from PySide6.QtGui import QPixmap, QTextCursor, QFont
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsItem, QGraphicsTextItem, QApplication
)

from constants import GRID_SIZE, GREEK_MAP


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
    """
    Editable text label with slash Greek shortcuts.
    Type '/alpha' or '\\Delta' then press Space/Tab/Enter (or click away) to expand.
    """
    def __init__(self, text: str = "m"):
        super().__init__(text)
        self.setDefaultTextColor(Qt.black)
        self.setTextInteractionFlags(Qt.NoTextInteraction)  # start not editing
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
            | QGraphicsItem.ItemIsFocusable
        )
        # Sensible default font
        self.setFont(QFont("Times New Roman", 20))

    # ----- Editing lifecycle -----
    def mouseDoubleClickEvent(self, event):
        # Enter edit mode
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        # Select all for quick overwrite
        cursor = self.textCursor()
        try:
            cursor.select(QTextCursor.Document)
        except Exception:
            cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        # Expand anywhere in the text when leaving edit mode
        self._expand_slash_tokens(expand_all=True)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        # Commit & expand on Enter; cancel on Esc
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._expand_slash_tokens(expand_all=True)
            self.clearFocus()  # triggers focusOutEvent
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            event.accept()
            return

        # Let base class insert the key first
        super().keyPressEvent(event)

        # Expand nearest token at word boundaries
        if event.key() in {
            Qt.Key_Space, Qt.Key_Tab, Qt.Key_Comma,
            Qt.Key_Semicolon, Qt.Key_Period, Qt.Key_Colon
        }:
            self._expand_slash_tokens(expand_all=False)

    # ----- Greek expansion -----
    def _expand_slash_tokens(self, expand_all: bool):
        """
        Replace '/word' or '\\word' with Greek if known.
        If expand_all=True: process whole document; else: last token near caret.
        """
        if expand_all:
            cur = QTextCursor(self.document())
            cur.select(QTextCursor.Document)
            text = cur.selectedText()
            new_text = self._replace_all_tokens(text)
            if new_text != text:
                cur.insertText(new_text)
            return

        # Local scan near caret (~64 chars back)
        caret = self.textCursor().position()
        start = max(0, caret - 64)

        scan = QTextCursor(self.document())
        scan.setPosition(start)
        scan.setPosition(caret, QTextCursor.KeepAnchor)
        segment = scan.selectedText()

        rx = QRegularExpression(r"(?:/|\\)([A-Za-z]+)")
        it = rx.globalMatch(segment)

        last = None
        while it.hasNext():
            last = it.next()
        if not last:
            return

        name = last.captured(1)
        symbol = GREEK_MAP.get(name)
        if not symbol:
            return

        token_start = start + last.capturedStart(0)
        token_end   = start + last.capturedEnd(0)

        repl = QTextCursor(self.document())
        repl.setPosition(token_start)
        repl.setPosition(token_end, QTextCursor.KeepAnchor)
        repl.insertText(symbol)

    @staticmethod
    def _replace_all_tokens(text: str) -> str:
        rx = QRegularExpression(r"(?:/|\\)([A-Za-z]+)")
        it = rx.globalMatch(text)

        out = []
        last_i = 0
        while it.hasNext():
            m = it.next()
            name = m.captured(1)
            out.append(text[last_i:m.capturedStart(0)])
            out.append(GREEK_MAP.get(name, text[m.capturedStart(0):m.capturedEnd(0)]))
            last_i = m.capturedEnd(0)
        out.append(text[last_i:])
        return "".join(out)

    # ----- Movement -----
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
