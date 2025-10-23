from __future__ import annotations
from typing import Optional, List
from math import atan2, degrees
from PySide6.QtCore import Qt, QPointF, QRectF, QSizeF
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsEllipseItem
)

# Visual constants
HANDLE_SIZE = 10.0
BOX_COLOR = QColor(40, 120, 255, 180)
BOX_PEN = QPen(BOX_COLOR, 1.5)
BOX_PEN.setCosmetic(True)
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

class TransformOverlay(QGraphicsPathItem):
    """
    Robust oriented overlay: a simple QGraphicsPathItem sibling that draws an
    oriented rectangle path in SCENE coordinates. Children handles ignore transforms.
    """
    def __init__(self, target: QGraphicsItem):
        super().__init__()
        self.setZValue(1e9)
        self.setPen(BOX_PEN)
        self.setBrush(Qt.NoBrush)

        self._target = target
        self._handles: List[Handle] = []
        self._rotate_handle: Optional[RotateHandle] = None

        self._ensure_handles()
        self.update_from_target()

    # ---------------- Geometry & drawing ----------------
    def update_from_target(self):
        t = self._target
        if not t or not t.scene():
            return

        # Map target's local corners to SCENE coordinates (oriented quad)
        br = t.boundingRect()
        tl, tr, brc, bl = br.topLeft(), br.topRight(), br.bottomRight(), br.bottomLeft()
        pts_scene = [t.mapToScene(p) for p in (tl, tr, brc, bl)]

        # Build a simple closed path in SCENE coordinates
        path = QPainterPath(pts_scene[0])
        for p in pts_scene[1:]:
            path.lineTo(p)
        path.closeSubpath()

        # Since this item lives in the SCENE (no parent), its local == scene
        self.setPath(path)

        # Layout handles at corners + edge midpoints (in SCENE coords)
        TL, TR, BR_, BL = pts_scene[0], pts_scene[1], pts_scene[2], pts_scene[3]
        def mid(a: QPointF, b: QPointF) -> QPointF: return QPointF((a.x()+b.x())/2.0, (a.y()+b.y())/2.0)
        M_N, M_E, M_S, M_W = mid(TL, TR), mid(TR, BR_), mid(BR_, BL), mid(BL, TL)

        positions = {
            "N":  M_N, "S":  M_S, "E":  M_E, "W":  M_W,
            "NE": TR,  "NW": TL,  "SE": BR_, "SW": BL,
        }
        for h in self._handles:
            h.place_at(positions[h.role])

        # Place rotate handle 24 px outward from top edge normal
        if self._rotate_handle:
            ex = TR.x() - TL.x(); ey = TR.y() - TL.y()
            nx, ny = -ey, ex
            length = (ex*ex + ey*ey) ** 0.5 or 1.0
            nx /= length; ny /= length
            # choose outward direction away from the item's center
            center = self._center_of_points(pts_scene)
            to_mid = QPointF(M_N.x() - center.x(), M_N.y() - center.y())
            if (nx*to_mid.x() + ny*to_mid.y()) < 0:
                nx, ny = -nx, -ny
            offset = QPointF(nx*24.0, ny*24.0)
            self._rotate_handle.place_at(M_N + offset)

        # Keep visible even with GL viewport
        for h in self._handles:
            h.setVisible(True)
        if self._rotate_handle:
            self._rotate_handle.setVisible(True)

    @staticmethod
    def _center_of_points(pts: list[QPointF]) -> QPointF:
        x = sum(p.x() for p in pts) / len(pts)
        y = sum(p.y() for p in pts) / len(pts)
        return QPointF(x, y)

    # ---------------- Scene sync hooks ----------------
    def attach(self):
        # Recompute whenever target moves/changes
        if self.scene() is not None and self._target.scene() is self.scene():
            self._target.installSceneEventFilter(self)
            # For text items, update when document changes (reflows)
            try:
                doc = getattr(self._target, "document", None)
                if callable(doc) and doc():
                    doc().contentsChanged.connect(self.update_from_target)
            except Exception:
                pass

    def sceneEventFilter(self, watched: QGraphicsItem, event) -> bool:
        # Sync on typical scene events
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

    # ---------------- Handles ----------------
    def _ensure_handles(self):
        if self._handles:
            return
        for role in ("N", "S", "E", "W", "NE", "NW", "SE", "SW"):
            self._handles.append(Handle(self, role))
        self._rotate_handle = RotateHandle(self)

    @property
    def target(self) -> QGraphicsItem:
        return self._target


class Handle(QGraphicsRectItem):
    """Resize handle that stays constant size on screen."""
    def __init__(self, overlay: TransformOverlay, role: str):
        super().__init__(overlay)
        self.overlay = overlay
        self.role = role
        self.setBrush(HANDLE_BRUSH)
        self.setPen(HANDLE_PEN)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)  # constant size
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor({
            "N": Qt.SizeVerCursor, "S": Qt.SizeVerCursor,
            "E": Qt.SizeHorCursor, "W": Qt.SizeHorCursor,
            "NE": Qt.SizeBDiagCursor, "SW": Qt.SizeBDiagCursor,
            "NW": Qt.SizeFDiagCursor, "SE": Qt.SizeFDiagCursor
        }[role])

        self._press_local: Optional[QPointF] = None
        self._center_local: Optional[QPointF] = None
        self._start_sx = 1.0
        self._start_sy = 1.0

        # Initialize rect
        self.setRect(QRectF(-HANDLE_SIZE/2, -HANDLE_SIZE/2, HANDLE_SIZE, HANDLE_SIZE))

    def place_at(self, scene_pos: QPointF):
        # Because we ignore transforms, setPos in scene coords is fine
        self.setPos(scene_pos)

    def mousePressEvent(self, e):
        t = self.overlay.target
        br = t.boundingRect()
        self._center_local = br.center()
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
        t = self.overlay.target
        cur_local = t.mapFromScene(e.scenePos()) - self._center_local
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
        else:
            dx = self._press_local.x(); dy = self._press_local.y()
            if abs(dx) > EPS: sx = cur_local.x() / dx
            if abs(dy) > EPS: sy = cur_local.y() / dy

        t._sx = clamp(self._start_sx * sx, 0.1, 10.0)
        t._sy = clamp(self._start_sy * sy, 0.1, 10.0)
        apply_transform(t)
        self.overlay.update_from_target()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._press_local = None
        self._center_local = None
        e.accept()


class RotateHandle(QGraphicsEllipseItem):
    """Rotate handle placed off the top edge; constant on-screen size."""
    def __init__(self, overlay: TransformOverlay):
        super().__init__(overlay)
        self.overlay = overlay
        self.setBrush(HANDLE_BRUSH)
        self.setPen(HANDLE_PEN)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.SizeAllCursor)

        self._press_angle = 0.0
        self._start_angle = 0.0

        self.setRect(QRectF(-HANDLE_SIZE/2, -HANDLE_SIZE/2, HANDLE_SIZE, HANDLE_SIZE))

    def place_at(self, scene_pos: QPointF):
        self.setPos(scene_pos)

    def mousePressEvent(self, e):
        t = self.overlay.target
        center_scene = self._overlay_center_scene()
        p = e.scenePos()
        self._press_angle = atan2(p.y() - center_scene.y(), p.x() - center_scene.x())
        if not hasattr(t, "_angle"): t._angle = 0.0
        self._start_angle = t._angle
        e.accept()

    def mouseMoveEvent(self, e):
        t = self.overlay.target
        center_scene = self._overlay_center_scene()
        p = e.scenePos()
        ang = atan2(p.y() - center_scene.y(), p.x() - center_scene.x())
        delta_deg = degrees(ang - self._press_angle)
        t._angle = (self._start_angle + delta_deg) % 360.0
        apply_transform(t)
        self.overlay.update_from_target()
        e.accept()

    def mouseReleaseEvent(self, e):
        e.accept()

    def _overlay_center_scene(self) -> QPointF:
        # Center of the overlay path’s bounding rect in SCENE coordinates
        br = self.overlay.path().boundingRect().center()
        return br
