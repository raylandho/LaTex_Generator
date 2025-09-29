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
        # grid
        pen = QPen(QColor(235, 235, 235))
        pen.setCosmetic(True)
        painter.setPen(pen)
        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += GRID_SIZE
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += GRID_SIZE
        # axes
        axis = QPen(QColor(210, 210, 210))
        axis.setCosmetic(True)
        axis.setWidth(2)
        painter.setPen(axis)
        painter.drawLine(rect.left(), 0, rect.right(), 0)
        painter.drawLine(0, rect.top(), 0, rect.bottom())


class WhiteboardView(QGraphicsView):
    def __init__(self, scene: WhiteboardScene, assets_dir: str):
        super().__init__(scene)
        self.assets_dir = assets_dir
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self._panning = False
        self._last = None
        self._space_down = False  # track Space key

    # Zoom (Ctrl+wheel) -----------------------------------------------------
    def wheelEvent(self, e):
        if Qt.ControlModifier & e.modifiers():
            delta = e.angleDelta().y() / 240.0
            factor = 1.0 + 0.2 * delta
            old = self.mapToScene(e.position().toPoint())
            self.scale(factor, factor)
            new = self.mapToScene(e.position().toPoint())
            d = new - old
            self.translate(d.x(), d.y())
            e.accept()
        else:
            super().wheelEvent(e)

    # Track Space key for panning -------------------------------------------
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            self._space_down = True
            e.accept(); return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
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
                item.setOffset(-br.width()/2, -br.height()/2)
            item.setPos(self.mapToScene(e.position().toPoint()))
            self.scene().addItem(item)
            e.acceptProposedAction(); return
        super().dropEvent(e)
