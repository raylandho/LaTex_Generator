from __future__ import annotations
import os
from PySide6.QtCore import Qt, QMimeData, QSize
from PySide6.QtGui import QDrag, QPixmap, QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from constants import ASSET_MAP

MIME_TYPE = "application/x-physdraw-item"


class Palette(QListWidget):
    """
    Simple, compact palette:
      - Black background (like before)
      - 2 columns, neat grid
      - Same drag payload (label via MIME_TYPE)
    """
    def __init__(self, assets_dir: str):
        super().__init__()
        self.assets_dir = assets_dir

        # ---- Layout: 2-column grid ----
        icon_px = 48
        self._columns = 2
        self._spacing = 6
        self._cell = QSize(96, 84)  # per-item cell (w x h) — tweak if needed

        self.setViewMode(QListWidget.IconMode)
        self.setWrapping(True)
        self.setUniformItemSizes(True)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)  # no accidental reordering
        self.setSpacing(self._spacing)
        self.setGridSize(self._cell)
        self.setIconSize(QSize(icon_px, icon_px))

        # Compute a fixed width for exactly 2 columns
        # width = 2 * cell_w + (2-1)*spacing + small padding
        pad = 12
        self.setFixedWidth(self._columns * self._cell.width() + (self._columns - 1) * self._spacing + pad)

        # ---- Visuals: black background, light text ----
        self.setStyleSheet("""
            QListWidget {
                background: #111;
                color: #ddd;
                border: none;
            }
            QListWidget::item {
                padding: 4px;
            }
            QListWidget::item:selected {
                background: #2a2a2a;
                color: #fff;
            }
        """)

        self.setDragEnabled(True)
        self.populate()

    # ---------------- Data ----------------
    def populate(self):
        self.clear()
        for label, filename in ASSET_MAP.items():
            item = QListWidgetItem(label)
            pix = QPixmap(os.path.join(self.assets_dir, filename))
            if not pix.isNull():
                item.setIcon(QIcon(pix))
            item.setData(Qt.UserRole, label)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            # ensure each item takes exactly one grid cell
            item.setSizeHint(self._cell)
            self.addItem(item)

    # ---------------- Drag & drop ----------------
    def startDrag(self, supportedActions):
        it = self.currentItem()
        if not it:
            return

        label = it.data(Qt.UserRole)
        if not label:
            return

        mime = QMimeData()
        mime.setData(MIME_TYPE, str(label).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime)

        # Prefer the QListWidgetItem's QIcon for a crisp drag pixmap
        icon = it.icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(self.iconSize()))
        else:
            # Fallback: load from assets directly
            filename = ASSET_MAP.get(label)
            if filename:
                pix = QPixmap(os.path.join(self.assets_dir, filename))
                if not pix.isNull():
                    drag.setPixmap(pix.scaled(self.iconSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

        drag.exec(Qt.CopyAction)
