from __future__ import annotations
from PySide6.QtCore import QRectF

GRID_SIZE = 20
SCENE_BOUNDS = QRectF(-5000, -5000, 10000, 10000)

# Logical item names mapped to asset filenames inside ./assets
ASSET_MAP = {
    "Arrow": "arrow.png",
    "Current source": "current_source.png",
    "resistor": "resistor.png",
    "Text": "textbox.jpg",  # icon for creating text labels
    "Rectangle": "shape_rectangle.png",   # optional icon
    "Ellipse":   "shape_ellipse.png",
    "Voltage Source": "voltage_source.png",
}

# Greek slash/escape map for LabelItem (/alpha, \Delta, etc.)
GREEK_MAP = {
    # lowercase
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",

    # uppercase
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ", "Epsilon": "Ε",
    "Zeta": "Ζ", "Eta": "Η", "Theta": "Θ", "Iota": "Ι", "Kappa": "Κ",
    "Lambda": "Λ", "Mu": "Μ", "Nu": "Ν", "Xi": "Ξ", "Omicron": "Ο",
    "Pi": "Π", "Rho": "Ρ", "Sigma": "Σ", "Tau": "Τ", "Upsilon": "Υ",
    "Phi": "Φ", "Chi": "Χ", "Psi": "Ψ", "Omega": "Ω",
}
