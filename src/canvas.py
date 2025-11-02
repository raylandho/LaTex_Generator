from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsEllipseItem, QGraphicsPathItem
)

from constants import GRID_SIZE, SCENE_BOUNDS, ASSET_MAP
from items import PixmapItem, LabelItem, LineItem, RectItem, EllipseItem, load_pixmap_for, snap_to_grid
from palette import MIME_TYPE


# ---------------- Scene ----------------
class WhiteboardScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(SCENE_BOUNDS)
        self.setBackgroundBrush(Qt.white)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        # --- crisp grid ---
        grid_pen = QPen(QColor(235, 235, 235))
        grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)

        left = int(rect.left()) - (int(rect.left()) % GRID_SIZE)
        top = int(rect.top()) - (int(rect.top()) % GRID_SIZE)

        x = float(left)
        while x < rect.right():
            painter.drawLine(x + 0.5, rect.top(), x + 0.5, rect.bottom())
            x += GRID_SIZE

        y = float(top)
        while y < rect.bottom():
            painter.drawLine(rect.left(), y + 0.5, rect.right(), y + 0.5)
            y += GRID_SIZE

        # --- axes ---
        axis_pen = QPen(QColor(210, 210, 210))
        axis_pen.setCosmetic(True)
        axis_pen.setWidth(2)
        painter.setPen(axis_pen)
        painter.drawLine(rect.left(), 0.5, rect.right(), 0.5)   # X
        painter.drawLine(0.5, rect.top(), 0.5, rect.bottom())   # Y


# ---------------- View ----------------
class WhiteboardView(QGraphicsView):
    def __init__(self, scene: WhiteboardScene, assets_dir: str):
        super().__init__(scene)
        self.assets_dir = assets_dir

        # Rendering & performance
        self.setRenderHints(QPainter.Antialiasing |
                            QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.viewport().setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.viewport().setAttribute(Qt.WA_NoSystemBackground, True)

        # Disable zoom/pan
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setDragMode(QGraphicsView.RubberBandDrag)

        # Enable drag-and-drop
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        # Overlay (selection box)
        self._overlay = None
        try:
            self.scene().selectionChanged.connect(self._on_selection_changed)
        except Exception:
            pass

        # Tool states
        self._tool = "select"        # select / line / pen / eraser

        # Line tool
        self._drawing_line = False
        self._line_item = None
        self._line_p0 = QPointF()

        # Pen tool (smoothed)
        self._drawing_pen = False
        self._pen_path: QPainterPath | None = None
        self._pen_item: QGraphicsPathItem | None = None
        self._pen_last: QPointF | None = None
        self._pen_min_step = 2.0  # ignore jitter < 2 px

        # Eraser
        self._erasing = False
        self._eraser_radius = 16
        self._eraser_circle = None

    # ---------- Tool management ----------
    def set_tool(self, name: str):
        self._tool = name
        if name in ("line", "pen", "eraser"):
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            self.setDragMode(QGraphicsView.RubberBandDrag)

        if name == "eraser":
            self.viewport().setCursor(Qt.CrossCursor)
            self._make_eraser_circle()
        elif name == "pen":
            self.viewport().setCursor(Qt.CrossCursor)
            self._remove_eraser_circle()
        else:
            self.viewport().unsetCursor()
            self._remove_eraser_circle()

    # ---------- Eraser preview circle ----------
    def _make_eraser_circle(self):
        if not self._eraser_circle:
            circle = QGraphicsEllipseItem(
                0, 0, self._eraser_radius * 2, self._eraser_radius * 2
            )
            pen = QPen(QColor(150, 150, 150, 180))
            pen.setCosmetic(True)
            circle.setPen(pen)
            circle.setBrush(Qt.NoBrush)
            circle.setZValue(1e9)
            circle.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations)
            self._eraser_circle = circle
            self.scene().addItem(circle)
            circle.hide()

    def _remove_eraser_circle(self):
        if self._eraser_circle:
            self.scene().removeItem(self._eraser_circle)
            self._eraser_circle = None

    # ---------- Mouse handling ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            super().mousePressEvent(e)
            return

        if self._tool == "line":
            self._start_line(e)
        elif self._tool == "pen":
            self._start_pen(e)
        elif self._tool == "eraser":
            self._start_erasing(e)
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._tool == "line" and self._drawing_line:
            self._update_line(e); return
        elif self._tool == "pen" and self._drawing_pen:
            self._continue_pen(e); return
        elif self._tool == "eraser":
            self._update_eraser_cursor(e)
            if self._erasing:
                self._erase_at(e)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            super().mouseReleaseEvent(e)
            return

        if self._tool == "line" and self._drawing_line:
            self._finish_line(e)
        elif self._tool == "pen" and self._drawing_pen:
            self._finish_pen()
        elif self._tool == "eraser" and self._erasing:
            self._stop_erasing()
        else:
            super().mouseReleaseEvent(e)

    # ---------- Line tool ----------
    def _start_line(self, e):
        self._drawing_line = True
        p0 = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            p0 = snap_to_grid(p0)
        self._line_p0 = p0
        self._line_item = LineItem(p0, p0)  # static line (non-selectable)
        self.scene().addItem(self._line_item)

    def _update_line(self, e):
        if not self._line_item:
            return
        p1 = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            p1 = snap_to_grid(p1)
        self._line_item.setLine(QLineF(self._line_p0, p1))

    def _finish_line(self, e):
        self._drawing_line = False
        if not self._line_item:
            return
        if self._line_item.line().length() < 1.0:
            self.scene().removeItem(self._line_item)
        self._line_item = None

    # ---------- Pen tool (smoothed) ----------
    def _start_pen(self, e):
        self._drawing_pen = True
        pos = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            pos = snap_to_grid(pos)
        self._pen_last = pos
        self._pen_path = QPainterPath(pos)
        self._pen_item = QGraphicsPathItem(self._pen_path)
        pen = QPen(Qt.black, 2)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self._pen_item.setPen(pen)
        self._pen_item.setZValue(10)
        self.scene().addItem(self._pen_item)

    def _continue_pen(self, e):
        if not self._pen_item or self._pen_path is None or self._pen_last is None:
            return
        cur = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            cur = snap_to_grid(cur)
        # ignore tiny jitter
        if (cur - self._pen_last).manhattanLength() < self._pen_min_step:
            return
        # Quadratic midpoint smoothing: control = last, end = midpoint(last, cur)
        mid = QPointF((self._pen_last.x() + cur.x()) * 0.5,
                      (self._pen_last.y() + cur.y()) * 0.5)
        self._pen_path.quadTo(self._pen_last, mid)
        self._pen_item.setPath(self._pen_path)
        self._pen_last = cur

    def _finish_pen(self):
        # Nudge final segment so the tail closes nicely
        if self._pen_item and self._pen_path is not None and self._pen_last is not None:
            self._pen_path.lineTo(self._pen_last)
            self._pen_item.setPath(self._pen_path)
        self._drawing_pen = False
        self._pen_path = None
        self._pen_item = None
        self._pen_last = None

    # ---------- Eraser ----------
    def _start_erasing(self, e):
        self._erasing = True
        self._erase_at(e)
        if self._eraser_circle:
            self._eraser_circle.show()

    def _stop_erasing(self):
        self._erasing = False
        if self._eraser_circle:
            self._eraser_circle.hide()

    def _update_eraser_cursor(self, e):
        if not self._eraser_circle:
            return
        pos = self.mapToScene(e.position().toPoint())
        self._eraser_circle.setRect(
            pos.x() - self._eraser_radius,
            pos.y() - self._eraser_radius,
            self._eraser_radius * 2,
            self._eraser_radius * 2
        )

    def _erase_at(self, e):
        pos = self.mapToScene(e.position().toPoint())
        rect = QRectF(
            pos.x() - self._eraser_radius,
            pos.y() - self._eraser_radius,
            self._eraser_radius * 2,
            self._eraser_radius * 2
        )
        hits = self.scene().items(rect)
        for it in hits:
            if it is self._eraser_circle or it is self._overlay:
                continue
            self.scene().removeItem(it)
            del it

    # ---------- Overlay ----------
    def _on_selection_changed(self):
        sel = list(self.scene().selectedItems())
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
            self._overlay.update_from_target()
            return
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

    # ---------- Drag & drop from palette ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_TYPE):
            e.setDropAction(Qt.CopyAction)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(MIME_TYPE):
            e.setDropAction(Qt.CopyAction)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        e.accept()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_TYPE):
            e.ignore()
            return

        label = bytes(e.mimeData().data(MIME_TYPE)).decode("utf-8")

        if label == "Text":
            item = LabelItem("m")

        elif label == "Rectangle":
            item = RectItem()  # default 120x80, no fill
            item.setTransformOriginPoint(item.boundingRect().center())

        elif label == "Ellipse":
            item = EllipseItem()  # default 120x80, no fill
            item.setTransformOriginPoint(item.boundingRect().center())

        else:
            filename = ASSET_MAP.get(label)
            pix = load_pixmap_for(filename, self.assets_dir)
            item = PixmapItem(pix)
            br = item.boundingRect()
            item.setOffset(-br.width() / 2, -br.height() / 2)

        pos = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            pos = snap_to_grid(pos)
        item.setTransformOriginPoint(item.boundingRect().center())
        item.setPos(pos)

        self.scene().addItem(item)
        item.setSelected(True)

        if self._tool == "select":
            self._ensure_overlay(item)

        e.setDropAction(Qt.CopyAction)
        e.acceptProposedAction()
