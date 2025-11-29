# latex_export.py
from __future__ import annotations

from typing import List, Tuple
import math

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsTextItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
)
from PySide6.QtGui import QPainterPath

from constants import ASSET_MAP  # not used directly, but fine to keep


# Optional: used only to ignore the blue transform overlay & handles
try:
    from handles import TransformOverlay
except Exception:  # pragma: no cover
    TransformOverlay = None


# ---------- Mapping: palette labels → (circuitikz element, default label) ----------

# default_label is what we put inside the circle via "l=...".
# For plain elements (resistor, capacitor, etc.) we use None.
CIRCUIT_ELEMENT_MAP: dict[str, Tuple[str, str | None]] = {
    "resistor": ("R", None),
    "Capacitor": ("C", None),
    "Inductor": ("L", None),
    "Battery": ("battery", None),

    # Sources & meters: give them a visible letter inside the circle
    "Voltage Source": ("V", "V"),
    "Current source": ("I", "I"),
    "Ammeter": ("ammeter", "A"),
    "Voltmeter": ("voltmeter", "V"),

    "Lightbulb": ("lamp", None),  # classic lamp symbol
    # Other icons (switches, probe, etc.) are handled as generic boxes below.
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
    This is good enough for rectangles, ellipses, arcs, and pen strokes.
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

    NOTE: This version does **not** use PNGs in LaTeX at all.
    Everything is vector (TikZ + circuitikz), so the .tex file is
    completely self-contained.

    - Coordinates are in *pixels* relative to the diagram's bounding box.
    - We set [x=0.05cm, y=0.05cm], so 1 px ~ 0.05 cm (tweak as needed).
    - Supports:
        * Pixmaps with known labels → circuitikz elements (to[R], to[C], etc.),
          with default labels for sources/meters so circles aren’t empty.
        * Other pixmaps → drawn boxes with the label text inside
        * Text labels (QGraphicsTextItem)
        * Wires: QGraphicsLineItem → single \draw p1 -- p2;
        * Other drawable items via their shape() as polylines
    - Ignores:
        * The blue transform overlay + its handles (TransformOverlay)
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

        # ---------- Pixmaps → circuitikz or generic TikZ node ----------
        if isinstance(it, QGraphicsPixmapItem):
            label = it.data(0)
            center = it.mapToScene(it.boundingRect().center())
            p = fmt_point(center)

            # 1) Known circuit elements → circuitikz with optional default label
            if isinstance(label, str) and label in CIRCUIT_ELEMENT_MAP:
                elem, default_label = CIRCUIT_ELEMENT_MAP[label]

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

                # Build the style: "elem" or "elem, l=V" etc.
                if default_label:
                    style = f"{elem}, l={default_label}"
                else:
                    style = elem

                lines.append(rf"  \draw {t1} to[{style}] {t2};")
                continue

            # 2) Everything else → generic drawn box with label text
            label_text = _escape_latex(str(label)) if label is not None else "?"
            br = it.boundingRect()
            # Convert px size to cm based on x=0.05cm scaling
            w_cm = br.width() * 0.05
            h_cm = br.height() * 0.05
            lines.append(
                rf"  \node[draw,align=center,minimum width={w_cm:.2f}cm,"
                rf" minimum height={h_cm:.2f}cm] at {p} {{{label_text}}};"
            )
            continue

        # ---------- Text labels ----------
        if isinstance(it, QGraphicsTextItem):
            center = it.mapToScene(it.boundingRect().center())
            p = fmt_point(center)
            text = _escape_latex(it.toPlainText())
            lines.append(rf"  \node[anchor=center] at {p} {{{text}}};")
            continue

        # ---------- Wires: QGraphicsLineItem → single centerline ----------
        if isinstance(it, QGraphicsLineItem):
            line = it.line()
            p1 = fmt_point(it.mapToScene(line.p1()))
            p2 = fmt_point(it.mapToScene(line.p2()))
            lines.append(rf"  \draw {p1} -- {p2};")
            continue

        # ---------- Rectangles / Ellipses / Paths: export shape() polyline ----------
        if isinstance(it, (QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPathItem)):
            try:
                path = it.mapToScene(it.shape())
            except Exception:
                lines.append(f"% [ignored item type (no shape): {type(it).__name__}]")
                continue

            pts = _path_to_poly(path)
            if len(pts) >= 2:
                seq = " -- ".join(fmt_point(p) for p in pts)
                lines.append(rf"  \draw {seq};  % {type(it).__name__} shape")
            else:
                lines.append(f"% [shape too small: {type(it).__name__}]")
            continue

        # Fallback: document that we skipped some odd item
        lines.append(f"% [ignored item type: {type(it).__name__}]")

    lines.append(r"\end{tikzpicture}")
    return "\n".join(lines) + "\n"
