# -*- coding: utf-8 -*-
"""
Carte mentale : on écrit un plan (une idée par ligne, retrait = sous-idée),
la carte radiale est construite automatiquement puis posée sur le tableau.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen

BRANCH_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#9333ea", "#0891b2", "#db2777", "#65a30d"]


def parse_outline(text):
    """
    « Idée centrale » sur la 1re ligne, puis une branche par ligne.
    Retrait (espaces, tabulation ou tirets « - ») = sous-branche.
    """
    lines = [l.rstrip() for l in text.replace("\t", "    ").splitlines() if l.strip()]
    if not lines:
        return None

    def level(l):
        stripped = l.lstrip(" ")
        n = (len(l) - len(stripped)) // 2
        while stripped.startswith(("-", "•", "*")):
            n += 1
            stripped = stripped[1:].lstrip()
        return n, stripped.strip()

    root = {"t": level(lines[0])[1], "c": []}
    stack = [(-1, root)]
    for l in lines[1:]:
        n, t = level(l)
        n = max(n, 0)
        while stack and stack[-1][0] >= n:
            stack.pop()
        node = {"t": t, "c": []}
        stack[-1][1]["c"].append(node)
        stack.append((n, node))
    return root


def _font(size, bold=False):
    f = QFont("Segoe UI", 10)
    f.setPixelSize(size)
    f.setBold(bold)
    return f


def layout(item):
    """Positions des nœuds : liste de (x, y, texte, niveau, couleur, parent_xy)."""
    cx, cy = item["p"]
    sc = item.get("s", 1.0)
    root = item["tree"]
    nodes = [(cx, cy, root["t"], 0, "#0f172a", None)]
    kids = root["c"]
    n = len(kids)
    if not n:
        return nodes
    R1, R2, R3 = 260 * sc, 190 * sc, 150 * sc
    sector = 2 * math.pi / n
    for i, b in enumerate(kids):
        a = -math.pi / 2 + i * sector
        col = BRANCH_COLORS[i % len(BRANCH_COLORS)]
        bx, by = cx + R1 * math.cos(a) * 1.25, cy + R1 * math.sin(a)
        nodes.append((bx, by, b["t"], 1, col, (cx, cy)))
        m = len(b["c"])
        span = min(sector * 0.9, math.radians(40) * max(m, 1))
        children = b["c"][::-1] if math.sin(a) > 0.3 else b["c"]   # en bas : garder l'ordre de lecture (gauche → droite)
        for j, c in enumerate(children):
            aa = a + (0 if m == 1 else -span / 2 + j * span / (m - 1))
            x2, y2 = bx + R2 * math.cos(aa) * 1.2, by + R2 * math.sin(aa)
            nodes.append((x2, y2, c["t"], 2, col, (bx, by)))
            k = len(c["c"])
            for q, d in enumerate(c["c"]):
                a3 = aa + (0 if k == 1 else -0.5 + q * 1.0 / (k - 1))
                nodes.append((x2 + R3 * math.cos(a3), y2 + R3 * math.sin(a3), d["t"], 3, col, (x2, y2)))
    return nodes


SIZES = {0: 30, 1: 24, 2: 19, 3: 16}


def _box(x, y, text, lvl, sc):
    fm = QFontMetricsF(_font(int(SIZES[lvl] * sc), lvl < 2))
    r = fm.boundingRect(QRectF(0, 0, 260 * sc, 400), Qt.AlignCenter | Qt.TextWordWrap, text)
    pad = (16 if lvl == 0 else 10) * sc
    return QRectF(x - r.width() / 2 - pad, y - r.height() / 2 - pad / 1.5, r.width() + 2 * pad, r.height() + pad * 1.3)


def mindmap_bounds(item):
    sc = item.get("s", 1.0)
    rect = None
    for x, y, t, lvl, col, par in layout(item):
        b = _box(x, y, t, lvl, sc)
        rect = b if rect is None else rect.united(b)
    return rect or QRectF()


def draw_mindmap(p, item):
    sc = item.get("s", 1.0)
    nodes = layout(item)
    p.setRenderHint(QPainter.Antialiasing, True)
    for x, y, t, lvl, col, par in nodes:           # liens d'abord
        if par is None:
            continue
        path = QPainterPath(QPointF(*par))
        mx = (par[0] + x) / 2
        path.cubicTo(QPointF(mx, par[1]), QPointF(mx, y), QPointF(x, y))
        p.setPen(QPen(QColor(col), max(2, (7 - 2 * lvl) * sc), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    for x, y, t, lvl, col, par in nodes:
        b = _box(x, y, t, lvl, sc)
        c = QColor(col)
        if lvl == 0:
            p.setPen(QPen(c, 3))
            p.setBrush(QColor("#fef3c7"))
            p.drawEllipse(b.adjusted(-10, -6, 10, 6))
        elif lvl == 1:
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(b, 14, 14)
        else:
            light = QColor(c)
            light.setAlpha(40)
            p.setPen(QPen(c, 2))
            p.setBrush(QColor(255, 255, 255))
            p.drawRoundedRect(b, 10, 10)
            p.setBrush(light)
            p.drawRoundedRect(b, 10, 10)
        p.setFont(_font(int(SIZES[lvl] * sc), lvl < 2))
        p.setPen(QColor("white") if lvl == 1 else QColor("#0f172a"))
        p.drawText(b, Qt.AlignCenter | Qt.TextWordWrap, t)
