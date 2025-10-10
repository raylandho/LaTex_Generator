from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from constants import GRID_SIZE, SCENE_BOUNDS, ASSET_MAP
from items import PixmapItem, LabelItem, load_pixmap_for
from palette import MIME_TYPE
from handles import TransformOverlay, apply_transform  # NEW


class WhiteboardScene(QGraphicsScene):
    def __init__(self):
        super().__init__(SCENE_BOUNDS)
        self.setBackgroundBrush(Qt.white)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)
        grid_pen = QPen(QColor(235, 235, 235)); grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)

        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)
        x = left
        while x < rect.right():
            painter.drawLine(x + 0.5, rect.top(), x + 0.5, rect.bottom()); x += GRID_SIZE
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y + 0.5, rect.right(), y + 0.5); y += GRID_SIZE

        axis_pen = QPen(QColor(210, 210, 210)); axis_pen.setCosmetic(True); axis_pen.setWidth(2)
        painter.setPen(axis_pen)
        painter.drawLine(rect.left(), 0 + 0.5, rect.right(), 0 + 0.5)
        painter.drawLine(0 + 0.5, rect.top(), 0 + 0.5, rect.bottom())


class WhiteboardView(QGraphicsView):
    def __init__(self, scene: WhiteboardScene, assets_dir: str):
        super().__init__(scene)
        self.assets_dir = assets_dir

        self.setRenderHints(QPainter.Antialiasing |
                            QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheNone)

        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self._panning = False
        self._last = None
        self._space_down = False

        # --- overlay lifecycle tied to selection ---
        self._overlay: TransformOverlay | None = None
        self.scene().selectionChanged.connect(self._on_selection_changed)

    # Keep overlay in sync with selection
    def _on_selection_changed(self):
        sel = [it for it in self.scene().selectedItems()]
        # Only show for a single item
        if len(sel) == 1:
            self._ensure_overlay(sel[0])
        else:
            self._drop_overlay()

    def _ensure_overlay(self, target):
        if self._overlay and self._overlay.target is target:
            self._overlay.update_from_target()
            return
        self._drop_overlay()
        self._overlay = TransformOverlay(target)
        self.scene().addItem(self._overlay)
        self._overlay.attach()            # <-- attach AFTER both share the same scene
        self._overlay.update_from_target()

    def _drop_overlay(self):
        if self._overlay:
            self.scene().removeItem(self._overlay)
            self._overlay = None

    # Zoom / Resize / Rotate selection --------------------------------------
    def wheelEvent(self, e):
        if (e.modifiers() & Qt.AltModifier) and self.scene().selectedItems():
            steps = e.angleDelta().y() / 120.0
            if hasattr(self.window(), "_rotate_selected"):
                self.window()._rotate_selected(steps * 10.0)
            if self._overlay:
                self._overlay.update_from_target()
            self.viewport().update(); e.accept(); return

        if (e.modifiers() & Qt.ShiftModifier) and self.scene().selectedItems():
            delta = e.angleDelta().y() / 240.0
            factor = 1.0 + 0.2 * delta
            if hasattr(self.window(), "_scale_selected"):
                self.window()._scale_selected(factor)
            if self._overlay:
                self._overlay.update_from_target()
            self.viewport().update(); e.accept(); return

        if e.modifiers() & Qt.ControlModifier:
            delta = e.angleDelta().y() / 240.0
            factor = 1.0 + 0.2 * delta
            old = self.mapToScene(e.position().toPoint())
            self.scale(factor, factor)
            new = self.mapToScene(e.position().toPoint())
            d = new - old
            self.translate(d.x(), d.y())
            self.viewport().update(); e.accept(); return

        super().wheelEvent(e)

    # Track Space key for panning -------------------------------------------
    def keyPressEvent(self, e):
        if self.scene().focusItem() is not None:
            super().keyPressEvent(e); return
        if e.key() == Qt.Key_Space:
            self._space_down = True; e.accept(); return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.scene().focusItem() is not None:
            super().keyReleaseEvent(e); return
        if e.key() == Qt.Key_Space:
            self._space_down = False; e.accept(); return
        super().keyReleaseEvent(e)

    # Mouse pan when Space held or middle button ----------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self._space_down):
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
        if self._panning and (e.button() in (Qt.MiddleButton, Qt.LeftButton)):
            self._panning = False
            self._last = None
            self.setCursor(Qt.ArrowCursor)
            e.accept(); return
        super().mouseReleaseEvent(e)

    # Drag & drop from palette ----------------------------------------------
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
                item.setOffset(-br.width() / 2, -br.height() / 2)
            # Always set transform origin to center for intuitive transforms
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setPos(self.mapToScene(e.position().toPoint()))
            self.scene().addItem(item)
            # show overlay for the newly added item
            item.setSelected(True)
            self._ensure_overlay(item)
            e.acceptProposedAction(); return
        super().dropEvent(e)
