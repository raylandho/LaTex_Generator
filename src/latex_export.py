# latex_export.py
from __future__ import annotations

from typing import List
import math

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsPixmapItem,
    QGraphicsPathItem,
)
from PySide6.QtGui import QPainterPath

from constants import ASSET_MAP

# Optional: used only to ignore the blue transform overlay & handles in export
try:
    from handles import TransformOverlay
except Exception:  # pragma: no cover
    TransformOverlay = None


# ---------- Mapping: palette labels → circuitikz element keys ----------

CIRCUIT_ELEMENT_MAP = {
    # keys must match the *labels* from ASSET_MAP / palette
    "resistor": "R",
    "Capacitor": "C",
    "Inductor": "L",
    "Battery": "battery",
    "Voltage Source": "V",
    "Current source": "I",
    "Ammeter": "ammeter",
    "Voltmeter": "voltmeter",
    "Lightbulb": "lamp",  # adjust if your circuitikz version uses a different name
    # "Time Controlled Switch": "switch",           # enable & tweak if desired
    # "Voltage Controlled Switch": "switch",        # or a more specific element
}


# ---------- Helpers ----------

def _escape_latex(text: str) -> str:
    """
    Escape basic LaTeX special chars so labels compile safely.
    Greek letters are left as-is (XeLaTeX/LuaLaTeX handle them fine).
    """
    replacements = {
        '\\': r'\textbackslash{}',
        '{': r'\{',
        '}': r'\}',
        '$': r'\$',
        '&': r'\&',
        '#': r'\#',
        '_': r'\_',
        '%': r'\%',
        '^': r'\^{}',
        '~': r'\~{}',
    }
    for ch, repl in replacements.items():
        text = text.replace(ch, repl)
    # Newlines → forced line breaks
    text = text.replace("\n", r"\\")
    return text


def _path_to_poly(path: QPainterPath) -> List[QPointF]:
    """
    Convert a QPainterPath into a simple polyline by walking its elements.
    This is good enough for lines, rectangles, ellipses, arcs, and pen strokes.
    """
    pts: List[QPointF] = []
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        pts.append(QPointF(e.x, e.y))

    # De-duplicate consecutive identical points
    dedup: List[QPointF] = []
    for p in pts:
        if not dedup or (p.x() != dedup[-1].x() or p.y() != dedup[-1].y()):
            dedup.append(p)
    return dedup


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


# ---------- Main entry ----------

def scene_to_tikz(scene: QGraphicsScene, image_dir: str = "assets") -> str:
    """
    Convert the current scene contents into a TikZ picture.

    - Coordinates are in *pixels* relative to the diagram's bounding box.
    - We set [x=0.05cm, y=0.05cm], so 1 px ~ 0.05 cm (tweak as needed).
    - Supports:
        * Lines (QGraphicsLineItem)
        * Rectangles / ellipses (approx. by polylines)
        * Freehand pen strokes (selectable QGraphicsPathItem)
        * Text labels (QGraphicsTextItem)
        * Pixmaps:
            - Known labels → circuitikz elements (to[R], to[C], etc.)
            - Others → \\includegraphics from `image_dir` + ASSET_MAP
    - Ignores:
        * The blue transform overlay + its handles (TransformOverlay)
        * Non-selectable helper items (eraser circle, arc previews, etc.)
    """
    items = [it for it in scene.items() if it.isVisible()]
    if not items:
        return "\\begin{tikzpicture}\n% empty diagram\n\\end{tikzpicture}\n"

    # Bounding box of all visible items; anchor coordinates here
    bounds = scene.itemsBoundingRect()
    origin_x = bounds.left()
    origin_y = bounds.bottom()  # flip Y so TikZ Y goes "up"

    def fmt_point(p: QPointF) -> str:
        """Convert a scene point into TikZ coordinates (pixels)."""
        x = p.x() - origin_x
        y = origin_y - p.y()
        return f"({x:.2f},{y:.2f})"

    lines: List[str] = []
    lines.append(r"\begin{tikzpicture}[x=0.05cm,y=0.05cm]")
    lines.append(
        f"% scene bounds: left={bounds.left():.1f}, top={bounds.top():.1f}, "
        f"right={bounds.right():.1f}, bottom={bounds.bottom():.1f}"
    )

    # Draw from back to front (reverse of Qt’s default items() order)
    for it in reversed(items):
        # Skip the blue overlay and its handles (if present)
        if TransformOverlay is not None:
            if isinstance(it, TransformOverlay):
                continue
            if it.parentItem() is not None and isinstance(it.parentItem(), TransformOverlay):
                continue

        # ---------- Pixmaps → circuitikz or includegraphics ----------
        if isinstance(it, QGraphicsPixmapItem):
            label = it.data(0)
            center = it.mapToScene(it.boundingRect().center())

            if isinstance(label, str) and label in CIRCUIT_ELEMENT_MAP:
                # Use circuitikz element instead of PNG
                elem = CIRCUIT_ELEMENT_MAP[label]

                br = it.boundingRect()

                # Midpoints of each side in *local* coords
                left_mid_local  = QPointF(br.left(), (br.top() + br.bottom()) / 2.0)
                right_mid_local = QPointF(br.right(), (br.top() + br.bottom()) / 2.0)
                top_mid_local   = QPointF((br.left() + br.right()) / 2.0, br.top())
                bot_mid_local   = QPointF((br.left() + br.right()) / 2.0, br.bottom())

                # Map to scene
                p_left  = it.mapToScene(left_mid_local)
                p_right = it.mapToScene(right_mid_local)
                p_top   = it.mapToScene(top_mid_local)
                p_bot   = it.mapToScene(bot_mid_local)

                # Pick the longer of horizontal/vertical spans as the element orientation
                d_h = _dist(p_left, p_right)
                d_v = _dist(p_top, p_bot)
                if d_h >= d_v:
                    p1, p2 = p_left, p_right
                else:
                    p1, p2 = p_top, p_bot

                t1 = fmt_point(p1)
                t2 = fmt_point(p2)
                lines.append(rf"  \draw {t1} to[{elem}] {t2};")
                continue

            # Fallback: generic image node
            p = fmt_point(center)
            filename = ASSET_MAP.get(label, None) if label is not None else None
            if filename:
                tex_img = f"{image_dir}/{filename}"
                lines.append(
                    rf"  \node at {p} {{\includegraphics[width=2cm]{{{tex_img}}}}};"
                )
            else:
                lines.append(
                    rf"  % image at {p} (no filename metadata; edit manually)"
                )
            continue

        # ---------- Text labels ----------
        if isinstance(it, QGraphicsTextItem):
            center = it.mapToScene(it.boundingRect().center())
            p = fmt_point(center)
            text = _escape_latex(it.toPlainText())
            lines.append(rf"  \node[anchor=center] at {p} {{{text}}};")
            continue

        # ---------- Straight lines ----------
        if isinstance(it, QGraphicsLineItem):
            line = it.line()
            p1 = fmt_point(it.mapToScene(line.p1()))
            p2 = fmt_point(it.mapToScene(line.p2()))
            lines.append(rf"  \draw {p1} -- {p2};")
            continue

        # ---------- Rectangles (content ones only) ----------
        if isinstance(it, QGraphicsRectItem):
            # Only export if it's meant to be content (selectable)
            if not bool(it.flags() & QGraphicsItem.ItemIsSelectable):
                continue
            path = it.mapToScene(it.shape())
            pts = _path_to_poly(path)
            if len(pts) >= 2:
                seq = " -- ".join(fmt_point(p) for p in pts)
                lines.append(rf"  \draw {seq};")
            continue

        # ---------- Ellipses / circles (content ones only) ----------
        if isinstance(it, QGraphicsEllipseItem):
            if not bool(it.flags() & QGraphicsItem.ItemIsSelectable):
                continue
            path = it.mapToScene(it.shape())
            pts = _path_to_poly(path)
            if len(pts) >= 2:
                seq = " -- ".join(fmt_point(p) for p in pts)
                lines.append(rf"  \draw {seq};  % ellipse approximation")
            continue

        # ---------- Paths (pen strokes, arcs, etc.) ----------
        if isinstance(it, QGraphicsPathItem):
            # Heuristic: only export selectable paths (pen strokes, arcs),
            # not helper overlays or previews
            if not bool(it.flags() & QGraphicsItem.ItemIsSelectable):
                continue
            path = it.mapToScene(it.path())
            pts = _path_to_poly(path)
            if len(pts) >= 2:
                seq = " -- ".join(fmt_point(p) for p in pts)
                lines.append(rf"  \draw {seq};  % freehand/arc path")
            continue

        # Fallback: document that we skipped some odd item
        lines.append(f"% [ignored item type: {type(it).__name__}]")

    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines) + "\n"
