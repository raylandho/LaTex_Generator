from __future__ import annotations
import os
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QPixmap, QIcon   # <-- add QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from constants import ASSET_MAP

MIME_TYPE = "application/x-physdraw-item"


class Palette(QListWidget):
    def __init__(self, assets_dir: str):
        super().__init__()
        self.assets_dir = assets_dir
        self.setDragEnabled(True)
        self.setViewMode(QListWidget.IconMode)
        self.setSpacing(8)
        self.setIconSize(QPixmap(48, 48).size())
        self.setFixedWidth(160)
        self.setResizeMode(QListWidget.Adjust)
        self.populate()

    def populate(self):
        for label, filename in ASSET_MAP.items():
            item = QListWidgetItem(label)
            pix = QPixmap(os.path.join(self.assets_dir, filename))
            if not pix.isNull():
                # Use a QIcon, not a scaled QPixmap
                item.setIcon(QIcon(pix))
            item.setData(Qt.UserRole, label)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.addItem(item)

    def startDrag(self, supportedActions):
        it = self.currentItem()
        if not it:
            return
        mime = QMimeData()
        mime.setData(MIME_TYPE, it.data(Qt.UserRole).encode("utf-8"))

        drag = QDrag(self)
        drag.setMimeData(mime)

        # Prefer the QListWidgetItem's QIcon
        icon = it.icon()
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(48, 48))
        else:
            # Fallback: load from assets directly
            label = it.data(Qt.UserRole)
            filename = ASSET_MAP.get(label)
            if filename:
                pix = QPixmap(os.path.join(self.assets_dir, filename))
                if not pix.isNull():
                    drag.setPixmap(pix.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        drag.exec(Qt.CopyAction)
