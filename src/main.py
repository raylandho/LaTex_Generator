from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QToolBar, QStyle, QFileDialog, QGraphicsView
)

from palette import Palette
from canvas import WhiteboardScene, WhiteboardView


class MainWindow(QMainWindow):
    def __init__(self, project_root: str):
        super().__init__()
        self.setWindowTitle("PhysDraw — PNG Whiteboard")
        self.resize(1200, 800)

        assets_dir = os.path.join(project_root, "assets")
        self.scene = WhiteboardScene()
        self.view = WhiteboardView(self.scene, assets_dir)
        self.palette = Palette(assets_dir)

        central = QWidget(self)
        lay = QHBoxLayout(central)
        lay.addWidget(self.palette)
        lay.addWidget(self.view, 1)
        self.setCentralWidget(central)

        self._make_toolbar()
        self.statusBar().showMessage(
            "Drag PNGs from the palette. Wheel=zoom, Right/Middle-drag or Space+Left=pan. "
            "Select + Ctrl+= / Ctrl+- resize (or Shift+Wheel). Alt=rotate with wheel. Alt=drag disables snap."
        )

    # ---------------- Toolbar ----------------
    def _make_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)

        # Basic scene actions
        act_clear = QAction(self.style().standardIcon(QStyle.SP_TrashIcon), "Clear", self)
        act_clear.triggered.connect(self.scene.clear)
        tb.addAction(act_clear)

        act_delete = QAction("Delete Selected", self)
        act_delete.setShortcut("Del")
        act_delete.triggered.connect(self._delete_selected)
        tb.addAction(act_delete)

        act_add_text = QAction("Add Text", self)
        act_add_text.triggered.connect(self._add_text)
        tb.addAction(act_add_text)

        # --------- Zoom controls ----------
        tb.addSeparator()
        act_zoom_in = QAction(self.style().standardIcon(QStyle.SP_ArrowUp), "Zoom In", self)
        act_zoom_in.setShortcut("Ctrl++")
        act_zoom_in.triggered.connect(lambda: self._zoom_by(1.2))
        tb.addAction(act_zoom_in)

        act_zoom_out = QAction(self.style().standardIcon(QStyle.SP_ArrowDown), "Zoom Out", self)
        act_zoom_out.setShortcut("Ctrl+-")
        act_zoom_out.triggered.connect(lambda: self._zoom_by(1/1.2))
        tb.addAction(act_zoom_out)

        act_zoom_reset = QAction("100%", self)
        act_zoom_reset.setShortcut("Ctrl+0")
        act_zoom_reset.triggered.connect(self._zoom_reset)
        tb.addAction(act_zoom_reset)

        # --------- Pan controls ----------
        tb.addSeparator()
        # Pan step in screen pixels (converted to scene units automatically)
        PAN_STEP = 80
        act_pan_left  = QAction("◀", self); act_pan_left.setToolTip("Pan Left")
        act_pan_right = QAction("▶", self); act_pan_right.setToolTip("Pan Right")
        act_pan_up    = QAction("▲", self); act_pan_up.setToolTip("Pan Up")
        act_pan_down  = QAction("▼", self); act_pan_down.setToolTip("Pan Down")

        act_pan_left.triggered.connect(lambda: self._pan_pixels(-PAN_STEP, 0))
        act_pan_right.triggered.connect(lambda: self._pan_pixels(+PAN_STEP, 0))
        act_pan_up.triggered.connect(lambda: self._pan_pixels(0, -PAN_STEP))
        act_pan_down.triggered.connect(lambda: self._pan_pixels(0, +PAN_STEP))

        tb.addAction(act_pan_left)
        tb.addAction(act_pan_right)
        tb.addAction(act_pan_up)
        tb.addAction(act_pan_down)

        # --------- Export ----------
        tb.addSeparator()
        act_export_png = QAction("Export PNG", self)
        act_export_png.triggered.connect(self._export_png)
        tb.addAction(act_export_png)

        # --------- Size controls (you already had these) ----------
        tb.addSeparator()
        act_scale_up = QAction("Bigger", self)
        act_scale_up.setShortcut("Ctrl+=")
        act_scale_up.triggered.connect(lambda: self._scale_selected(1.1))
        tb.addAction(act_scale_up)

        act_scale_down = QAction("Smaller", self)
        act_scale_down.setShortcut("Ctrl+-")
        act_scale_down.triggered.connect(lambda: self._scale_selected(1/1.1))
        tb.addAction(act_scale_down)

    # ---------------- Helpers ----------------
    def _zoom_by(self, factor: float):
        # Zoom around the view center
        self.view.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.view.scale(factor, factor)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def _zoom_reset(self):
        self.view.resetTransform()
        self.view.centerOn(0, 0)

    def _pan_pixels(self, dx_px: int, dy_px: int):
        """Pan by a fixed number of screen pixels, independent of zoom."""
        vp_rect = self.view.viewport().rect()
        center_px = vp_rect.center()
        src_scene = self.view.mapToScene(center_px)
        dst_scene = self.view.mapToScene(center_px + QPoint(dx_px, dy_px))
        self.view.centerOn(src_scene + (dst_scene - src_scene))
        self.view.setFocus()

    def _delete_selected(self):
        for it in self.scene.selectedItems():
            self.scene.removeItem(it)
            del it

    def _add_text(self):
        from items import LabelItem
        item = LabelItem("F")
        self.scene.addItem(item)
        item.setTransformOriginPoint(item.boundingRect().center())

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "diagram.png", "PNG (*.png)")
        if not path:
            return
        from PySide6.QtGui import QPixmap, QPainter
        rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        img = QPixmap(int(max(64, rect.width())), int(max(64, rect.height())))
        img.fill(Qt.white)
        p = QPainter(img)
        self.scene.render(p, source=rect)
        p.end()
        img.save(path, "PNG")

    def _scale_selected(self, factor: float):
        from items import PixmapItem, LabelItem
        for it in self.scene.selectedItems():
            if isinstance(it, LabelItem):
                f = it.font()
                size = f.pointSizeF() if f.pointSizeF() > 0 else 12.0
                new_size = max(6.0, min(96.0, size * factor))
                f.setPointSizeF(new_size)
                it.setFont(f)
            else:
                # Geometric scale for pixmaps/other items
                new_scale = max(0.1, min(10.0, it.scale() * factor))
                it.setScale(new_scale)


def main():
    app = QApplication(sys.argv)
    root = os.path.dirname(os.path.abspath(__file__))  # src/
    project_root = os.path.dirname(root)               # project root
    win = MainWindow(project_root=project_root)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
