from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QToolBar, QStyle, QFileDialog
)

from constants import SCENE_BOUNDS  # (not used directly, but fine to keep)
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
            "Drag PNGs from the palette. Ctrl+Wheel to zoom, Space+drag to pan. "
            "Select + Ctrl+= / Ctrl+- to resize (or Shift+Wheel). Alt = no snap."
        )

    def _make_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)

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

        tb.addSeparator()
        # NEW: resize controls
        act_scale_up = QAction("Bigger", self)
        act_scale_up.setShortcut("Ctrl+=")  # Ctrl+Plus also works
        act_scale_up.triggered.connect(lambda: self._scale_selected(1.1))
        tb.addAction(act_scale_up)

        act_scale_down = QAction("Smaller", self)
        act_scale_down.setShortcut("Ctrl+-")
        act_scale_down.triggered.connect(lambda: self._scale_selected(1/1.1))
        tb.addAction(act_scale_down)

        tb.addSeparator()
        act_export_png = QAction("Export PNG", self)
        act_export_png.triggered.connect(self._export_png)
        tb.addAction(act_export_png)

    def _delete_selected(self):
        for it in self.scene.selectedItems():
            self.scene.removeItem(it)
            del it

    def _add_text(self):
        from items import LabelItem  # absolute import to match your setup
        item = LabelItem("F")
        item.setPos(0, 0)
        self.scene.addItem(item)

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

    # NEW: shared helper used by toolbar and Shift+Wheel
    def _scale_selected(self, factor: float):
        from items import PixmapItem, LabelItem  # absolute import
        for it in self.scene.selectedItems():
            if isinstance(it, PixmapItem):
                new_scale = max(0.1, min(10.0, it.scale() * factor))
                it.setScale(new_scale)
            elif isinstance(it, LabelItem):
                f = it.font()
                size = f.pointSizeF() if f.pointSizeF() > 0 else 12.0
                new_size = max(6.0, min(96.0, size * factor))
                f.setPointSizeF(new_size)
                it.setFont(f)


def main():
    app = QApplication(sys.argv)
    root = os.path.dirname(os.path.abspath(__file__))  # src/
    project_root = os.path.dirname(root)               # project root
    win = MainWindow(project_root=project_root)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
