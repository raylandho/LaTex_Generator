from __future__ import annotations
from typing import Optional, List
from math import atan2, degrees
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF
from PySide6.QtGui import QPen, QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsRectItem, QGraphicsItem, QGraphicsEllipseItem, QStyleOptionGraphicsItem, QWidget
)

HANDLE_SIZE = 10.0
BOX_COLOR = QColor(40, 120, 255, 180)
BOX_PEN = QPen(BOX_COLOR, 1.5)
HANDLE_BRUSH = QBrush(QColor(255, 255, 255))
HANDLE_PEN = QPen(BOX_COLOR, 1.5)

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

def apply_transform(item: QGraphicsItem):
    from PySide6.QtGui import QTransform
    item.setTransformOriginPoint(item.boundingRect().center())
    t = QTransform()
    angle = getattr(item, "_angle", 0.0)
    sx = getattr(item, "_sx", 1.0)
    sy = getattr(item, "_sy", 1.0)
    t.rotate(angle)
    t.scale(sx, sy)
    item.setTransform(t)

class TransformOverlay(QGraphicsObject):
    def __init__(self, target: QGraphicsItem):
        super().__init__(None)
        self.setZValue(1e9)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setFlag(QGraphicsItem.ItemHasNoContents, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

        self._target = target
        self._rect = QRectF()
        self._handles: List[Handle] = []
        self._rotate_handle: Optional[RotateHandle] = None

        # don't install the event filter yet; wait until we're in the same scene
        self.update_from_target()

    def attach(self):
        if self.scene() is not None and self._target.scene() is self.scene():
            self._target.installSceneEventFilter(self)

    def boundingRect(self) -> QRectF:
        pad = 30
        r = self._rect
        return r.adjusted(-pad, -pad, pad, pad)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        if not self._target or not self._target.scene():
            return
        painter.setPen(BOX_PEN)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)

    def update_from_target(self):
        if not self._target or not self._target.scene():
            return
        # map local corners to scene, then take AABB (works with rotation)
        local = self._target.boundingRect()
        mapped = [self._target.mapToScene(p) for p in (local.topLeft(), local.topRight(),
                                                       local.bottomRight(), local.bottomLeft())]
        xs = [p.x() for p in mapped]; ys = [p.y() for p in mapped]
        self._rect = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
        self.setPos(0, 0)

        self._ensure_handles()
        self._layout_handles()
        self.prepareGeometryChange()
        self.update()

    def _ensure_handles(self):
        if self._handles:
            return
        for role in ("N", "S", "E", "W", "NE", "NW", "SE", "SW"):
            self._handles.append(Handle(self, role))
        self._rotate_handle = RotateHandle(self)

    def _layout_handles(self):
        r = self._rect
        cx, cy = r.center().x(), r.center().y()
        s = HANDLE_SIZE
        positions = {
            "N":  QPointF(cx, r.top()),
            "S":  QPointF(cx, r.bottom()),
            "E":  QPointF(r.right(), cy),
            "W":  QPointF(r.left(),  cy),
            "NE": QPointF(r.right(), r.top()),
            "NW": QPointF(r.left(),  r.top()),
            "SE": QPointF(r.right(), r.bottom()),
            "SW": QPointF(r.left(),  r.bottom()),
        }
        for h in self._handles:
            p = positions[h.role]
            h.setRect(QRectF(p.x() - s/2, p.y() - s/2, s, s))

        if self._rotate_handle:
            top_center = QPointF(cx, r.top())
            offset = QPointF(0, -24)
            self._rotate_handle.setRect(QRectF(top_center + offset - QPointF(s/2, s/2), QSizeF(s, s)))

    # keep overlay synced when target moves/rotates/transforms
    def sceneEventFilter(self, watched: QGraphicsItem, event) -> bool:
        name = getattr(event, "__class__", type(event)).__name__
        if ("GraphicsSceneMove" in name or
            "GraphicsSceneMouseMove" in name or
            "GraphicsSceneChange" in name or
            "GraphicsSceneUpdate" in name or
            "GraphicsSceneResize" in name or
            "GraphicsSceneWheel" in name or
            "GraphicsSceneHover" in name):
            self.update_from_target()
        return False

    @property
    def target(self) -> QGraphicsItem:
        return self._target

class Handle(QGraphicsRectItem):
    def __init__(self, overlay: TransformOverlay, role: str):
        super().__init__(overlay)
        self.setBrush(HANDLE_BRUSH)
        self.setPen(HANDLE_PEN)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor({
            "N": Qt.SizeVerCursor, "S": Qt.SizeVerCursor,
            "E": Qt.SizeHorCursor, "W": Qt.SizeHorCursor,
            "NE": Qt.SizeBDiagCursor, "SW": Qt.SizeBDiagCursor,
            "NW": Qt.SizeFDiagCursor, "SE": Qt.SizeFDiagCursor
        }[role])
        self.role = role
        self._press_local: Optional[QPointF] = None
        self._center_local: Optional[QPointF] = None
        self._start_sx = 1.0
        self._start_sy = 1.0

    def mousePressEvent(self, e):
        t = self.parentItem().target
        br = t.boundingRect()
        self._center_local = br.center()
        # position where user grabbed, mapped to target's local coords
        press_local = t.mapFromScene(e.scenePos())
        self._press_local = press_local - self._center_local
        if not hasattr(t, "_sx"): t._sx = 1.0
        if not hasattr(t, "_sy"): t._sy = 1.0
        if not hasattr(t, "_angle"): t._angle = 0.0
        self._start_sx = t._sx
        self._start_sy = t._sy
        e.accept()

    def mouseMoveEvent(self, e):
        if self._press_local is None or self._center_local is None:
            return
        t = self.parentItem().target
        cur_local = t.mapFromScene(e.scenePos()) - self._center_local

        # epsilon to avoid division by ~0
        EPS = 1e-6
        sx, sy = 1.0, 1.0

        if self.role in ("E", "W"):
            denom = self._press_local.x()
            if abs(denom) > EPS:
                sx = cur_local.x() / denom
        elif self.role in ("N", "S"):
            denom = self._press_local.y()
            if abs(denom) > EPS:
                sy = cur_local.y() / denom
        else:  # corners
            dx = self._press_local.x(); dy = self._press_local.y()
            if abs(dx) > EPS:
                sx = cur_local.x() / dx
            if abs(dy) > EPS:
                sy = cur_local.y() / dy

        # Clamp scale and apply (center stays fixed because origin is center)
        t._sx = clamp(self._start_sx * sx, 0.1, 10.0)
        t._sy = clamp(self._start_sy * sy, 0.1, 10.0)
        apply_transform(t)
        self.parentItem().update_from_target()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._press_local = None
        self._center_local = None
        e.accept()

class RotateHandle(QGraphicsEllipseItem):
    def __init__(self, overlay: TransformOverlay):
        super().__init__(overlay)
        self.setBrush(HANDLE_BRUSH)
        self.setPen(HANDLE_PEN)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.SizeAllCursor)
        self._press_angle = 0.0
        self._start_angle = 0.0

    def mousePressEvent(self, e):
        t = self.parentItem().target
        rect = self.parentItem()._rect
        center = rect.center()
        p = e.scenePos()
        self._press_angle = atan2(p.y() - center.y(), p.x() - center.x())
        if not hasattr(t, "_angle"): t._angle = 0.0
        self._start_angle = t._angle
        e.accept()

    def mouseMoveEvent(self, e):
        t = self.parentItem().target
        rect = self.parentItem()._rect
        center = rect.center()
        p = e.scenePos()
        ang = atan2(p.y() - center.y(), p.x() - center.x())
        delta_deg = degrees(ang - self._press_angle)
        t._angle = (self._start_angle + delta_deg) % 360.0
        apply_transform(t)
        self.parentItem().update_from_target()
        e.accept()

    def mouseReleaseEvent(self, e):
        e.accept()
