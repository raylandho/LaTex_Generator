from __future__ import annotations
from PySide6.QtCore import QRectF


GRID_SIZE = 20
SCENE_BOUNDS = QRectF(-5000, -5000, 10000, 10000)


# Logical item names mapped to asset filenames inside ./assets
ASSET_MAP = {
"Arrow": "arrow.png",
"Block": "block.png",
"Spring": "spring.jpg",
"Text": "textbox.jpg", # icon for creating text labels
}