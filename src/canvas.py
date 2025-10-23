from __future__ import annotations
from PySide6.QtCore import Qt, QRectF, QEvent
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

        # --- crisp grid in exposed rect only ---
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
        painter.drawLine(rect.left(), 0.5, rect.right(), 0.5)   # X
        painter.drawLine(0.5, rect.top(), 0.5, rect.bottom())   # Y


class WhiteboardView(QGraphicsView):
    def __init__(self, scene: WhiteboardScene, assets_dir: str):
        super().__init__(scene)
        self.assets_dir = assets_dir

        # Optional GPU viewport
        try:
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            self.setViewport(QOpenGLWidget())
        except Exception:
            pass

        # Quality & smoothness
        self.setRenderHints(QPainter.Antialiasing |
                            QPainter.TextAntialiasing |
                            QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)

        # Reduce flicker
        self.viewport().setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.viewport().setAttribute(Qt.WA_NoSystemBackground, True)

        # Absolutely no transform or anchor-based zooming
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)

        # No scrollbars, ever
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Keep selection rubber-band and item interaction
        self.setDragMode(QGraphicsView.RubberBandDrag)

        # Accept drops
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        # Optional overlay (selection box/handles)
        self._overlay = None
        try:
            self.scene().selectionChanged.connect(self._on_selection_changed)
        except Exception:
            pass

    # ----- selection overlay hooks -----
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

    # ----------------- HARD BLOCKS: wheel/gestures/keys/scroll -----------------

    # Block mouse wheel & trackpad two-finger scroll
    def wheelEvent(self, e):
        e.accept()  # swallow; no zoom, no scroll

    # Block native gestures from touchpads (pinch/rotate) on Qt 6
    def event(self, e):
        t = e.type()
        if t in (QEvent.NativeGesture, QEvent.Gesture, QEvent.GestureOverride):
            # swallow any gestures so they don't become scroll/zoom
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        # If a text item is actively being edited, don't block typing at all
        fi = self.scene().focusItem()
        if fi and hasattr(fi, "textInteractionFlags") and \
        fi.textInteractionFlags() == Qt.TextEditorInteraction:
            super().keyPressEvent(e)
            return

        # Otherwise, block view-scrolling/navigation keys as before
        blocked_keys = {
            Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
            Qt.Key_Home, Qt.Key_End, Qt.Key_PageUp, Qt.Key_PageDown,
            Qt.Key_Space  # prevent space from scrolling the view
        }

        # Only block when it's one of the above, or when Ctrl/Alt combos (not Shift)
        if e.key() in blocked_keys or (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            e.accept()
            return

        super().keyPressEvent(e)


    # Ensure mouse middle/right/space panning stays off (we do nothing special)
    def mousePressEvent(self, e):  super().mousePressEvent(e)
    def mouseMoveEvent(self, e):   super().mouseMoveEvent(e)
    def mouseReleaseEvent(self, e): super().mouseReleaseEvent(e)

    # ----------------------- Drag & drop ---------------------------
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

            e.setDropAction(Qt.CopyAction)
            e.acceptProposedAction()
            return

        e.ignore()
