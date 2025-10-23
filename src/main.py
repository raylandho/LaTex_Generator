from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QToolBar, QStyle,
    QFileDialog, QTabWidget, QInputDialog, QMessageBox
)

from constants import SCENE_BOUNDS  # (not used directly, but fine to keep)
from palette import Palette
from canvas import WhiteboardScene, WhiteboardView


class MainWindow(QMainWindow):
    def __init__(self, project_root: str):
        super().__init__()
        self.setWindowTitle("PhysDraw — PNG Whiteboard")
        self.resize(1200, 800)

        self.assets_dir = os.path.join(project_root, "assets")

        # Left: shared palette; Right: tabbed whiteboards
        self.palette = Palette(self.assets_dir)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_page_index)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setMovable(True)

        # Build central layout
        central = QWidget(self)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.palette)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._make_toolbar()

        # Status
        self.statusBar().showMessage(
            "Drag PNGs from the palette. No zoom or panning. "
            "Use the toolbar or Ctrl+= / Ctrl+- to resize selected items."
        )

        # Create first page
        self._add_page("Page 1")

    # ---------------- Toolbar ----------------
    def _make_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)

        # Pages
        act_new_page = QAction("New Page", self)
        act_new_page.setShortcut("Ctrl+T")
        act_new_page.triggered.connect(self._add_page_dialog)
        tb.addAction(act_new_page)

        act_close_page = QAction("Close Page", self)
        act_close_page.setShortcut("Ctrl+W")
        act_close_page.triggered.connect(self._close_current_page)
        tb.addAction(act_close_page)

        act_rename_page = QAction("Rename Page", self)
        act_rename_page.triggered.connect(self._rename_current_page)
        tb.addAction(act_rename_page)

        tb.addSeparator()

        # Scene actions
        act_clear = QAction(self.style().standardIcon(QStyle.SP_TrashIcon), "Clear", self)
        act_clear.triggered.connect(self._clear_current_scene)
        tb.addAction(act_clear)

        act_delete = QAction("Delete Selected", self)
        act_delete.setShortcut("Del")
        act_delete.triggered.connect(self._delete_selected)
        tb.addAction(act_delete)

        act_add_text = QAction("Add Text", self)
        act_add_text.triggered.connect(self._add_text)
        tb.addAction(act_add_text)

        tb.addSeparator()

        # Resize controls for selected items
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
        act_export_png.triggered.connect(self._export_png_current)
        tb.addAction(act_export_png)

    # ---------------- Helpers: active page ----------------
    def _current_view(self) -> WhiteboardView | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, WhiteboardView) else None

    def _current_scene(self) -> WhiteboardScene | None:
        v = self._current_view()
        return v.scene() if v else None

    # ---------------- Page management ----------------
    def _add_page_dialog(self):
        name, ok = QInputDialog.getText(self, "New Page", "Page name:", text=f"Page {self.tabs.count()+1}")
        if ok and name.strip():
            self._add_page(name.strip())

    def _add_page(self, name: str):
    # Give the scene a QObject parent to keep it alive
        scene = WhiteboardScene(parent=self)
        view = WhiteboardView(scene, self.assets_dir)

        # Belt-and-suspenders: also parent the scene to the view and keep a ref
        scene.setParent(view)
        view._scene_ref = scene  # strong reference to prevent GC

        idx = self.tabs.addTab(view, name)
        self.tabs.setCurrentIndex(idx)

    def _close_current_page(self):
        idx = self.tabs.currentIndex()
        if idx < 0:
            return
        self._close_page_index(idx)

    def _close_page_index(self, index: int):
        if self.tabs.count() <= 1:
            QMessageBox.information(self, "Close Page", "At least one page must remain.")
            return
        self.tabs.removeTab(index)

    def _rename_current_page(self):
        idx = self.tabs.currentIndex()
        if idx < 0:
            return
        current = self.tabs.tabText(idx)
        name, ok = QInputDialog.getText(self, "Rename Page", "New name:", text=current)
        if ok and name.strip():
            self.tabs.setTabText(idx, name.strip())

    def _on_tab_changed(self, index: int):
        # optional: update status per page
        if index >= 0:
            self.statusBar().showMessage(f"Active: {self.tabs.tabText(index)}")

    # ---------------- Scene ops (target current tab) ----------------
    def _clear_current_scene(self):
        sc = self._current_scene()
        if sc:
            sc.clear()

    def _delete_selected(self):
        sc = self._current_scene()
        if not sc:
            return
        for it in sc.selectedItems():
            sc.removeItem(it)
            del it

    def _add_text(self):
        sc = self._current_scene()
        if not sc:
            return
        from items import LabelItem
        item = LabelItem("F")
        sc.addItem(item)
        item.setTransformOriginPoint(item.boundingRect().center())

    def _export_png_current(self):
        view = self._current_view()
        sc = self._current_scene()
        if not view or not sc:
            return
        default_name = f"{self.tabs.tabText(self.tabs.currentIndex())}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", default_name, "PNG (*.png)")
        if not path:
            return
        from PySide6.QtGui import QPixmap, QPainter
        rect = sc.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        img = QPixmap(int(max(64, rect.width())), int(max(64, rect.height())))
        img.fill(Qt.white)
        p = QPainter(img)
        sc.render(p, source=rect)
        p.end()
        img.save(path, "PNG")

    # Helper used by toolbar actions to scale selected items
    def _scale_selected(self, factor: float):
        sc = self._current_scene()
        if not sc:
            return
        from items import PixmapItem, LabelItem  # absolute import
        for it in sc.selectedItems():
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
