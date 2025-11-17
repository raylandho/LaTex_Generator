from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QToolBar, QStyle,
    QFileDialog, QTabWidget, QInputDialog, QMessageBox
)

from palette import Palette
from canvas import WhiteboardScene, WhiteboardView


class MainWindow(QMainWindow):
    def __init__(self, project_root: str):
        super().__init__()
        self.setWindowTitle("PhysDraw — PNG Whiteboard")
        self.resize(1200, 800)

        self.assets_dir = os.path.join(project_root, "assets")

        # Left: palette | Right: tabbed boards
        self.palette = Palette(self.assets_dir)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_page_index)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.palette)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._make_toolbar()

        self.statusBar().showMessage(
            "Tools: Select | Line (Ctrl+L) | Pen (Ctrl+P) | Eraser (Ctrl+E). "
            "Drag items from the palette. Alt bypasses grid snap."
        )

        # First page
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

        # ---- Tool mode: Select / Line / Pen / Eraser ----
        self.act_select = QAction("Select", self)
        self.act_select.setCheckable(True)

        self.act_line = QAction("Line", self)
        self.act_line.setCheckable(True)
        self.act_line.setShortcut("Ctrl+L")

        self.act_pen = QAction("Pen", self)
        self.act_pen.setCheckable(True)
        self.act_pen.setShortcut("Ctrl+P")

        self.act_eraser = QAction("Eraser", self)
        self.act_eraser.setCheckable(True)
        self.act_eraser.setShortcut("Ctrl+E")

        self.act_arc = QAction("Arc", self)
        self.act_arc.setCheckable(True)
        self.act_arc.setShortcut("Ctrl+A")  # note: conflicts with Select All in text contexts; change if you prefer
        tb.addAction(self.act_arc)

        def set_tool(name: str):
            v = self._current_view()
            if not v:
                return
            # update checks
            self.act_select.setChecked(name == "select")
            self.act_line.setChecked(name == "line")
            self.act_pen.setChecked(name == "pen")
            self.act_eraser.setChecked(name == "eraser")
            getattr(self, "act_arc").setChecked(name == "arc")
            # apply to view
            v.set_tool(name)

        self.act_select.triggered.connect(lambda: set_tool("select"))
        self.act_line.triggered.connect(lambda: set_tool("line"))
        self.act_pen.triggered.connect(lambda: set_tool("pen"))
        self.act_eraser.triggered.connect(lambda: set_tool("eraser"))
        self.act_arc.triggered.connect(lambda: set_tool("arc"))

        tb.addAction(self.act_select)
        tb.addAction(self.act_line)
        tb.addAction(self.act_pen)
        tb.addAction(self.act_eraser)
        self.act_select.setChecked(True)

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

        # Resize selected
        act_scale_up = QAction("Bigger", self)
        act_scale_up.setShortcut("Ctrl+=")
        act_scale_up.triggered.connect(lambda: self._scale_selected(1.1))
        tb.addAction(act_scale_up)

        act_scale_down = QAction("Smaller", self)
        act_scale_down.setShortcut("Ctrl+-")
        act_scale_down.triggered.connect(lambda: self._scale_selected(1/1.1))
        tb.addAction(act_scale_down)

        tb.addSeparator()

        # Export
        act_export_png = QAction("Export PNG", self)
        act_export_png.triggered.connect(self._export_png_current)
        tb.addAction(act_export_png)

        act_export_tex = QAction("Export LaTeX", self)
        act_export_tex.triggered.connect(self._export_latex_current)
        tb.addAction(act_export_tex)

        # expose setter for reuse if needed
        self._set_tool_from_toolbar = set_tool

    # ---------------- Pages ----------------
    def _add_page_dialog(self):
        name, ok = QInputDialog.getText(self, "New Page", "Page name:", text=f"Page {self.tabs.count()+1}")
        if ok and name.strip():
            self._add_page(name.strip())

    def _add_page(self, name: str):
        scene = WhiteboardScene(parent=self)
        view = WhiteboardView(scene, self.assets_dir)
        scene.setParent(view)
        idx = self.tabs.addTab(view, name)
        self.tabs.setCurrentIndex(idx)
        # apply currently active tool to the new tab
        if self.act_eraser.isChecked():
            view.set_tool("eraser")
        elif self.act_pen.isChecked():
            view.set_tool("pen")
        elif self.act_line.isChecked():
            view.set_tool("line")
        else:
            view.set_tool("select")

    def _close_current_page(self):
        idx = self.tabs.currentIndex()
        if idx >= 0:
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
        if index < 0:
            return
        self.statusBar().showMessage(f"Active: {self.tabs.tabText(index)}")
        v = self._current_view()
        if not v:
            return
        # re-apply toolbar-selected tool to the new tab
        if self.act_eraser.isChecked():
            v.set_tool("eraser")
        elif self.act_pen.isChecked():
            v.set_tool("pen")
        elif self.act_line.isChecked():
            v.set_tool("line")
        else:
            v.set_tool("select")

    # ---------------- Scene actions ----------------
    def _current_view(self) -> WhiteboardView | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, WhiteboardView) else None

    def _current_scene(self) -> WhiteboardScene | None:
        v = self._current_view()
        return v.scene() if v else None

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

    def _scale_selected(self, factor: float):
        sc = self._current_scene()
        if not sc:
            return
        from items import PixmapItem, LabelItem
        for it in sc.selectedItems():
            if isinstance(it, PixmapItem):
                it.setScale(max(0.1, min(10.0, it.scale() * factor)))
            elif isinstance(it, LabelItem):
                f = it.font()
                s = f.pointSizeF() if f.pointSizeF() > 0 else 12.0
                f.setPointSizeF(max(6.0, min(96.0, s * factor)))
                it.setFont(f)

    def _export_png_current(self):
        view = self._current_view()
        sc = self._current_scene()
        if not (view and sc):
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "diagram.png", "PNG (*.png)")
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

    def _export_latex_current(self):
        """Export the current scene as a standalone LaTeX document using TikZ."""
        view = self._current_view()
        sc = self._current_scene()
        if not (view and sc):
            return

        from latex_export import scene_to_tikz

        # Ask user for destination .tex file
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export LaTeX",
            "diagram.tex",
            "TeX files (*.tex);;All files (*)",
        )
        if not path:
            return

        # Use the last path component of assets_dir, e.g. ".../project/assets" → "assets"
        image_dir_name = os.path.basename(self.assets_dir) or "assets"

        tikz_body = scene_to_tikz(sc, image_dir=image_dir_name)

        # Wrap into a minimal standalone document
        doc = (
            r"\documentclass[tikz,border=5pt]{standalone}" "\n"
            r"\usepackage{graphicx}" "\n"
            r"\usepackage{circuitikz}" "\n"
            r"\begin{document}" "\n"
            + tikz_body +
            r"\end{document}" "\n"
        )

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(doc)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export LaTeX",
                f"Could not write file:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Export LaTeX",
            "LaTeX file exported.\nCompile it with (pdf|xe|lua)latex to get the diagram."
        )


def main():
    app = QApplication(sys.argv)
    root = os.path.dirname(os.path.abspath(__file__))  # src/
    project_root = os.path.dirname(root)               # project root
    win = MainWindow(project_root=project_root)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
