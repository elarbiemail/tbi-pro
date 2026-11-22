# -*- coding: utf-8 -*-
"""
Surface d'écriture multi-stylets : sert au tableau blanc (avec pages et fonds)
et à l'annotation par-dessus l'écran (fond transparent).

Chaque stylet (identifié par une clé : couleur de sa LED, « souris »…) garde son
propre outil, sa couleur et son épaisseur : deux élèves peuvent écrire en même
temps avec des réglages différents.
"""
import base64
import json
import math
import os
import threading
import time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QPointF, QRect, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter,
                           QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QWidget

from . import instruments as instr
from . import recognize
from .mindmap import draw_mindmap, mindmap_bounds

BACKGROUNDS = ["blanc", "quadrillage", "seyes", "lignes", "points", "millimetre", "repere", "portee", "ardoise", "noir"]
BG_LABELS = {"blanc": "Blanc", "quadrillage": "Quadrillage", "seyes": "Seyès", "lignes": "Lignes",
             "points": "Points", "millimetre": "Papier millimétré", "repere": "Repère orthonormé",
             "portee": "Portées musicales", "ardoise": "Ardoise verte", "noir": "Noir"}
PALETTE = ["#1e3a8a", "#111827", "#dc2626", "#16a34a", "#2563eb", "#f59e0b", "#9333ea", "#ffffff"]
WIDTHS = {"fin": 3, "moyen": 6, "epais": 12}
DEFAULT_INK = {"rouge": "#dc2626", "vert": "#16a34a", "bleu": "#2563eb"}
SHAPES = ("line", "arrow", "rect", "ellipse", "triangle", "star")
FILLABLE = ("rect", "ellipse", "triangle", "star", "poly")
TEXT_FLAGS = int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)


def text_font(size):
    f = QFont("Segoe UI", 10)
    f.setPixelSize(max(8, int(size)))
    return f


def text_rect(it):
    fm = QFontMetricsF(text_font(it["s"]))
    r = fm.boundingRect(QRectF(0, 0, it.get("wmax", 1400), 4000), TEXT_FLAGS, it["t"])
    return QRectF(it["p"][0], it["p"][1], r.width(), r.height())


class ToolState:
    def __init__(self, color="#1e3a8a"):
        self.tool = "pen"          # pen, marker, eraser, select, handwrite, magic, text, compass, formes…
        self.color = color
        self.width = WIDTHS["moyen"]
        self.fill = False          # formes pleines


def new_page(size, bg="blanc"):
    return {"bg": bg, "size": [size[0], size[1]], "items": [], "undo": [], "redo": []}


# ----------------------------------------------------------------------------
# Fonds de page
# ----------------------------------------------------------------------------
def _bg_image(page):
    img = page.get("_bgimg")
    if img is None and page.get("bgimg"):
        img = QImage()
        img.loadFromData(QByteArray(base64.b64decode(page["bgimg"])))
        page["_bgimg"] = img
    return img


def draw_background(p, page, w, h, transparent=False):
    if transparent:
        return
    bg = page.get("bg", "blanc")
    colors = {"ardoise": "#1f3d2b", "noir": "#111111"}
    p.fillRect(QRectF(0, 0, w, h), QColor(colors.get(bg, "#ffffff")))
    img = _bg_image(page)
    if img is not None and not img.isNull():              # page importée (PDF, image de fond)
        s = min(w / img.width(), h / img.height())
        iw, ih = img.width() * s, img.height() * s
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(QRectF((w - iw) / 2, (h - ih) / 2, iw, ih), img)
        return
    if bg == "quadrillage":
        p.setPen(QPen(QColor("#cbd5e1"), 1))
        step = 30
        for x in range(step, int(w), step):
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        for y in range(step, int(h), step):
            p.drawLine(QPointF(0, y), QPointF(w, y))
    elif bg == "seyes":
        u = 10                                  # interligne fin (réglure Seyès : 4 fins par grand carreau)
        major = 4 * u
        thin, thick = QPen(QColor("#c7d2fe"), 1), QPen(QColor("#818cf8"), 1.4)
        for i, y in enumerate(range(major, int(h), u)):
            p.setPen(thick if i % 4 == 0 else thin)
            p.drawLine(QPointF(0, y), QPointF(w, y))
        p.setPen(thick)
        margin = 3 * major
        for x in range(margin + major, int(w), major):
            p.drawLine(QPointF(x, major), QPointF(x, h))
        p.setPen(QPen(QColor("#ef4444"), 1.6))
        p.drawLine(QPointF(margin, 0), QPointF(margin, h))
    elif bg == "lignes":
        p.setPen(QPen(QColor("#94a3b8"), 1))
        for y in range(48, int(h), 48):
            p.drawLine(QPointF(0, y), QPointF(w, y))
    elif bg == "points":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#94a3b8"))
        for x in range(30, int(w), 30):
            for y in range(30, int(h), 30):
                p.drawEllipse(QPointF(x, y), 1.6, 1.6)
    elif bg == "millimetre":
        mm = 3.78
        for i in range(int(w / mm) + 1):
            p.setPen(QPen(QColor("#f59e0b" if i % 10 == 0 else "#fde68a"), 1.2 if i % 10 == 0 else 0.5))
            p.drawLine(QPointF(i * mm, 0), QPointF(i * mm, h))
        for i in range(int(h / mm) + 1):
            p.setPen(QPen(QColor("#f59e0b" if i % 10 == 0 else "#fde68a"), 1.2 if i % 10 == 0 else 0.5))
            p.drawLine(QPointF(0, i * mm), QPointF(w, i * mm))
    elif bg == "repere":
        u = 40
        cx, cy = (w // 2 // u) * u, (h // 2 // u) * u
        p.setPen(QPen(QColor("#e2e8f0"), 1))
        for x in range(int(cx % u), int(w), u):
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        for y in range(int(cy % u), int(h), u):
            p.drawLine(QPointF(0, y), QPointF(w, y))
        p.setPen(QPen(QColor("#0f172a"), 2))
        p.drawLine(QPointF(0, cy), QPointF(w, cy))
        p.drawLine(QPointF(cx, 0), QPointF(cx, h))
        p.setBrush(QColor("#0f172a"))
        p.drawPolygon(QPolygonF([QPointF(w - 2, cy), QPointF(w - 14, cy - 6), QPointF(w - 14, cy + 6)]))
        p.drawPolygon(QPolygonF([QPointF(cx, 2), QPointF(cx - 6, 14), QPointF(cx + 6, 14)]))
        p.setFont(text_font(13))
        for i in range(-int(cx // u), int((w - cx) // u) + 1):
            if i:
                p.drawLine(QPointF(cx + i * u, cy - 4), QPointF(cx + i * u, cy + 4))
                p.drawText(QRectF(cx + i * u - 15, cy + 6, 30, 18), Qt.AlignCenter, str(i))
        for j in range(-int(cy // u), int((h - cy) // u) + 1):
            if j:
                p.drawLine(QPointF(cx - 4, cy + j * u), QPointF(cx + 4, cy + j * u))
                p.drawText(QRectF(cx - 36, cy + j * u - 9, 28, 18), Qt.AlignRight | Qt.AlignVCenter, str(-j))
        p.drawText(QRectF(cx - 22, cy + 4, 18, 18), Qt.AlignCenter, "O")
        p.drawText(QRectF(w - 30, cy - 26, 24, 20), Qt.AlignCenter, "x")
        p.drawText(QRectF(cx + 8, 4, 24, 20), Qt.AlignCenter, "y")
    elif bg == "portee":
        gap, staff = 14, 14 * 4
        p.setPen(QPen(QColor("#334155"), 1.2))
        y = 70
        while y + staff < h - 30:
            for i in range(5):
                p.drawLine(QPointF(40, y + i * gap), QPointF(w - 40, y + i * gap))
            p.drawLine(QPointF(40, y), QPointF(40, y + staff))
            p.drawLine(QPointF(w - 40, y), QPointF(w - 40, y + staff))
            y += staff + 70


def item_image(it):
    img = it.get("_img")
    if img is None:
        img = QImage()
        img.loadFromData(QByteArray(base64.b64decode(it["data"])))
        it["_img"] = img
    return img


def shape_polygon(k, x1, y1, x2, y2):
    """Sommets d'un triangle (isocèle) ou d'une étoile à 5 branches inscrits dans le rectangle."""
    l, r, t, b = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
    if k == "triangle":
        return [((l + r) / 2, t), (r, b), (l, b)]
    cx, cy, rx, ry = (l + r) / 2, (t + b) / 2, (r - l) / 2, (b - t) / 2
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        f = 1.0 if i % 2 == 0 else 0.42
        pts.append((cx + rx * f * math.cos(a), cy + ry * f * math.sin(a)))
    return pts


# ----------------------------------------------------------------------------
# Transformations : chaque objet peut être agrandi (scl) et pivoté (rot, degrés)
# autour du centre de son cadre.
# ----------------------------------------------------------------------------
def local_bounds(it):
    k = it["k"]
    if k == "image":
        x, y, w, h = it["r"]
        return QRectF(x, y, w, h + (18 if it.get("credit") else 0))
    if k == "text":
        return text_rect(it)
    if k == "mindmap":
        return mindmap_bounds(it)
    hw = it.get("w", 4) / 2 + 2
    if k in ("stroke", "poly"):
        xs = [p[0] for p in it["pts"]]
        ys = [p[1] for p in it["pts"]]
        return QRectF(min(xs) - hw, min(ys) - hw, max(xs) - min(xs) + 2 * hw, max(ys) - min(ys) + 2 * hw)
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    extra = max(14, it.get("w", 4) * 3.5) if k == "arrow" else 0
    return QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized().adjusted(-hw - extra, -hw - extra, hw + extra, hw + extra)


def is_transformed(it):
    return bool(it.get("rot")) or abs(it.get("scl", 1.0) - 1.0) > 1e-6


def pivot(it):
    c = local_bounds(it).center()
    return c.x(), c.y()


def to_item_local(it, x, y):
    """Point de la page → repère de l'objet (avant rotation / agrandissement)."""
    if not is_transformed(it):
        return x, y
    cx, cy = pivot(it)
    a = -math.radians(it.get("rot", 0.0))
    s = it.get("scl", 1.0) or 1.0
    dx, dy = x - cx, y - cy
    return cx + (dx * math.cos(a) - dy * math.sin(a)) / s, cy + (dx * math.sin(a) + dy * math.cos(a)) / s


def to_page_point(it, x, y):
    if not is_transformed(it):
        return x, y
    cx, cy = pivot(it)
    a = math.radians(it.get("rot", 0.0))
    s = it.get("scl", 1.0)
    dx, dy = (x - cx) * s, (y - cy) * s
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def world_corners(it):
    b = local_bounds(it)
    return [to_page_point(it, b.left(), b.top()), to_page_point(it, b.right(), b.top()),
            to_page_point(it, b.right(), b.bottom()), to_page_point(it, b.left(), b.bottom())]


def draw_item(p, it):
    if is_transformed(it):
        cx, cy = pivot(it)
        p.save()
        p.translate(cx, cy)
        p.rotate(it.get("rot", 0.0))
        s = it.get("scl", 1.0)
        p.scale(s, s)
        p.translate(-cx, -cy)
        _draw_raw(p, it)
        p.restore()
    else:
        _draw_raw(p, it)


def _draw_raw(p, it):
    k = it["k"]
    if k == "image":
        x, y, w, h = it["r"]
        p.drawImage(QRectF(x, y, w, h), item_image(it))
        if it.get("credit"):                       # crédit obligatoire des images sous licence libre
            p.setFont(text_font(11))
            p.setPen(QColor(100, 116, 139))
            p.drawText(QRectF(x, y + h + 2, max(w, 260), 16), Qt.AlignLeft | Qt.AlignTop, it["credit"])
        return
    if k == "text":
        p.setFont(text_font(it["s"]))
        p.setPen(QColor(it["c"]))
        p.drawText(text_rect(it), TEXT_FLAGS, it["t"])
        return
    if k == "mindmap":
        draw_mindmap(p, it)
        return
    col = QColor(it["c"])
    col.setAlpha(it.get("a", 255))
    pen = QPen(col, it["w"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    if it.get("fill") and k in FILLABLE:
        fc = QColor(it["c"])
        fc.setAlpha(150)
        p.setBrush(fc)
    else:
        p.setBrush(Qt.NoBrush)
    if k == "stroke":
        pts = it["pts"]
        if len(pts) == 1:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(*pts[0]), it["w"] / 2, it["w"] / 2)
            return
        path = QPainterPath(QPointF(*pts[0]))
        if len(pts) == 2:
            path.lineTo(QPointF(*pts[1]))
        else:  # lissage : courbes passant par les milieux des segments
            for i in range(1, len(pts) - 1):
                mid = QPointF((pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2)
                path.quadTo(QPointF(*pts[i]), mid)
            path.lineTo(QPointF(*pts[-1]))
        p.drawPath(path)
        return
    if k == "poly":
        p.drawPolygon(QPolygonF([QPointF(*q) for q in it["pts"]]))
        return
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    if k == "line":
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    elif k == "arrow":
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        ang = math.atan2(y2 - y1, x2 - x1)
        L = max(14, it["w"] * 3.5)
        a1 = QPointF(x2 - L * math.cos(ang - 0.45), y2 - L * math.sin(ang - 0.45))
        a2 = QPointF(x2 - L * math.cos(ang + 0.45), y2 - L * math.sin(ang + 0.45))
        p.setBrush(col)
        p.drawPolygon(QPolygonF([QPointF(x2, y2), a1, a2]))
    elif k == "rect":
        p.drawRect(QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized())
    elif k == "ellipse":
        p.drawEllipse(QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized())
    elif k in ("triangle", "star"):
        p.drawPolygon(QPolygonF([QPointF(*q) for q in shape_polygon(k, x1, y1, x2, y2)]))


def render_page(p, page, transparent=False, frozen=None):
    w, h = page["size"]
    draw_background(p, page, w, h, transparent and frozen is None)
    if frozen is not None:
        p.drawPixmap(QRectF(0, 0, w, h), frozen, QRectF(frozen.rect()))
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    for it in page["items"]:
        draw_item(p, it)


# ----------------------------------------------------------------------------
# Géométrie (gomme, sélection)
# ----------------------------------------------------------------------------
def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _poly_hit(pts, x, y, rr, filled):
    n = len(pts)
    if any(_seg_dist(x, y, *pts[i], *pts[(i + 1) % n]) <= rr for i in range(n)):
        return True
    if filled:
        inside, j = False, n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi:
                inside = not inside
            j = i
        return inside
    return False


def hit(it, x, y, r):
    if is_transformed(it):
        x, y = to_item_local(it, x, y)
        r = r / (it.get("scl", 1.0) or 1.0)
    k = it["k"]
    if k == "image":
        X, Y, W, H = it["r"]
        return X - r <= x <= X + W + r and Y - r <= y <= Y + H + r
    if k == "text":
        return text_rect(it).adjusted(-r, -r, r, r).contains(QPointF(x, y))
    if k == "mindmap":
        return mindmap_bounds(it).adjusted(-r, -r, r, r).contains(QPointF(x, y))
    rr = r + it["w"] / 2
    if k == "stroke":
        pts = it["pts"]
        if len(pts) == 1:
            return math.hypot(x - pts[0][0], y - pts[0][1]) <= rr
        return any(_seg_dist(x, y, *pts[i], *pts[i + 1]) <= rr for i in range(len(pts) - 1))
    if k == "poly":
        return _poly_hit(it["pts"], x, y, rr, it.get("fill"))
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    if k in ("line", "arrow"):
        return _seg_dist(x, y, x1, y1, x2, y2) <= rr
    l, rgt, t, b = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
    if k == "rect":
        if it.get("fill") and l <= x <= rgt and t <= y <= b:
            return True
        edges = [(l, t, rgt, t), (rgt, t, rgt, b), (rgt, b, l, b), (l, b, l, t)]
        return any(_seg_dist(x, y, *e) <= rr for e in edges)
    if k == "ellipse":
        cx, cy, ax, ay = (l + rgt) / 2, (t + b) / 2, max((rgt - l) / 2, 1), max((b - t) / 2, 1)
        d = math.hypot((x - cx) / ax, (y - cy) / ay)
        return (it.get("fill") and d <= 1) or abs(d - 1) * min(ax, ay) <= rr
    if k in ("triangle", "star"):
        return _poly_hit(shape_polygon(k, x1, y1, x2, y2), x, y, rr, it.get("fill"))
    return False


def translate(it, dx, dy):
    k = it["k"]
    if k == "image":
        it["r"] = [it["r"][0] + dx, it["r"][1] + dy, it["r"][2], it["r"][3]]
    elif k in ("text", "mindmap"):
        it["p"] = [it["p"][0] + dx, it["p"][1] + dy]
    elif k in ("stroke", "poly"):
        it["pts"] = [[x + dx, y + dy] for x, y in it["pts"]]
    else:
        it["p1"] = [it["p1"][0] + dx, it["p1"][1] + dy]
        it["p2"] = [it["p2"][0] + dx, it["p2"][1] + dy]


def clone(it):
    c = {k: (v.copy() if isinstance(v, list) else v) for k, v in it.items()}
    if "pts" in c:
        c["pts"] = [list(p) for p in it["pts"]]
    if "tree" in it:
        c["tree"] = json.loads(json.dumps(it["tree"]))
    if "_img" in it:
        c["_img"] = it["_img"]
    return c


# ----------------------------------------------------------------------------
# Widget
# ----------------------------------------------------------------------------
class InkCanvas(QWidget):
    changed = Signal()          # contenu modifié (pour rafraîchir la barre d'outils)
    text_requested = Signal(object, str)   # position (page), clé du stylet : saisir un texte
    edit_text_requested = Signal(object)   # objet texte à modifier
    _hw_done = Signal(object, object)

    def __init__(self, transparent=False, parent=None):
        super().__init__(parent)
        self.transparent = transparent
        self.pages = []
        self.index = 0
        self.tools = {}
        self.active = {}        # id pointeur → geste en cours
        self.frozen = None      # mode annotation : image de l'écran « figé »
        self.hovers = {}        # id pointeur → position (doigt visible sans appui)
        self.instruments = []   # règle, équerre, rapporteur, projecteur, rideau
        self.selected = None    # objet sélectionné (outil Sélection)
        self._hw_group = []     # traits du stylo « écriture → texte » en attente
        self._hw_timer = QTimer(self, singleShot=True, interval=1400, timeout=self._hw_recognize)
        self._hw_done.connect(self._hw_apply)
        self._cache = None
        self._toast, self._toast_t = "", 0
        self.setAttribute(Qt.WA_OpaquePaintEvent, not transparent)
        self.setMouseTracking(False)
        QTimer.singleShot(0, self._ensure_page)

    # -------------------------------------------------------------- pages
    def _ensure_page(self):
        if not self.pages:
            self.pages.append(new_page((max(self.width(), 800), max(self.height(), 600))))
            self.index = 0

    @property
    def page(self):
        self._ensure_page()
        return self.pages[self.index]

    def go_page(self, i):
        self.cancel_all()
        self.selected = None
        self.index = max(0, min(len(self.pages) - 1, i))
        self.invalidate()

    def add_page(self):
        self.cancel_all()
        cur = self.page
        self.pages.insert(self.index + 1, new_page(cur["size"], cur["bg"]))
        self.index += 1
        self.invalidate()

    def delete_page(self):
        if len(self.pages) <= 1:
            self.clear_page()
            return
        self.cancel_all()
        del self.pages[self.index]
        self.index = min(self.index, len(self.pages) - 1)
        self.invalidate()

    def cycle_background(self):
        if self.page.get("bgimg"):                  # page importée (PDF) : le fond est la diapositive
            self.toast("Page importée : fond non modifiable")
            return
        bg = self.page["bg"]
        self.page["bg"] = BACKGROUNDS[(BACKGROUNDS.index(bg) + 1) % len(BACKGROUNDS)]
        self.toast("Fond : " + BG_LABELS[self.page["bg"]])
        self.invalidate()

    # -------------------------------------------------------------- outils
    def tool_for(self, key):
        if key not in self.tools:
            ink = DEFAULT_INK.get(key, "#1e3a8a")
            if self.page["bg"] in ("ardoise", "noir") or self.transparent:
                ink = DEFAULT_INK.get(key, "#ffffff" if not self.transparent else "#dc2626")
            self.tools[key] = ToolState(ink)
        return self.tools[key]

    # -------------------------------------------------------------- historique
    def _snapshot(self):
        pg = self.page
        pg["undo"].append([it for it in pg["items"]])
        del pg["undo"][:-60]
        pg["redo"].clear()

    def undo(self):
        pg = self.page
        if pg["undo"]:
            pg["redo"].append(pg["items"])
            pg["items"] = pg["undo"].pop()
            self.invalidate()

    def redo(self):
        pg = self.page
        if pg["redo"]:
            pg["undo"].append(pg["items"])
            pg["items"] = pg["redo"].pop()
            self.invalidate()

    def clear_page(self):
        if self.page["items"]:
            self._snapshot()
            self.page["items"] = []
        self.frozen = None
        self.invalidate()

    # -------------------------------------------------------------- coordonnées
    def _scale(self):
        w, h = self.page["size"]
        return self.width() / w, self.height() / h

    def to_page(self, pos):
        sx, sy = self._scale()
        return pos.x() / sx, pos.y() / sy

    # -------------------------------------------------------------- instruments
    def toggle_instrument(self, kind):
        for ins in self.instruments:
            if ins.kind == kind:
                self.instruments.remove(ins)
                self.update()
                return
        W, H = self.page["size"]
        cls = instr.KINDS[kind]
        if kind in ("projecteur", "rideau"):
            ins = cls(W, H)
        elif kind == "rapporteur":
            ins = cls(W / 2, H * 0.62)
        elif kind == "regle":
            ins = cls(W / 2 - cls.L / 2, H * 0.55)
        else:
            ins = cls(W * 0.35, H * 0.3)
        self.instruments.append(ins)
        self.update()

    # -------------------------------------------------------------- sélection
    SEL_ACTIONS = [("delete", "🗑"), ("duplicate", "⧉"), ("front", "⬆"), ("back", "⬇"), ("edit", "✏"), ("fill", "◧")]

    def _sel_valid(self):
        if self.selected is not None and not any(it is self.selected for it in self.page["items"]):
            self.selected = None
        return self.selected

    def select_item(self, it):
        self.selected = it
        self.update()
        self.changed.emit()

    def sel_handles(self):
        """Poignées de l'objet sélectionné (coordonnées page)."""
        it = self._sel_valid()
        if it is None:
            return None
        cs = world_corners(it)
        cx = sum(p[0] for p in cs) / 4
        cy = sum(p[1] for p in cs) / 4
        a = math.radians(it.get("rot", 0.0))
        top = ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)
        rot = (top[0] + 46 * math.sin(a), top[1] - 46 * math.cos(a))
        W, H = self.page["size"]
        acts = [a_ for a_ in self.SEL_ACTIONS if not (a_[0] == "edit" and it["k"] != "text")
                and not (a_[0] == "fill" and it["k"] not in FILLABLE)]
        by = max(p[1] for p in cs) + 44
        if by > H - 30:
            by = min(p[1] for p in cs) - 44
        by = max(30, min(H - 30, by))
        x0 = cx - (len(acts) - 1) * 56 / 2
        x0 = max(30, min(W - 30 - (len(acts) - 1) * 56, x0))
        buttons = [(name, icon, (x0 + i * 56, by)) for i, (name, icon) in enumerate(acts)]
        return {"corners": cs, "rotate": rot, "center": pivot(it), "buttons": buttons}

    def _sel_action(self, name):
        it = self.selected
        items = self.page["items"]
        self._snapshot()
        if name == "delete":
            items[:] = [i for i in items if i is not it]
            self.selected = None
        elif name == "duplicate":
            c = clone(it)
            translate(c, 30, 30)
            items.append(c)
            self.selected = c
        elif name == "front":
            items[:] = [i for i in items if i is not it] + [it]
        elif name == "back":
            items[:] = [it] + [i for i in items if i is not it]
        elif name == "fill":
            c = clone(it)
            c["fill"] = not it.get("fill")
            items[items.index(it)] = c
            self.selected = c
        elif name == "edit":
            self.page["undo"].pop()
            self.edit_text_requested.emit(it)
            return
        self.invalidate()

    def recolor_selected(self, color):
        it = self._sel_valid()
        if it is None or "c" not in it:
            return
        self._snapshot()
        c = clone(it)
        c["c"] = color
        items = self.page["items"]
        items[items.index(it)] = c
        self.selected = c
        self.invalidate()

    def import_pdf(self, path, max_pages=60):
        """Chaque page du PDF devient une page du tableau (en fond), sur laquelle on peut écrire."""
        from PySide6.QtCore import QSize
        from PySide6.QtPdf import QPdfDocument
        doc = QPdfDocument(self)
        doc.load(path)
        n = doc.pageCount()
        if n <= 0:
            raise RuntimeError("PDF illisible ou protégé")
        W, H = self.page["size"]
        first_new = None
        for i in range(min(n, max_pages)):
            ps = doc.pagePointSize(i)
            s = min(W * 1.5 / max(ps.width(), 1), H * 1.5 / max(ps.height(), 1))
            img = doc.render(i, QSize(int(ps.width() * s), int(ps.height() * s)))
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            img.convertToFormat(QImage.Format_RGB32).save(buf, "JPG", 88)
            pg = new_page((W, H), "blanc")
            pg["bgimg"] = base64.b64encode(bytes(buf.data())).decode()
            if first_new is None and not self.page["items"] and not self.page.get("bgimg") and len(self.pages) == 1:
                self.pages[0] = pg
                first_new = 0
            else:
                self.pages.append(pg)
                if first_new is None:
                    first_new = len(self.pages) - 1
        doc.close()
        self.go_page(first_new or 0)
        return min(n, max_pages)

    def page_thumbnail(self, i, width=260):
        pg = self.pages[i]
        w, h = pg["size"]
        img = QImage(width, int(width * h / w), QImage.Format_ARGB32)
        img.fill(Qt.white)
        p = QPainter(img)
        p.scale(width / w, width / w)
        render_page(p, pg, False)
        p.end()
        return img

    def replace_text(self, it, text):
        items = self.page["items"]
        if not any(i is it for i in items):
            return
        self._snapshot()
        c = clone(it)
        c["t"] = text
        items[items.index(it)] = c
        self.selected = c
        self.invalidate()

    def _begin_sel_gesture(self, g, kind, x, y):
        """Démarre déplacer / agrandir / pivoter : copie l'objet pour que « Annuler » retrouve l'original."""
        it = self.selected
        self._snapshot()
        c = clone(it)
        items = self.page["items"]
        items[items.index(it)] = c
        self.selected = c
        cx, cy = pivot(c)
        g.update(tool=kind, item_ref=c, scl0=c.get("scl", 1.0), rot0=c.get("rot", 0.0),
                 d0=max(8.0, math.hypot(x - cx, y - cy)), a0=math.atan2(y - cy, x - cx))

    # -------------------------------------------------------------- gestes
    def pen_down(self, pid, key, pos):
        x, y = self.to_page(pos)
        ts = self.tool_for(key)
        g = {"tool": ts.tool, "key": key, "last": (x, y)}
        for ins in reversed(self.instruments):        # les instruments sont au-dessus du dessin
            part = ins.hit(x, y)
            if part == "close":
                self.instruments.remove(ins)
                self.update()
                return
            if part == "rotate":
                g.update(tool="ins_rotate", ins=ins, a0=ins.a - math.atan2(y - ins.y, x - ins.x),
                         r0=getattr(ins, "r", 0), d0=math.hypot(x - ins.x, y - ins.y))
                self.active[pid] = g
                return
            if part == "body":
                g.update(tool="ins_move", ins=ins)
                self.active[pid] = g
                return
            if part == "block":                       # zone masquée par le projecteur
                return
        if ts.tool == "select":
            h = self.sel_handles()
            if h:
                for name, icon, (bx, by) in h["buttons"]:
                    if math.hypot(x - bx, y - by) <= 24:
                        self._sel_action(name)
                        return
                if math.hypot(x - h["rotate"][0], y - h["rotate"][1]) <= 24:
                    self._begin_sel_gesture(g, "sel_rotate", x, y)
                    self.active[pid] = g
                    return
                for cxy in h["corners"]:
                    if math.hypot(x - cxy[0], y - cxy[1]) <= 24:
                        self._begin_sel_gesture(g, "sel_scale", x, y)
                        self.active[pid] = g
                        return
            target = None
            for it in reversed(self.page["items"]):
                if hit(it, x, y, 12):
                    target = it
                    break
            self.selected = target
            if target is not None:
                self._begin_sel_gesture(g, "sel_move", x, y)
                g["moved"] = False
                self.active[pid] = g
            self.update()
            self.changed.emit()
            return
        if self.selected is not None:
            self.selected = None
        if ts.tool == "text":
            self.text_requested.emit((x, y), key)
            return
        if ts.tool == "compass":
            g["center"] = (x, y)
            g["radius"] = 0.0
            self.active[pid] = g
            self.update()
            return
        if ts.tool in ("pen", "marker", "magic", "handwrite"):
            a = 90 if ts.tool == "marker" else 255
            w = ts.width * (3 if ts.tool == "marker" else 1)
            if ts.tool in ("pen", "marker"):
                for ins in self.instruments:          # tracé le long d'un bord : aimanté
                    edge = ins.snap_edge(x, y) if hasattr(ins, "snap_edge") else None
                    if edge:
                        g["edge"], g["edge_off"] = edge, w / 2 + 1.5
                        x, y = instr.project_on_line(x, y, edge, g["edge_off"])
                        break
            g["item"] = {"k": "stroke", "c": ts.color, "w": w, "a": a, "pts": [[x, y]]}
            if ts.tool == "handwrite":
                self._hw_timer.stop()
        elif ts.tool in SHAPES:
            g["item"] = {"k": ts.tool, "c": ts.color, "w": ts.width, "p1": [x, y], "p2": [x, y]}
            if ts.fill and ts.tool in FILLABLE:
                g["item"]["fill"] = True
        elif ts.tool == "eraser":
            self._snapshot()
            self._erase(x, y, ts.width)
        self.active[pid] = g
        self.update()

    def pen_move(self, pid, pos):
        g = self.active.get(pid)
        if not g:
            return
        x, y = self.to_page(pos)
        lx, ly = g["last"]
        tool = g["tool"]
        if tool == "ins_move":
            g["ins"].move_by(x - lx, y - ly)
        elif tool == "ins_rotate":
            ins = g["ins"]
            if hasattr(ins, "resize_to"):                 # projecteur : la poignée change le rayon
                ins.resize_to(x, y)
            else:
                a = g["a0"] + math.atan2(y - ins.y, x - ins.x)
                step = math.radians(15)
                if abs(a - round(a / step) * step) < math.radians(3):   # aimantation tous les 15°
                    a = round(a / step) * step
                ins.a = a
        elif tool == "compass":
            cx, cy = g["center"]
            g["radius"] = math.hypot(x - cx, y - cy)
        elif tool in ("pen", "marker", "magic", "handwrite"):
            if "edge" in g:
                x, y = instr.project_on_line(x, y, g["edge"], g["edge_off"])
                pts = g["item"]["pts"]
                if len(pts) > 1:
                    pts[-1] = [x, y]                  # trait droit : on garde les deux extrémités
                else:
                    pts.append([x, y])
                g["last"] = (x, y)
                self.update()
                return
            if math.hypot(x - lx, y - ly) < 1.5:
                return
            g["item"]["pts"].append([x, y])
        elif tool in SHAPES:
            g["item"]["p2"] = [x, y]
        elif tool == "eraser":
            ts = self.tool_for(g["key"])
            steps = max(1, int(math.hypot(x - lx, y - ly) / 6))
            for i in range(1, steps + 1):
                self._erase(lx + (x - lx) * i / steps, ly + (y - ly) * i / steps, ts.width)
        elif tool == "sel_move":
            translate(g["item_ref"], x - lx, y - ly)
            g["moved"] = True
            self._cache = None
        elif tool == "sel_scale":
            it = g["item_ref"]
            cx, cy = pivot(it)
            it["scl"] = max(0.08, min(12.0, g["scl0"] * math.hypot(x - cx, y - cy) / g["d0"]))
            self._cache = None
        elif tool == "sel_rotate":
            it = g["item_ref"]
            cx, cy = pivot(it)
            rot = g["rot0"] + math.degrees(math.atan2(y - cy, x - cx) - g["a0"])
            snap = round(rot / 15) * 15
            if abs(rot - snap) < 4:                       # aimantation tous les 15°
                rot = snap
            it["rot"] = rot % 360
            self._cache = None
        g["last"] = (x, y)
        self.update()

    def pen_up(self, pid):
        g = self.active.pop(pid, None)
        if not g:
            return
        tool = g["tool"]
        if tool == "sel_move" and not g.get("moved"):
            self.page["undo"].pop()                       # simple toucher : pas d'entrée d'historique
        if tool == "compass" and g["radius"] > 4:
            ts = self.tool_for(g["key"])
            (cx, cy), r = g["center"], g["radius"]
            g["item"] = {"k": "ellipse", "c": ts.color, "w": ts.width, "p1": [cx - r, cy - r], "p2": [cx + r, cy + r]}
            if ts.fill:
                g["item"]["fill"] = True
        if tool == "magic" and "item" in g:              # stylo de formes : reconnaissance de la forme
            ts = self.tool_for(g["key"])
            shape = recognize.recognize_shape(g["item"]["pts"])
            if shape is not None:
                shape.update(c=g["item"]["c"], w=g["item"]["w"])
                if ts.fill and shape["k"] in FILLABLE:
                    shape["fill"] = True
                g["item"] = shape
        if "item" in g:
            self._snapshot()
            self.page["items"].append(g["item"])
            if tool == "handwrite":
                self._hw_group.append(g["item"])
                self._hw_timer.start()
            if self._cache is not None:
                self._draw_on_cache(g["item"])
        if tool.startswith("sel_"):
            self._cache = None
        self.update()
        self.changed.emit()

    # -------------------------------------------------------------- écriture manuscrite → texte
    def _hw_recognize(self):
        group = [it for it in self._hw_group if any(it is i for i in self.page["items"])]
        self._hw_group = []
        if not group:
            return
        self.toast("Reconnaissance de l'écriture…")
        W, H = self.page["size"]
        strokes = [it["pts"] for it in group]

        def job():
            try:
                cands = recognize.recognize_handwriting(strokes, W, H, "fr")
                self._hw_done.emit(group, cands[0] if cands else "")
            except Exception as e:
                self._hw_done.emit(group, RuntimeError(str(e)))
        threading.Thread(target=job, daemon=True).start()

    def _hw_apply(self, group, text):
        if isinstance(text, Exception) or not text:
            self.toast("Écriture non reconnue (connexion Internet ?)" if isinstance(text, Exception)
                       else "Écriture non reconnue")
            return
        items = self.page["items"]
        present = [it for it in group if any(it is i for i in items)]
        if not present:
            return
        xs = [p[0] for it in present for p in it["pts"]]
        ys = [p[1] for it in present for p in it["pts"]]
        h = max(ys) - min(ys)
        size = max(18, min(140, h * 0.85))
        ids = {id(it) for it in present}
        self._snapshot()
        items[:] = [i for i in items if id(i) not in ids]
        items.append({"k": "text", "t": text, "p": [min(xs), min(ys) - size * 0.1], "c": present[0]["c"],
                      "s": size, "wmax": max(400, (max(xs) - min(xs)) * 1.6)})
        self.toast(f"« {text} »")
        self.invalidate()

    def set_hover(self, pid, pos):
        if pos is None:
            if self.hovers.pop(pid, None) is not None:
                self.update()
        else:
            self.hovers[pid] = self.to_page(pos)
            self.update()

    def cancel_all(self):
        for pid in list(self.active):
            self.pen_up(pid)

    def _erase(self, x, y, width):
        if self.selected is not None and hit(self.selected, x, y, max(10, width * 2.5)):
            self.selected = None
        r = max(10, width * 2.5)
        items = self.page["items"]
        keep = [it for it in items if not hit(it, x, y, r)]
        if len(keep) != len(items):
            self.page["items"] = keep
            self._cache = None

    # -------------------------------------------------------------- souris réelle (tests, PC)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.pen_down(0, "souris", e.position())

    def mouseMoveEvent(self, e):
        self.pen_move(0, e.position())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.pen_up(0)

    def add_text(self, pos, text, key):
        if not text.strip():
            return
        ts = self.tool_for(key)
        size = {3: 28, 6: 40, 12: 60}.get(ts.width, 36)
        self._snapshot()
        self.page["items"].append({"k": "text", "t": text, "p": [pos[0], pos[1]], "c": ts.color, "s": size})
        self.invalidate()

    def add_item(self, it):
        self._snapshot()
        self.page["items"].append(it)
        self.invalidate()

    # -------------------------------------------------------------- images
    def insert_qimage(self, img, credit="", max_frac=0.4):
        """Insère une image (pictogramme, image en ligne…) au centre de la page."""
        if img is None or img.isNull():
            return
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        W, H = self.page["size"]
        s = min(W * max_frac / img.width(), H * max_frac / img.height(), 1.5)
        w, h = img.width() * s, img.height() * s
        n = len(self.page["items"]) % 6               # décalage : les insertions successives ne se superposent pas
        it = {"k": "image", "data": base64.b64encode(bytes(buf.data())).decode(),
              "r": [(W - w) / 2 + n * 24, (H - h) / 2 + n * 24, w, h], "_img": img}
        if credit:
            it["credit"] = credit
        self.add_item(it)

    def insert_image(self, path):
        with open(path, "rb") as f:
            data = f.read()
        img = QImage()
        if not img.loadFromData(QByteArray(data)):
            self.toast("Image illisible")
            return
        W, H = self.page["size"]
        s = min(W * 0.6 / img.width(), H * 0.6 / img.height(), 1.0)
        w, h = img.width() * s, img.height() * s
        it = {"k": "image", "data": base64.b64encode(data).decode(), "r": [(W - w) / 2, (H - h) / 2, w, h], "_img": img}
        self._snapshot()
        self.page["items"].append(it)
        self.invalidate()

    # -------------------------------------------------------------- rendu
    def invalidate(self):
        self._cache = None
        self.update()
        self.changed.emit()

    def resizeEvent(self, e):
        for pg in self.pages:
            if not pg["items"]:
                pg["size"] = [self.width(), self.height()]
        self._cache = None
        super().resizeEvent(e)

    def _build_cache(self):
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        sx, sy = self._scale()
        p.scale(sx, sy)
        render_page(p, self.page, self.transparent, self.frozen)
        p.end()
        self._cache = pm

    def _draw_on_cache(self, it):
        if self._cache is None:
            return
        p = QPainter(self._cache)
        p.setRenderHint(QPainter.Antialiasing, True)
        sx, sy = self._scale()
        p.scale(sx, sy)
        draw_item(p, it)
        p.end()

    def paintEvent(self, e):
        if self._cache is None or self._cache.size() != (self.size() * self.devicePixelRatioF()):
            self._build_cache()
        p = QPainter(self)
        if self.transparent:
            # alpha 1 : invisible, mais permet à la fenêtre de recevoir la souris sous Windows
            p.fillRect(self.rect(), QColor(0, 0, 0, 1))
        p.drawPixmap(0, 0, self._cache)
        p.setRenderHint(QPainter.Antialiasing, True)
        sx, sy = self._scale()
        p.save()
        p.scale(sx, sy)
        for ins in self.instruments:
            ins.paint(p)
        for g in self.active.values():
            if g["tool"] == "compass":
                (cx, cy), r = g["center"], g["radius"]
                ts = self.tool_for(g["key"])
                p.setPen(QPen(QColor(ts.color), max(1, ts.width / 2), Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), r, r)
                ang = math.atan2(g["last"][1] - cy, g["last"][0] - cx)
                ex, ey = cx + r * math.cos(ang), cy + r * math.sin(ang)
                p.setPen(QPen(QColor(71, 85, 105), 3))
                p.drawLine(QPointF(cx, cy), QPointF(ex, ey))   # branche du compas
                p.setBrush(QColor(71, 85, 105))
                p.drawEllipse(QPointF(cx, cy), 5, 5)
                p.setFont(text_font(18))
                p.setPen(QColor(15, 23, 42))
                p.drawText(QPointF((cx + ex) / 2 + 10, (cy + ey) / 2 - 10), f"r = {r / instr.PX_PER_CM:.1f} cm")
                continue
            if g["tool"] == "ins_rotate":
                ins = g["ins"]
                p.setFont(text_font(18))
                p.setPen(QColor(3, 105, 161))
                p.drawText(QPointF(ins.x + 12, ins.y - 14), f"{math.degrees(ins.a) % 360:.0f}°")
                continue
            if "item" in g:
                draw_item(p, g["item"])
            elif g["tool"] == "eraser" and "last" in g:
                ts = self.tool_for(g["key"])
                r = max(10, ts.width * 2.5)
                p.setPen(QPen(QColor(120, 120, 120, 200), 2, Qt.DashLine))
                p.setBrush(QColor(255, 255, 255, 60))
                p.drawEllipse(QPointF(*g["last"]), r, r)
        h = self.sel_handles()
        if h:                                           # cadre de sélection + poignées
            cs = h["corners"]
            p.setPen(QPen(QColor(14, 165, 233), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawPolygon(QPolygonF([QPointF(*c) for c in cs]))
            top = ((cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2)
            p.setPen(QPen(QColor(14, 165, 233), 2))
            p.drawLine(QPointF(*top), QPointF(*h["rotate"]))
            for c in cs:                                # coins : agrandir / réduire
                p.setBrush(QColor("white"))
                p.drawRect(QRectF(c[0] - 9, c[1] - 9, 18, 18))
            p.setBrush(QColor(14, 165, 233))
            p.drawEllipse(QPointF(*h["rotate"]), 13, 13)
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI Symbol", 13, QFont.Bold))
            r = h["rotate"]
            p.drawText(QRectF(r[0] - 13, r[1] - 13, 26, 26), Qt.AlignCenter, "⟳")
            for name, icon, (bx, by) in h["buttons"]:   # barre d'actions
                p.setPen(QPen(QColor(15, 23, 42), 1))
                p.setBrush(QColor(15, 23, 42, 225))
                p.drawEllipse(QPointF(bx, by), 23, 23)
                p.setPen(QColor("#fca5a5") if name == "delete" else QColor("white"))
                p.setFont(QFont("Segoe UI Symbol", 15, QFont.Bold))
                p.drawText(QRectF(bx - 23, by - 23, 46, 46), Qt.AlignCenter, icon)
            sel = self.selected
            info = []
            if abs(sel.get("scl", 1.0) - 1) > 0.01:
                info.append(f"{sel.get('scl', 1.0) * 100:.0f} %")
            if sel.get("rot"):
                info.append(f"{sel['rot']:.0f}°")
            if info:
                p.setFont(text_font(14))
                p.setPen(QColor(3, 105, 161))
                p.drawText(QPointF(r[0] + 18, r[1] + 5), "  ".join(info))
        for (hx, hy) in self.hovers.values():          # curseur du doigt
            p.setPen(QPen(QColor(250, 204, 21), 3))
            p.setBrush(QColor(250, 204, 21, 60))
            p.drawEllipse(QPointF(hx, hy), 14, 14)
            p.setBrush(QColor(250, 204, 21))
            p.drawEllipse(QPointF(hx, hy), 3, 3)
        p.restore()
        if self._toast and time.time() - self._toast_t < 2.5:
            f = p.font()
            f.setPointSize(16)
            f.setBold(True)
            p.setFont(f)
            r = p.fontMetrics().boundingRect(self._toast).adjusted(-18, -10, 18, 10)
            r.moveCenter(self.rect().center())
            r.moveTop(self.height() - 120)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(15, 23, 42, 220))
            p.drawRoundedRect(r, 12, 12)
            p.setPen(QColor("white"))
            p.drawText(r, Qt.AlignCenter, self._toast)
        p.end()

    def toast(self, text):
        self._toast, self._toast_t = text, time.time()
        self.update()
        QTimer.singleShot(2600, self.update)

    # -------------------------------------------------------------- fichiers
    def export_pdf(self, path):
        w0, h0 = self.pages[0]["size"]
        writer = QPdfWriter(path)
        writer.setResolution(96)
        writer.setPageSize(QPageSize(QSizeF(w0 * 0.75, h0 * 0.75), QPageSize.Point, "TBI"))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0))
        writer.setTitle("TBI Pro")
        p = QPainter(writer)
        for i, pg in enumerate(self.pages):
            if i:
                writer.newPage()
            vp = p.viewport()
            w, h = pg["size"]
            p.save()
            s = min(vp.width() / w, vp.height() / h)
            p.scale(s, s)
            render_page(p, pg, False)
            p.restore()
        p.end()

    def export_png(self, path):
        w, h = self.page["size"]
        img = QImage(int(w), int(h), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        render_page(p, self.page, self.transparent, self.frozen)
        p.end()
        img.save(path)

    def save(self, path):
        pages = []
        for pg in self.pages:
            d = {"bg": pg["bg"], "size": pg["size"],
                 "items": [{k: v for k, v in it.items() if not k.startswith("_")} for it in pg["items"]]}
            if pg.get("bgimg"):
                d["bgimg"] = pg["bgimg"]
            pages.append(d)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"app": "TBI Pro", "version": 1, "pages": pages}, f)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.cancel_all()
        self.pages = [dict({"bg": pg.get("bg", "blanc"), "size": pg["size"], "items": pg["items"], "undo": [], "redo": []},
                           **({"bgimg": pg["bgimg"]} if pg.get("bgimg") else {}))
                      for pg in d["pages"]] or [new_page((self.width(), self.height()))]
        self.selected = None
        self.index = 0
        self.invalidate()
