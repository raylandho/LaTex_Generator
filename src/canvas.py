from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from constants import GRID_SIZE, ASSET_MAP  # SCENE_BOUNDS unused for infinite board
from items import PixmapItem, LabelItem, load_pixmap_for
from palette import MIME_TYPE

# Infinite-ish bounds; we only paint the visible part of the grid
HUGE_BOUNDS = QRectF(-1_000_000.0, -1_000_000.0, 2_000_000.0, 2_000_000.0)


class WhiteboardScene(QGraphicsScene):
    def __init__(self):
        super().__init__(HUGE_BOUNDS)
        self.setBackgroundBrush(Qt.white)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        # Crisp grid in exposed rect only
        grid_pen = QPen(QColor(235, 235, 235))
        grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)

        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top  = int(rect.top())  - (int(rect.top())  % GRID_SIZE)

        x = float(left)
        while x < rect.right():
            painter.drawLine(x + 0.5, rect.top(), x + 0.5, rect.bottom())
            x += GRID_SIZE

        y = float(top)
        while y < rect.bottom():
            painter.drawLine(rect.left(), y + 0.5, rect.right(), y + 0.5)
            y += GRID_SIZE

        # axes
        axis_pen = QPen(QColor(210, 210, 210))
        axis_pen.setCosmetic(True)
        axis_pen.setWidth(2)
        painter.setPen(axis_pen)
        painter.drawLine(rect.left(), 0.5, rect.right(), 0.5)   # X axis
        painter.drawLine(0.5, rect.top(), 0.5, rect.bottom())   # Y axis


class WhiteboardView(QGraphicsView):
    def __init__(self, scene: WhiteboardScene, assets_dir: str):
        super().__init__(scene)
        self.assets_dir = assets_dir

        # Quality & feel
        self.setRenderHints(QPainter.Antialiasing |
                            QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheNone)

        # Natural zoom/pan
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self._panning = False
        self._last = None
        self._space_down = False

        # IMPORTANT: let the view receive key events (for Space-to-pan, Ctrl+0, etc.)
        self.setFocusPolicy(Qt.StrongFocus)

        # Scrollbars if you drift far
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # If you’re using the handle overlay:
        self._overlay = None
        try:
            self.scene().selectionChanged.connect(self._on_selection_changed)
        except Exception:
            pass

    # ----- selection overlay hooks (safe no-ops if handles.py not present) -----
    def _on_selection_changed(self):
        if self._overlay is None:
            return
        sel = [it for it in self.scene().selectedItems()]
        if len(sel) == 1:
            self._ensure_overlay(sel[0])
        else:
            self._drop_overlay()

    def _ensure_overlay(self, target):
        try:
            from handles import TransformOverlay
        except Exception:
            return
        if self._overlay and getattr(self._overlay, "target", None) is target:
            self._overlay.update_from_target(); return
        self._drop_overlay()
        self._overlay = TransformOverlay(target)
        self.scene().addItem(self._overlay)
        if hasattr(self._overlay, "attach"):
            self._overlay.attach()
        self._overlay.update_from_target()

    def _drop_overlay(self):
        if self._overlay:
            self.scene().removeItem(self._overlay)
            self._overlay = None

    # ----------------- Zoom / Resize / Rotate selection --------------------
    def wheelEvent(self, e):
        # Alt + Wheel => rotate selection
        if (e.modifiers() & Qt.AltModifier) and self.scene().selectedItems():
            if hasattr(self.window(), "_rotate_selected"):
                steps = e.angleDelta().y() / 120.0
                self.window()._rotate_selected(steps * 10.0)
            if self._overlay: self._overlay.update_from_target()
            self.viewport().update(); e.accept(); return

        # Shift + Wheel => uniform rescale selection
        if (e.modifiers() & Qt.ShiftModifier) and self.scene().selectedItems():
            if hasattr(self.window(), "_scale_selected"):
                delta = e.angleDelta().y() / 240.0
                self.window()._scale_selected(1.0 + 0.2 * delta)
            if self._overlay: self._overlay.update_from_target()
            self.viewport().update(); e.accept(); return

        # DEFAULT: Wheel zooms view (no modifier needed)
        delta = e.angleDelta().y() / 240.0
        factor = 1.0 + 0.2 * delta
        self.scale(factor, factor)
        self.viewport().update(); e.accept(); return

    # ------------------------ Space-to-pan & resets ------------------------
    def keyPressEvent(self, e):
        if self.scene().focusItem() is not None:
            super().keyPressEvent(e); return
        if e.key() == Qt.Key_Space:
            self._space_down = True; e.accept(); return
        # Ctrl+0 => reset view to origin @ 100%
        if (e.modifiers() & Qt.ControlModifier) and e.key() == Qt.Key_0:
            self.resetTransform()
            self.centerOn(0, 0)
            e.accept(); return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.scene().focusItem() is not None:
            super().keyReleaseEvent(e); return
        if e.key() == Qt.Key_Space:
            self._space_down = False; e.accept(); return
        super().keyReleaseEvent(e)

    # ------------------ Pan: Right/Middle drag, or Space+Left --------------
    def mousePressEvent(self, e):
        if (e.button() == Qt.MiddleButton or
            e.button() == Qt.RightButton or
            (e.button() == Qt.LeftButton and self._space_down)):
            self._panning = True
            self._last = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._panning and self._last is not None:
            d = e.position() - self._last
            self._last = e.position()
            self.translate(-d.x(), -d.y())
            e.accept(); return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._panning and (e.button() in (Qt.MiddleButton, Qt.RightButton, Qt.LeftButton)):
            self._panning = False
            self._last = None
            self.setCursor(Qt.ArrowCursor)
            e.accept(); return
        super().mouseReleaseEvent(e)

    # ----------------------- Drag & drop -----------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_TYPE):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_TYPE):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME_TYPE):
            label = bytes(e.mimeData().data(MIME_TYPE)).decode("utf-8")
            if label == "Text":
                item = LabelItem("m")
            else:
                filename = ASSET_MAP.get(label)
                pix = load_pixmap_for(filename, self.assets_dir)
                item = PixmapItem(pix)
                br = item.boundingRect()
                item.setOffset(-br.width()/2, -br.height()/2)
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setPos(self.mapToScene(e.position().toPoint()))
            self.scene().addItem(item)
            item.setSelected(True)
            self._ensure_overlay(item)
            e.acceptProposedAction(); return
        super().dropEvent(e)
