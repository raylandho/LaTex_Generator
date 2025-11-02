from __future__ import annotations
import os, re
from PySide6.QtCore import Qt, QPointF, QRegularExpression, QLineF
from PySide6.QtGui import QPixmap, QTextCursor, QFont, QTextCharFormat, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsPixmapItem, QGraphicsItem, QGraphicsTextItem, QApplication,
    QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem
)

from constants import GRID_SIZE, GREEK_MAP


# ---------- Utilities ----------
def snap_to_grid(p: QPointF, grid: int = GRID_SIZE) -> QPointF:
    return QPointF(round(p.x() / grid) * grid, round(p.y() / grid) * grid)


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


# ---------- Items ----------
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


# ---- Greek helper (case-flexible) ----
def _greek_from_token(name: str):
    """Return Greek symbol matching '/word' or '\\word' in a case-flexible way."""
    return (GREEK_MAP.get(name)
            or GREEK_MAP.get(name.capitalize())
            or GREEK_MAP.get(name.lower()))


class LabelItem(QGraphicsTextItem):
    """
    Editable text label with:
      - Slash Greek shortcuts: '/alpha' or '\\Delta' → α / Δ (case-flexible)
      - Bold/Italic toggles: Ctrl+B / Ctrl+I (selection or caret)
      - Grid snapping when not editing
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
        # Default font
        self.setFont(QFont("Times New Roman", 20))

    # ---------- External shortcuts support (called by the view) ----------
    def _ensure_edit_mode(self, place: str = "end"):
        """Enter edit mode and place caret so formatting applies to future typing."""
        if self.textInteractionFlags() != Qt.TextEditorInteraction:
            self.setTextInteractionFlags(Qt.TextEditorInteraction)
            self.setFocus(Qt.ShortcutFocusReason)
        cur = self.textCursor()
        if place == "end":
            cur.movePosition(QTextCursor.End)
        self.setTextCursor(cur)

    def handle_ctrl_format_shortcut(self, key: int):
        """Allow Ctrl+B / Ctrl+I to apply even before typing starts."""
        self._ensure_edit_mode(place="end")
        if key == Qt.Key_B:
            self._toggle_bold()
        elif key == Qt.Key_I:
            self._toggle_italic()

    # ---------- Editing lifecycle ----------
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
        # Expand anywhere in the text when leaving edit mode (preserving formatting)
        self._expand_all_slash_tokens_preserve_format()
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        super().focusOutEvent(event)

    # ---------- Key handling: Enter/Esc, Bold/Italic, Greek expansion ----------
    def keyPressEvent(self, event):
        # Commit & expand on Enter; cancel on Esc
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._expand_all_slash_tokens_preserve_format()
            self.clearFocus()  # triggers focusOutEvent
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.clearFocus()
            event.accept()
            return

        # Formatting shortcuts (work while editing)
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_B:
                self._toggle_bold()
                event.accept(); return
            if event.key() == Qt.Key_I:
                self._toggle_italic()
                event.accept(); return

        # Let base class insert the key first (so our expansion sees it)
        super().keyPressEvent(event)

        # After insertion, expand the nearest token at word boundaries
        if event.key() in {
            Qt.Key_Space, Qt.Key_Tab, Qt.Key_Comma,
            Qt.Key_Semicolon, Qt.Key_Period, Qt.Key_Colon
        }:
            self._expand_last_slash_token_near_caret()

    # ---------- Bold/Italic toggles ----------
    def _toggle_bold(self):
        cur = self.textCursor()
        fmt = cur.charFormat()
        new = QTextCharFormat(fmt)
        is_bold = fmt.fontWeight() >= QFont.Bold
        new.setFontWeight(QFont.Normal if is_bold else QFont.Bold)
        self._merge_format_on_selection_or_word(cur, new)

    def _toggle_italic(self):
        cur = self.textCursor()
        fmt = cur.charFormat()
        new = QTextCharFormat(fmt)
        new.setFontItalic(not fmt.fontItalic())
        self._merge_format_on_selection_or_word(cur, new)

    def _merge_format_on_selection_or_word(self, cur: QTextCursor, fmt: QTextCharFormat):
        """
        Apply formatting to current selection; if no selection, apply to the
        current typing point (so it affects text you type next).
        """
        cur.mergeCharFormat(fmt)  # selection or caret format
        # Ensure editor uses this updated cursor going forward
        self.setTextCursor(cur)

    # ---------- Greek expansion (preserve formatting) ----------
    def _expand_last_slash_token_near_caret(self):
        """
        Find the closest '/word' or '\\word' within ~64 chars before the caret and replace it,
        preserving the surrounding formatting.
        """
        caret = self.textCursor().position()
        start = max(0, caret - 64)

        scan = QTextCursor(self.document())
        scan.setPosition(start)
        scan.setPosition(caret, QTextCursor.KeepAnchor)
        segment = scan.selectedText()

        # Find the last token in the scanned segment
        py_rx = re.compile(r'(?:/|\\)([A-Za-z]+)')
        last = None
        for m in py_rx.finditer(segment):
            last = m
        if not last:
            return

        name = last.group(1)
        symbol = _greek_from_token(name)
        if not symbol:
            return

        token_start = start + last.start(0)
        token_end   = start + last.end(0)

        # Replace exactly that span; new text inherits current char format at start
        repl = QTextCursor(self.document())
        repl.setPosition(token_start)
        repl.setPosition(token_end, QTextCursor.KeepAnchor)
        repl.insertText(symbol)

    def _expand_all_slash_tokens_preserve_format(self):
        """
        Replace all '/word' or '\\word' tokens across the document with Greek symbols,
        preserving formatting by replacing each token in-place with QTextCursor.
        """
        doc = self.document()
        qrx = QRegularExpression(r"(?:/|\\)([A-Za-z]+)")
        pos = 0
        while True:
            c = doc.find(qrx, pos)
            if c.isNull():
                break
            token = c.selectedText()  # e.g. '/Alpha'
            m = re.match(r'(?:/|\\)([A-Za-z]+)$', token)
            if m:
                sym = _greek_from_token(m.group(1))
                if sym:
                    c.insertText(sym)
                    pos = c.position()  # continue after inserted symbol
                    continue
            # No replacement; move past this match
            pos = c.selectionEnd()

    # ---------- Movement / snapping ----------
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Only snap when not actively editing
            if self.textInteractionFlags() != Qt.TextEditorInteraction:
                if not (QApplication.keyboardModifiers() & Qt.AltModifier):
                    return snap_to_grid(value)
        return super().itemChange(change, value)


class LineItem(QGraphicsLineItem):
    """Selectable/movable straight line with cosmetic pen and grid snapping."""
    def __init__(self, p1: QPointF, p2: QPointF, color=Qt.black, width: float = 2.0):
        super().__init__(QLineF(p1, p2))
        # Explicitly non-selectable & non-movable
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)

        pen = QPen(color, width)
        pen.setCosmetic(True)  # constant on-screen width
        self.setPen(pen)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Snap whole line when moving (Alt to bypass)
            if not (QApplication.keyboardModifiers() & Qt.AltModifier):
                return snap_to_grid(value)
        return super().itemChange(change, value)

class RectItem(QGraphicsRectItem):
    """Movable/selectable rectangle with cosmetic outline and grid snapping."""
    def __init__(self, w: float = 120.0, h: float = 80.0, outline=Qt.black, fill=None, width: float = 2.0):
        super().__init__(-w/2, -h/2, w, h)  # centered rect
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        pen = QPen(outline, width)
        pen.setCosmetic(True)
        self.setPen(pen)
        if fill is None:
            self.setBrush(Qt.NoBrush)
        else:
            self.setBrush(QBrush(fill))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            if not (QApplication.keyboardModifiers() & Qt.AltModifier):
                return snap_to_grid(value)
        return super().itemChange(change, value)


class EllipseItem(QGraphicsEllipseItem):
    """Movable/selectable ellipse with cosmetic outline and grid snapping."""
    def __init__(self, w: float = 120.0, h: float = 80.0, outline=Qt.black, fill=None, width: float = 2.0):
        super().__init__(-w/2, -h/2, w, h)  # centered ellipse
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        pen = QPen(outline, width)
        pen.setCosmetic(True)
        self.setPen(pen)
        if fill is None:
            self.setBrush(Qt.NoBrush)
        else:
            self.setBrush(QBrush(fill))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            if not (QApplication.keyboardModifiers() & Qt.AltModifier):
                return snap_to_grid(value)
        return super().itemChange(change, value)
    
class ArcItem(QGraphicsPathItem):
    """
    Circle-arc item defined by center, radius, start angle, and sweep.
    Cosmetic pen so it stays 2px on-screen regardless of zoom.
    Angles are in degrees, 0 at +X (3 o'clock), CCW positive.
    """
    def __init__(self, center: QPointF, radius: float, start_deg: float, sweep_deg: float,
                 color=Qt.black, width: float = 2.0):
        super().__init__()
        pen = QPen(color, width)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.update_arc(center, radius, start_deg, sweep_deg)

    def update_arc(self, center: QPointF, radius: float, start_deg: float, sweep_deg: float):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainterPath

        if radius <= 0.0:
            self.setPath(QPainterPath())
            return

        rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)

        # Our start_deg/sweep_deg are CCW; Qt expects clockwise angles.
        start_deg_qt = -start_deg
        sweep_deg_qt = -sweep_deg

        path = QPainterPath()
        path.arcMoveTo(rect, start_deg_qt)
        path.arcTo(rect, start_deg_qt, sweep_deg_qt)
        self.setPath(path)
