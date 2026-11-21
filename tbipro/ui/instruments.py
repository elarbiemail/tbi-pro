# -*- coding: utf-8 -*-
"""
Instruments de géométrie posés sur le tableau : règle, équerre, rapporteur.

Au stylet :
  • appuyer dans l'instrument puis glisser   → le déplacer ;
  • poignée ⟳                                 → le faire tourner (aimanté tous les 15°) ;
  • croix ×                                   → le retirer ;
  • tracer au stylo le long d'un bord         → trait parfaitement droit (aimanté au bord).
Le compas est un outil de tracé (voir canvas.py).
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF

PX_PER_CM = 37.8          # 1 cm « écran » (96 ppp) ; l'échelle réelle dépend du projecteur
SNAP_DIST = 28            # distance d'aimantation au bord (pixels)
HANDLE_R = 20


class Instrument:
    kind = "?"
    edges = []            # segments aimantés, coordonnées locales [(x1, y1, x2, y2), …]

    def __init__(self, x, y, a=0.0):
        self.x, self.y, self.a = x, y, a

    # -------------------------------------------------------------- repères
    def to_local(self, px, py):
        dx, dy = px - self.x, py - self.y
        c, s = math.cos(-self.a), math.sin(-self.a)
        return dx * c - dy * s, dx * s + dy * c

    def to_world(self, lx, ly):
        c, s = math.cos(self.a), math.sin(self.a)
        return self.x + lx * c - ly * s, self.y + lx * s + ly * c

    # à définir
    def contains_local(self, lx, ly):
        return False

    rotate_handle = (0, 0)
    close_handle = (0, 0)

    def hit(self, px, py):
        """→ "rotate", "close", "body" ou None."""
        lx, ly = self.to_local(px, py)
        if math.hypot(lx - self.rotate_handle[0], ly - self.rotate_handle[1]) <= HANDLE_R + 4:
            return "rotate"
        if math.hypot(lx - self.close_handle[0], ly - self.close_handle[1]) <= HANDLE_R:
            return "close"
        if self.contains_local(lx, ly):
            return "body"
        return None

    def snap_edge(self, px, py):
        """Bord le plus proche (hors de l'instrument) → (x1, y1, x2, y2) monde, ou None."""
        lx, ly = self.to_local(px, py)
        if self.contains_local(lx, ly):
            return None
        best, bd = None, SNAP_DIST
        for (x1, y1, x2, y2) in self.edges:
            d = _seg_dist(lx, ly, x1, y1, x2, y2)
            if d < bd:
                best, bd = (x1, y1, x2, y2), d
        if best is None:
            return None
        a = self.to_world(best[0], best[1])
        b = self.to_world(best[2], best[3])
        return (a[0], a[1], b[0], b[1])

    def to_dict(self):
        return {"kind": self.kind, "x": self.x, "y": self.y, "a": self.a}

    # -------------------------------------------------------------- dessin
    def paint(self, p):
        p.save()
        p.translate(self.x, self.y)
        p.rotate(math.degrees(self.a))
        self.paint_local(p)
        self._handles(p)
        p.restore()

    def _handles(self, p):
        rx, ry = self.rotate_handle
        p.setPen(QPen(QColor(14, 116, 144), 2))
        p.setBrush(QColor(255, 255, 255, 230))
        p.drawEllipse(QPointF(rx, ry), HANDLE_R, HANDLE_R)
        p.setFont(QFont("Segoe UI Symbol", 14, QFont.Bold))
        p.drawText(QRectF(rx - HANDLE_R, ry - HANDLE_R, 2 * HANDLE_R, 2 * HANDLE_R), Qt.AlignCenter, "⟳")
        cx, cy = self.close_handle
        p.setPen(QPen(QColor(185, 28, 28), 2))
        p.drawEllipse(QPointF(cx, cy), HANDLE_R - 4, HANDLE_R - 4)
        p.drawText(QRectF(cx - HANDLE_R, cy - HANDLE_R, 2 * HANDLE_R, 2 * HANDLE_R), Qt.AlignCenter, "×")


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


FILL = QColor(186, 230, 253, 150)
BORDER = QColor(3, 105, 161)
TICK = QColor(15, 23, 42)


class Ruler(Instrument):
    kind = "regle"
    CM = 20
    L = CM * PX_PER_CM
    H = 80

    @property
    def edges(self):
        return [(0, 0, self.L, 0), (0, self.H, self.L, self.H)]

    rotate_handle = (L - 30, H - 26)
    close_handle = (28, H - 26)

    def contains_local(self, lx, ly):
        return 0 <= lx <= self.L and 0 <= ly <= self.H

    def paint_local(self, p):
        p.setPen(QPen(BORDER, 2))
        p.setBrush(FILL)
        p.drawRoundedRect(QRectF(0, 0, self.L, self.H), 6, 6)
        p.setFont(QFont("Segoe UI", 9))
        for mm in range(self.CM * 10 + 1):
            x = mm * PX_PER_CM / 10
            h = 22 if mm % 10 == 0 else (14 if mm % 5 == 0 else 8)
            p.setPen(QPen(TICK, 1.2 if mm % 10 == 0 else 0.8))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            if mm % 10 == 0:
                p.drawText(QRectF(x - 15, 22, 30, 16), Qt.AlignCenter, str(mm // 10))


class SetSquare(Instrument):
    kind = "equerre"
    W = 14 * PX_PER_CM
    H = 9 * PX_PER_CM

    @property
    def edges(self):
        return [(0, 0, self.W, 0), (0, 0, 0, self.H), (self.W, 0, 0, self.H)]

    rotate_handle = (W * 0.30, H * 0.22)
    close_handle = (34, 34)

    def contains_local(self, lx, ly):
        return lx >= 0 and ly >= 0 and lx / self.W + ly / self.H <= 1

    def paint_local(self, p):
        poly = QPolygonF([QPointF(0, 0), QPointF(self.W, 0), QPointF(0, self.H)])
        path = QPainterPath()
        path.addPolygon(poly)
        path.closeSubpath()
        p.setPen(QPen(BORDER, 2))
        p.setBrush(FILL)
        p.drawPath(path)
        p.setFont(QFont("Segoe UI", 8))
        for mm in range(0, int(self.W / PX_PER_CM * 10)):
            x = mm * PX_PER_CM / 10
            h = 16 if mm % 10 == 0 else (10 if mm % 5 == 0 else 6)
            p.setPen(QPen(TICK, 0.8))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            if mm % 10 == 0 and mm:
                p.drawText(QRectF(x - 12, 16, 24, 14), Qt.AlignCenter, str(mm // 10))
        for mm in range(0, int(self.H / PX_PER_CM * 10)):
            y = mm * PX_PER_CM / 10
            h = 16 if mm % 10 == 0 else (10 if mm % 5 == 0 else 6)
            p.drawLine(QPointF(0, y), QPointF(h, y))
        # angle droit
        p.setPen(QPen(BORDER, 1.5))
        p.drawRect(QRectF(0, 0, 18, 18))


class Protractor(Instrument):
    kind = "rapporteur"
    R = 6 * PX_PER_CM

    @property
    def edges(self):
        return [(-self.R, 0, self.R, 0)]

    rotate_handle = (0, -R * 0.42)
    close_handle = (-R * 0.62, -24)

    def contains_local(self, lx, ly):
        return ly <= 6 and math.hypot(lx, ly) <= self.R

    def paint_local(self, p):
        R = self.R
        path = QPainterPath(QPointF(-R, 0))
        path.arcTo(QRectF(-R, -R, 2 * R, 2 * R), 180, -180)
        path.closeSubpath()
        p.setPen(QPen(BORDER, 2))
        p.setBrush(FILL)
        p.drawPath(path)
        p.setFont(QFont("Segoe UI", 8))
        for deg in range(0, 181):
            t = math.radians(deg)
            L = 18 if deg % 10 == 0 else (11 if deg % 5 == 0 else 6)
            c, s = math.cos(t), -math.sin(t)
            p.setPen(QPen(TICK, 1 if deg % 10 == 0 else 0.6))
            p.drawLine(QPointF(R * c, R * s), QPointF((R - L) * c, (R - L) * s))
            if deg % 10 == 0:
                p.drawText(QRectF((R - 32) * c - 13, (R - 32) * s - 8, 26, 16), Qt.AlignCenter, str(deg))
                p.drawText(QRectF((R - 50) * c - 13, (R - 50) * s - 8, 26, 16), Qt.AlignCenter, str(180 - deg))
        p.setPen(QPen(QColor(220, 38, 38), 1.5))
        p.drawLine(QPointF(-8, 0), QPointF(8, 0))
        p.drawLine(QPointF(0, -8), QPointF(0, 2))


KINDS = {"regle": Ruler, "equerre": SetSquare, "rapporteur": Protractor}


def from_dict(d):
    cls = KINDS.get(d.get("kind"))
    return cls(d["x"], d["y"], d.get("a", 0.0)) if cls else None


def project_on_line(px, py, edge, offset):
    """Projette un point sur la droite d'un bord, décalé vers l'extérieur de « offset »."""
    x1, y1, x2, y2 = edge
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    t = (px - x1) * ux + (py - y1) * uy
    qx, qy = x1 + t * ux, y1 + t * uy
    nx, ny = px - qx, py - qy                  # côté où se trouve le stylet
    n = math.hypot(nx, ny)
    if n > 1e-6:
        qx, qy = qx + nx / n * offset, qy + ny / n * offset
    return qx, qy
