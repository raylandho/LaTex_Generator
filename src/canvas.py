from __future__ import annotations
from math import atan2, degrees, radians, cos, sin, hypot

from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsEllipseItem, QGraphicsPathItem,
    QGraphicsPixmapItem, QGraphicsLineItem, QGraphicsTextItem, QGraphicsRectItem
)

from constants import GRID_SIZE, SCENE_BOUNDS, ASSET_MAP
from items import (
    PixmapItem, LabelItem, LineItem, RectItem, EllipseItem, ArcItem,
    load_pixmap_for, snap_to_grid
)
from palette import MIME_TYPE


# ---------------- Helpers ----------------
def _constrain_to_cardinal_45(p0: QPointF, p1: QPointF) -> QPointF:
    """Snap angle from p0->p1 to nearest multiple of 45° while preserving length."""
    dx, dy = p1.x() - p0.x(), p1.y() - p0.y()
    if dx == 0 and dy == 0:
        return p1
    ang = degrees(atan2(dy, dx))
    snapped = round(ang / 45.0) * 45.0
    r = (dx * dx + dy * dy) ** 0.5
    nx = p0.x() + r * cos(radians(snapped))
    ny = p0.y() + r * sin(radians(snapped))
    return QPointF(nx, ny)


def _deg_from(p: QPointF, c: QPointF) -> float:
    """Angle in degrees from center c to point p, 0° at +X, CCW positive."""
    return degrees(atan2(p.y() - c.y(), p.x() - c.x()))


def _ccw_span(start_deg: float, end_deg: float) -> float:
    """Return CCW sweep from start->end in [0, 360)."""
    return (end_deg - start_deg) % 360.0


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

        # Disable zoom/pan by default (you can add Ctrl+Wheel zoom later)
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
        self._tool = "select"        # select / line / pen / eraser / arc

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

        # Arc tool (3-step: center -> start -> end)
        self._arc_stage = 0           # 0=pick center, 1=pick start, 2=pick end
        self._arc_center = QPointF()
        self._arc_start = QPointF()
        self._arc_preview: QGraphicsPathItem | None = None
        # Arc: visible dots + faint radius circle
        self._arc_center_dot: QGraphicsEllipseItem | None = None
        self._arc_start_dot: QGraphicsEllipseItem | None = None
        self._arc_end_dot: QGraphicsEllipseItem | None = None
        self._arc_radius_preview: QGraphicsEllipseItem | None = None

        # --- Reliable live modifier tracking ---
        self.setFocusPolicy(Qt.StrongFocus)   # receive key events
        self._mod_ctrl = False
        self._mod_shift = False
        self._mod_alt = False

    # ---------- Utility: safe remove ----------
    def _safe_remove_item(self, item):
        """Remove a QGraphicsItem if it's still valid and in a scene."""
        if not item:
            return
        try:
            from shiboken6 import isValid
            if not isValid(item):
                return
        except Exception:
            pass
        try:
            sc = item.scene()
            if sc is not None:
                sc.removeItem(item)
        except RuntimeError:
            pass

    # ---------- Tool management ----------
    def set_tool(self, name: str):
        self._tool = name
        if name in ("line", "pen", "eraser", "arc"):
            self.setDragMode(QGraphicsView.NoDrag)
        else:
            self.setDragMode(QGraphicsView.RubberBandDrag)

        if name == "eraser":
            self.viewport().setCursor(Qt.CrossCursor)
            self._make_eraser_circle()
        elif name in ("pen", "line", "arc"):
            self.viewport().setCursor(Qt.CrossCursor)
            self._remove_eraser_circle()
            if name != "arc":
                self._reset_arc()
        else:
            self.viewport().unsetCursor()
            self._remove_eraser_circle()
            self._reset_arc()

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
            circle.setAcceptedMouseButtons(Qt.NoButton)
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
        elif self._tool == "arc":
            self._arc_click(e)
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
        elif self._tool == "arc" and self._arc_stage >= 1:
            self._arc_update_preview(e); return
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

    # ---------- Key handling for reliable modifiers ----------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Control:
            self._mod_ctrl = True
            # instant preview flip if in arc gesture
            if self._tool == "arc" and self._arc_stage == 2:
                self._arc_update_preview_from_point(None)
        elif k == Qt.Key_Shift:
            self._mod_shift = True
            if self._tool == "arc" and self._arc_stage == 2:
                self._arc_update_preview_from_point(None)
        elif k == Qt.Key_Alt:
            self._mod_alt = True
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        k = e.key()
        if k == Qt.Key_Control:
            self._mod_ctrl = False
            if self._tool == "arc" and self._arc_stage == 2:
                self._arc_update_preview_from_point(None)
        elif k == Qt.Key_Shift:
            self._mod_shift = False
            if self._tool == "arc" and self._arc_stage == 2:
                self._arc_update_preview_from_point(None)
        elif k == Qt.Key_Alt:
            self._mod_alt = False
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        # reset modifier tracking if we lose focus mid-gesture
        self._mod_ctrl = self._mod_shift = self._mod_alt = False
        super().focusOutEvent(e)

    # ---------- Line tool ----------
    def _start_line(self, e):
        self._drawing_line = True
        p0 = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            p0 = snap_to_grid(p0)
        self._line_p0 = p0
        self._line_item = LineItem(p0, p0)  # static line (non-selectable by default)
        self.scene().addItem(self._line_item)

    def _update_line(self, e):
        if not self._line_item:
            return
        p1 = self.mapToScene(e.position().toPoint())
        if not (e.modifiers() & Qt.AltModifier):
            p1 = snap_to_grid(p1)
        if e.modifiers() & Qt.ShiftModifier:
            p1 = _constrain_to_cardinal_45(self._line_p0, p1)
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
        self._pen_item.setFlag(QGraphicsPathItem.ItemIsSelectable, True)
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

        # Transient preview items we should never erase
        transient_ids = {
            id(self._eraser_circle), id(self._overlay),
            id(self._arc_preview), id(self._arc_center_dot),
            id(self._arc_start_dot), id(self._arc_end_dot),
            id(self._arc_radius_preview),
        }

        for it in hits:
            if id(it) in transient_ids:
                continue
            if self._overlay and it.parentItem() is self._overlay:
                continue
            # Erase only drawable content types
            if isinstance(it, (QGraphicsPathItem, QGraphicsPixmapItem,
                               QGraphicsLineItem, QGraphicsTextItem,
                               QGraphicsRectItem, QGraphicsEllipseItem)):
                self.scene().removeItem(it)

    # ---------- Arc tool ----------
    def _reset_arc(self):
        self._arc_stage = 0
        self._arc_center = QPointF()
        self._arc_start = QPointF()

        # Safely dispose transient preview items
        for attr in ("_arc_preview", "_arc_center_dot", "_arc_start_dot",
                     "_arc_end_dot", "_arc_radius_preview"):
            item = getattr(self, attr)
            if item:
                self._safe_remove_item(item)
                setattr(self, attr, None)

    def _make_dot(self, scene_pos: QPointF, size: int = 7, z: float = 1e9) -> QGraphicsEllipseItem:
        dot = QGraphicsEllipseItem(-size/2, -size/2, size, size)
        pen = QPen(QColor(40, 120, 255, 220), 1.5)
        pen.setCosmetic(True)
        dot.setPen(pen)
        dot.setBrush(QColor(255, 255, 255))
        dot.setZValue(z)
        dot.setFlag(QGraphicsEllipseItem.ItemIgnoresTransformations, True)
        dot.setAcceptedMouseButtons(Qt.NoButton)
        self.scene().addItem(dot)
        dot.setPos(scene_pos)
        return dot

    def _ensure_dot_at(self, dot_attr: str, scene_pos: QPointF):
        dot = getattr(self, dot_attr)
        if dot is None:
            dot = self._make_dot(scene_pos)
            setattr(self, dot_attr, dot)
        else:
            if dot.scene() is None:
                dot = self._make_dot(scene_pos)
                setattr(self, dot_attr, dot)
            else:
                dot.setPos(scene_pos)

    def _arc_click(self, e):
        pos = self.mapToScene(e.position().toPoint())
        if not self._mod_alt:
            pos = snap_to_grid(pos)

        if self._arc_stage == 0:
            # select center + show center dot
            self._arc_center = pos
            self._arc_stage = 1
            self._ensure_dot_at("_arc_center_dot", self._arc_center)

        elif self._arc_stage == 1:
            # select start (2nd click) + show start dot + create preview items
            if hypot(pos.x() - self._arc_center.x(), pos.y() - self._arc_center.y()) < 1.0:
                return
            self._arc_start = pos
            self._arc_stage = 2
            self._ensure_dot_at("_arc_start_dot", self._arc_start)

            if not self._arc_preview:
                self._arc_preview = QGraphicsPathItem()
                pen = QPen(Qt.black, 2)
                pen.setCosmetic(True)
                self._arc_preview.setPen(pen)
                self._arc_preview.setZValue(9)
                self.scene().addItem(self._arc_preview)

            if not self._arc_radius_preview:
                self._arc_radius_preview = QGraphicsEllipseItem()
                pen = QPen(QColor(40, 120, 255, 120), 1.0)
                pen.setCosmetic(True)
                self._arc_radius_preview.setPen(pen)
                self._arc_radius_preview.setBrush(Qt.NoBrush)
                self._arc_radius_preview.setZValue(8)
                self._arc_radius_preview.setAcceptedMouseButtons(Qt.NoButton)
                self.scene().addItem(self._arc_radius_preview)

            self._arc_update_preview(e)

        else:
            # finalize with end point; cleanup handled by _reset_arc
            self._arc_finalize(pos)
            self._reset_arc()

    def _arc_update_preview_from_point(self, cur: QPointF | None):
        """Rebuild preview when modifiers change without mouse movement."""
        if not self._arc_preview:
            return
        if cur is None:
            # re-use last end-dot position if present; otherwise do nothing
            cur_item = self._arc_end_dot
            if not cur_item:
                return
            cur = cur_item.scenePos()

        if not self._mod_alt:
            cur = snap_to_grid(cur)
        self._ensure_dot_at("_arc_end_dot", cur)

        c = self._arc_center
        s = self._arc_start
        r = hypot(s.x() - c.x(), s.y() - c.y())
        if r < 1.0:
            self._arc_preview.setPath(QPainterPath())
            if self._arc_radius_preview:
                self._arc_radius_preview.setRect(QRectF())
            return

        if self._arc_radius_preview:
            self._arc_radius_preview.setRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))

        start_deg_ccw = _deg_from(s, c)
        end_deg_ccw   = _deg_from(cur, c)

        ccw_span = _ccw_span(start_deg_ccw, end_deg_ccw)   # [0, 360)

        # Simple rule: default CW, Ctrl = CCW
        sweep_ccw = ccw_span if self._mod_ctrl else -ccw_span

        # Optional: Shift = major arc in the chosen direction
        if self._mod_shift:
            sweep_ccw = sweep_ccw - 360.0 if sweep_ccw >= 0 else sweep_ccw + 360.0

        start_deg_qt = -start_deg_ccw
        sweep_qt     = -sweep_ccw

        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        path = QPainterPath()
        path.arcMoveTo(rect, start_deg_qt)   # start at 2nd point, no chord
        path.arcTo(rect, start_deg_qt, sweep_qt)
        self._arc_preview.setPath(path)

    def _arc_update_preview(self, e):
        if not self._arc_preview:
            return

        cur = self.mapToScene(e.position().toPoint())
        if not self._mod_alt:
            cur = snap_to_grid(cur)

        # Live end-point marker
        self._ensure_dot_at("_arc_end_dot", cur)

        c = self._arc_center
        s = self._arc_start
        r = hypot(s.x() - c.x(), s.y() - c.y())
        if r < 1.0:
            self._arc_preview.setPath(QPainterPath())
            if self._arc_radius_preview:
                self._arc_radius_preview.setRect(QRectF())
            return

        # Update faint radius circle
        if self._arc_radius_preview:
            self._arc_radius_preview.setRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r))

        # Angles in our CCW convention
        start_deg_ccw = _deg_from(s, c)   # start at 2nd click
        end_deg_ccw   = _deg_from(cur, c)

        # CCW span from start->current
        ccw_span = _ccw_span(start_deg_ccw, end_deg_ccw)   # [0, 360)

        # Behavior: default CW, Ctrl = CCW
        sweep_ccw = ccw_span if self._mod_ctrl else -ccw_span

        # Optional: Shift = major arc in the chosen direction
        if self._mod_shift:
            sweep_ccw = sweep_ccw - 360.0 if sweep_ccw >= 0 else sweep_ccw + 360.0

        # Convert to Qt's clockwise convention for rendering
        start_deg_qt = -start_deg_ccw
        sweep_qt     = -sweep_ccw

        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        path = QPainterPath()
        path.arcMoveTo(rect, start_deg_qt)   # begin exactly at 2nd point (no chord)
        path.arcTo(rect, start_deg_qt, sweep_qt)
        self._arc_preview.setPath(path)

    def _arc_finalize(self, end_pos: QPointF):
        # Use tracked modifiers for reliability
        mods_ctrl = self._mod_ctrl
        mods_alt  = self._mod_alt
        mods_shift = self._mod_shift

        c = self._arc_center
        s = self._arc_start
        if not mods_alt:
            end_pos = snap_to_grid(end_pos)

        r = hypot(s.x() - c.x(), s.y() - c.y())
        if r < 1.0:
            return

        start_deg_ccw = _deg_from(s, c)
        end_deg_ccw   = _deg_from(end_pos, c)

        # CCW span from start->end, then choose direction by Ctrl
        ccw_span = _ccw_span(start_deg_ccw, end_deg_ccw)   # [0, 360)
        sweep_ccw = ccw_span if mods_ctrl else -ccw_span   # Ctrl=CCW, else CW

        # Optional: Shift = major arc
        if mods_shift:
            sweep_ccw = sweep_ccw - 360.0 if sweep_ccw >= 0 else sweep_ccw + 360.0

        # ArcItem expects CCW; it converts internally to Qt's CW with arcMoveTo/arcTo
        arc = ArcItem(c, r, start_deg_ccw, sweep_ccw)
        self.scene().addItem(arc)
        arc.setSelected(True)
        if self._tool == "select":
            self._ensure_overlay(arc)

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
        # make overlay itself non-interactive
        self._overlay.setAcceptedMouseButtons(Qt.NoButton)
        try:
            self._overlay.setFlag(QGraphicsPathItem.ItemIsSelectable, False)
        except Exception:
            pass
        self.scene().addItem(self._overlay)
        if hasattr(self._overlay, "attach"):
            self._overlay.attach()
        self._overlay.update_from_target()

    def _drop_overlay(self):
        if self._overlay:
            self.scene().removeItem(self._overlay)
            try:
                self._overlay.deleteLater()
            except Exception:
                pass
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
            item = RectItem()  # default 120x80
            item.setTransformOriginPoint(item.boundingRect().center())
        elif label == "Ellipse":
            item = EllipseItem()  # default 120x80
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
