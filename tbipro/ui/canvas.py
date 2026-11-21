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
import time

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QPointF, QRect, QRectF, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter,
                           QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import QWidget

from . import instruments as instr
from .mindmap import draw_mindmap, mindmap_bounds

BACKGROUNDS = ["blanc", "quadrillage", "seyes", "lignes", "ardoise", "noir"]
BG_LABELS = {"blanc": "Blanc", "quadrillage": "Quadrillage", "seyes": "Seyès", "lignes": "Lignes",
             "ardoise": "Ardoise verte", "noir": "Noir"}
PALETTE = ["#1e3a8a", "#111827", "#dc2626", "#16a34a", "#2563eb", "#f59e0b", "#9333ea", "#ffffff"]
WIDTHS = {"fin": 3, "moyen": 6, "epais": 12}
DEFAULT_INK = {"rouge": "#dc2626", "vert": "#16a34a", "bleu": "#2563eb"}
SHAPES = ("line", "arrow", "rect", "ellipse")
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
        self.tool = "pen"          # pen, marker, eraser, move, line, arrow, rect, ellipse
        self.color = color
        self.width = WIDTHS["moyen"]


def new_page(size, bg="blanc"):
    return {"bg": bg, "size": [size[0], size[1]], "items": [], "undo": [], "redo": []}


# ----------------------------------------------------------------------------
# Rendu (partagé par l'écran et l'export PDF / PNG)
# ----------------------------------------------------------------------------
def draw_background(p, bg, w, h, transparent=False):
    if transparent:
        return
    colors = {"ardoise": "#1f3d2b", "noir": "#111111"}
    p.fillRect(QRectF(0, 0, w, h), QColor(colors.get(bg, "#ffffff")))
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


def item_image(it):
    img = it.get("_img")
    if img is None:
        img = QImage()
        img.loadFromData(QByteArray(base64.b64decode(it["data"])))
        it["_img"] = img
    return img


def draw_item(p, it):
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


def render_page(p, page, transparent=False, frozen=None):
    w, h = page["size"]
    draw_background(p, page["bg"], w, h, transparent and frozen is None)
    if frozen is not None:
        p.drawPixmap(QRectF(0, 0, w, h), frozen, QRectF(frozen.rect()))
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    for it in page["items"]:
        draw_item(p, it)


# ----------------------------------------------------------------------------
# Géométrie (gomme, déplacement)
# ----------------------------------------------------------------------------
def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def hit(it, x, y, r):
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
    (x1, y1), (x2, y2) = it["p1"], it["p2"]
    if k in ("line", "arrow"):
        return _seg_dist(x, y, x1, y1, x2, y2) <= rr
    l, rgt, t, b = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
    if k == "rect":
        edges = [(l, t, rgt, t), (rgt, t, rgt, b), (rgt, b, l, b), (l, b, l, t)]
        return any(_seg_dist(x, y, *e) <= rr for e in edges)
    if k == "ellipse":
        cx, cy, ax, ay = (l + rgt) / 2, (t + b) / 2, max((rgt - l) / 2, 1), max((b - t) / 2, 1)
        d = math.hypot((x - cx) / ax, (y - cy) / ay)
        return abs(d - 1) * min(ax, ay) <= rr
    return False


def translate(it, dx, dy):
    k = it["k"]
    if k == "image":
        it["r"] = [it["r"][0] + dx, it["r"][1] + dy, it["r"][2], it["r"][3]]
    elif k in ("text", "mindmap"):
        it["p"] = [it["p"][0] + dx, it["p"][1] + dy]
    elif k == "stroke":
        it["pts"] = [[x + dx, y + dy] for x, y in it["pts"]]
    else:
        it["p1"] = [it["p1"][0] + dx, it["p1"][1] + dy]
        it["p2"] = [it["p2"][0] + dx, it["p2"][1] + dy]


def clone(it):
    c = {k: (v.copy() if isinstance(v, list) else v) for k, v in it.items()}
    if "pts" in c:
        c["pts"] = [list(p) for p in it["pts"]]
    if "_img" in it:
        c["_img"] = it["_img"]
    return c


# ----------------------------------------------------------------------------
# Widget
# ----------------------------------------------------------------------------
class InkCanvas(QWidget):
    changed = Signal()          # contenu modifié (pour rafraîchir la barre d'outils)
    text_requested = Signal(object, str)   # position (page), clé du stylet : saisir un texte

    def __init__(self, transparent=False, parent=None):
        super().__init__(parent)
        self.transparent = transparent
        self.pages = []
        self.index = 0
        self.tools = {}
        self.active = {}        # id pointeur → geste en cours
        self.frozen = None      # mode annotation : image de l'écran « figé »
        self.hovers = {}        # id pointeur → position (doigt visible sans appui)
        self.instruments = []   # règle, équerre, rapporteur posés sur l'écran
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

    # -------------------------------------------------------------- gestes
    # -------------------------------------------------------------- instruments
    def toggle_instrument(self, kind):
        for ins in self.instruments:
            if ins.kind == kind:
                self.instruments.remove(ins)
                self.update()
                return
        W, H = self.page["size"]
        cls = instr.KINDS[kind]
        if kind == "rapporteur":
            ins = cls(W / 2, H * 0.62)
        elif kind == "regle":
            ins = cls(W / 2 - cls.L / 2, H * 0.55)
        else:
            ins = cls(W * 0.35, H * 0.3)
        self.instruments.append(ins)
        self.update()

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
                g.update(tool="ins_rotate", ins=ins, a0=ins.a - math.atan2(y - ins.y, x - ins.x))
                self.active[pid] = g
                return
            if part == "body":
                g.update(tool="ins_move", ins=ins)
                self.active[pid] = g
                return
        if ts.tool == "text":
            self.text_requested.emit((x, y), key)
            return
        if ts.tool == "compass":
            g["center"] = (x, y)
            g["radius"] = 0.0
            self.active[pid] = g
            self.update()
            return
        if ts.tool in ("pen", "marker"):
            a = 90 if ts.tool == "marker" else 255
            w = ts.width * (3 if ts.tool == "marker" else 1)
            for ins in self.instruments:              # tracé le long d'un bord : aimanté
                edge = ins.snap_edge(x, y)
                if edge:
                    g["edge"], g["edge_off"] = edge, w / 2 + 1.5
                    x, y = instr.project_on_line(x, y, edge, g["edge_off"])
                    break
            g["item"] = {"k": "stroke", "c": ts.color, "w": w, "a": a, "pts": [[x, y]]}
        elif ts.tool in SHAPES:
            g["item"] = {"k": ts.tool, "c": ts.color, "w": ts.width, "p1": [x, y], "p2": [x, y]}
        elif ts.tool == "eraser":
            self._snapshot()
            g["erased"] = False
            self._erase(x, y, ts.width)
        elif ts.tool == "move":
            target = None
            for it in reversed(self.page["items"]):
                if hit(it, x, y, 12):
                    target = it
                    break
            if target is not None:
                self._snapshot()
                c = clone(target)
                items = self.page["items"]
                items[items.index(target)] = c   # copie : l'historique garde l'ancienne version
                g["item_ref"] = c
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
            g["ins"].x += x - lx
            g["ins"].y += y - ly
        elif tool == "ins_rotate":
            ins = g["ins"]
            a = g["a0"] + math.atan2(y - ins.y, x - ins.x)
            step = math.radians(15)
            if abs(a - round(a / step) * step) < math.radians(3):   # aimantation tous les 15°
                a = round(a / step) * step
            ins.a = a
        elif tool == "compass":
            cx, cy = g["center"]
            g["radius"] = math.hypot(x - cx, y - cy)
        elif tool in ("pen", "marker"):
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
        elif tool == "move" and "item_ref" in g:
            translate(g["item_ref"], x - lx, y - ly)
            self._cache = None
        g["last"] = (x, y)
        self.update()

    def pen_up(self, pid):
        g = self.active.pop(pid, None)
        if not g:
            return
        if g["tool"] == "compass" and g["radius"] > 4:
            ts = self.tool_for(g["key"])
            (cx, cy), r = g["center"], g["radius"]
            g["item"] = {"k": "ellipse", "c": ts.color, "w": ts.width, "p1": [cx - r, cy - r], "p2": [cx + r, cy + r]}
        if "item" in g:
            self._snapshot()
            self.page["items"].append(g["item"])
            self._draw_on_cache(g["item"])
        self.update()
        self.changed.emit()

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
            pages.append({"bg": pg["bg"], "size": pg["size"],
                          "items": [{k: v for k, v in it.items() if not k.startswith("_")} for it in pg["items"]]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"app": "TBI Pro", "version": 1, "pages": pages}, f)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.cancel_all()
        self.pages = [{"bg": pg.get("bg", "blanc"), "size": pg["size"], "items": pg["items"], "undo": [], "redo": []}
                      for pg in d["pages"]] or [new_page((self.width(), self.height()))]
        self.index = 0
        self.invalidate()
