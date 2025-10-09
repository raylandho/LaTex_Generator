from __future__ import annotations
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from constants import GRID_SIZE, SCENE_BOUNDS, ASSET_MAP
from items import PixmapItem, LabelItem, load_pixmap_for
from palette import MIME_TYPE


class WhiteboardScene(QGraphicsScene):
    def __init__(self):
        super().__init__(SCENE_BOUNDS)
        self.setBackgroundBrush(Qt.white)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        # grid (1px cosmetic lines aligned to pixel centers to avoid blur/ghosts)
        grid_pen = QPen(QColor(235, 235, 235))
        grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)

        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)

        # draw verticals at x + 0.5, horizontals at y + 0.5 for crisp lines
        x = left
        while x < rect.right():
            painter.drawLine(x + 0.5, rect.top(), x + 0.5, rect.bottom())
            x += GRID_SIZE
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y + 0.5, rect.right(), y + 0.5)
            y += GRID_SIZE

        # axes (also cosmetic, 2px)
        axis_pen = QPen(QColor(210, 210, 210))
        axis_pen.setCosmetic(True)
        axis_pen.setWidth(2)
        painter.setPen(axis_pen)
        painter.drawLine(rect.left(), 0 + 0.5, rect.right(), 0 + 0.5)
        painter.drawLine(0 + 0.5, rect.top(), 0 + 0.5, rect.bottom())


class WhiteboardView(QGraphicsView):
    def __init__(self, scene: WhiteboardScene, assets_dir: str):
        super().__init__(scene)
        self.assets_dir = assets_dir

        # Better rendering + fewer artifacts when scaling pixmaps
        self.setRenderHints(QPainter.Antialiasing |
                            QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)

        # Force full repaints to avoid stale pixels when scaling/moving
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        # Disable view caching; let Qt repaint everything cleanly
        self.setCacheMode(QGraphicsView.CacheNone)

        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self._panning = False
        self._last = None
        self._space_down = False  # track Space key

    # Zoom / Resize selection ------------------------------------------------
    def wheelEvent(self, e):
        # Shift+Wheel => scale selected items; Ctrl+Wheel => zoom view
        if (e.modifiers() & Qt.ShiftModifier) and self.scene().selectedItems():
            delta = e.angleDelta().y() / 240.0
            factor = 1.0 + 0.2 * delta
            if hasattr(self.window(), "_scale_selected"):
                self.window()._scale_selected(factor)
            # ensure the whole view repaints (prevents "border line" trails)
            self.viewport().update()
            e.accept(); return

        if e.modifiers() & Qt.ControlModifier:
            delta = e.angleDelta().y() / 240.0
            factor = 1.0 + 0.2 * delta
            old = self.mapToScene(e.position().toPoint())
            self.scale(factor, factor)
            new = self.mapToScene(e.position().toPoint())
            d = new - old
            self.translate(d.x(), d.y())
            self.viewport().update()
            e.accept()
        else:
            super().wheelEvent(e)

    # Track Space key for panning -------------------------------------------
    def keyPressEvent(self, e):
        # If an item (e.g., LabelItem) is editing, let it handle keys
        if self.scene().focusItem() is not None:
            super().keyPressEvent(e); return

        if e.key() == Qt.Key_Space:
            self._space_down = True
            e.accept(); return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        # If an item is editing, let it handle keys
        if self.scene().focusItem() is not None:
            super().keyReleaseEvent(e); return

        if e.key() == Qt.Key_Space:
            self._space_down = False
            e.accept(); return
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
                # center-anchor the pixmap for nicer snapping
                br = item.boundingRect()
                item.setOffset(-br.width() / 2, -br.height() / 2)
            item.setPos(self.mapToScene(e.position().toPoint()))
            self.scene().addItem(item)
            e.acceptProposedAction(); return
        super().dropEvent(e)
