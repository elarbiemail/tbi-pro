# -*- coding: utf-8 -*-
"""
Vision : détection des LED, classement par couleur, calibrage (homographie)
et suivi de plusieurs stylets.

Toutes les positions caméra sont NORMALISÉES (0-1) : le calibrage reste valable
même si la résolution de la caméra change.
"""
import math

import numpy as np

try:
    import cv2
except ImportError:  # la source « portable » n'a pas besoin d'OpenCV pour détecter
    cv2 = None

COLOR_NAMES = ["blanc", "rouge", "vert", "bleu"]


# ----------------------------------------------------------------------------
# Couleur d'une LED
# ----------------------------------------------------------------------------
def classify_rgb(r, g, b):
    """Couleur dominante du halo d'une LED (le centre est souvent saturé en blanc)."""
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 45:
        return "blanc"
    if mx == r:
        return "rouge"
    if mx == g:
        return "vert"
    return "bleu"


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def expand_poly(poly, margin=0.04):
    c = np.mean(np.array(poly, float), axis=0)
    return [tuple(c + (np.array(p, float) - c) * (1 + margin)) for p in poly]


# ----------------------------------------------------------------------------
# Détection (source webcam ; la page du portable fait la même chose en JavaScript)
# ----------------------------------------------------------------------------
def detect_blobs(frame, threshold=225, min_area=2, max_area=400, roi=None, max_blobs=6):
    """frame BGR → liste de (x, y, surface, couleur) en coordonnées normalisées."""
    h, w = frame.shape[:2]
    bright = frame.max(axis=2) if frame.ndim == 3 else frame
    bright = cv2.GaussianBlur(bright, (3, 3), 0)
    _, mask = cv2.threshold(bright, threshold, 255, cv2.THRESH_BINARY)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    poly = expand_poly(roi) if roi else None
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if not (min_area <= area <= max_area):
            continue
        cx, cy = cents[i][0] / w, cents[i][1] / h
        if poly and not point_in_poly(cx, cy, poly):
            continue
        x0, y0 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        pad = 3
        sub = frame[max(0, y0 - pad):y0 + bh + pad, max(0, x0 - pad):x0 + bw + pad].reshape(-1, 3).astype(int)
        halo = sub[(sub.max(axis=1) > threshold * 0.55) & (sub.min(axis=1) < 245)]
        color = "blanc"
        if len(halo):
            b, g, r = halo.mean(axis=0)
            color = classify_rgb(r, g, b)
        out.append((cx, cy, area, color))
    out.sort(key=lambda t: -t[2])
    return out[:max_blobs]


# ----------------------------------------------------------------------------
# Calibrage
# ----------------------------------------------------------------------------
def homography(src, dst):
    """Homographie 3x3 par DLT (moindres carrés si plus de 4 points). Sans OpenCV."""
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        A.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.array(A, float))
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def apply_h(H, x, y):
    H = np.asarray(H, float)
    d = H[2, 0] * x + H[2, 1] * y + H[2, 2]
    return ((H[0, 0] * x + H[0, 1] * y + H[0, 2]) / d,
            (H[1, 0] * x + H[1, 1] * y + H[1, 2]) / d)


def camera_roi(H, w, h):
    """Contour de l'écran vu par la caméra (normalisé)."""
    Hi = np.linalg.inv(np.asarray(H, float))
    return [apply_h(Hi, x, y) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]


def target_points(w, h, inset=0.1):
    dx, dy = w * inset, h * inset
    return [(dx, dy), (w - dx, dy), (w - dx, h - dy), (dx, h - dy)]


def order_corners(pts):
    pts = np.array(pts, float).reshape(-1, 2)
    s, d = pts.sum(axis=1), pts[:, 1] - pts[:, 0]
    return [tuple(pts[np.argmin(s)]), tuple(pts[np.argmin(d)]), tuple(pts[np.argmax(s)]), tuple(pts[np.argmax(d)])]


def find_projection_quad(dark, light):
    """Calibrage automatique : image (noir projeté) et image (blanc projeté) → 4 coins normalisés."""
    g1 = cv2.cvtColor(dark, cv2.COLOR_BGR2GRAY) if dark.ndim == 3 else dark
    g2 = cv2.cvtColor(light, cv2.COLOR_BGR2GRAY) if light.ndim == 3 else light
    if g1.shape != g2.shape:
        g1 = cv2.resize(g1, (g2.shape[1], g2.shape[0]))
    h, w = g2.shape
    diff = cv2.GaussianBlur(cv2.absdiff(g2, g1), (7, 7), 0)
    _, mask = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.02 * w * h:
        return None
    peri = cv2.arcLength(c, True)
    quad = None
    for eps in (0.02, 0.03, 0.05, 0.08):
        a = cv2.approxPolyDP(c, eps * peri, True)
        if len(a) == 4:
            quad = a.reshape(4, 2)
            break
    if quad is None:
        quad = cv2.boxPoints(cv2.minAreaRect(c))
    return [(x / w, y / h) for x, y in order_corners(quad)]


# ----------------------------------------------------------------------------
# Suivi multi-stylets
# ----------------------------------------------------------------------------
class Track:
    __slots__ = ("id", "key", "x", "y", "seen", "lost", "down")

    def __init__(self, tid, key, x, y):
        self.id, self.key, self.x, self.y = tid, key, x, y
        self.seen, self.lost, self.down = 1, 0, False


class PenTracker:
    """
    Associe les points détectés d'une image à l'autre et produit des événements :
      ("down", id, clé, x, y)  ("move", id, clé, x, y)  ("up", id, clé, x, y)
    La clé identifie le stylet (sa couleur si l'option est active, sinon "stylet").
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.tracks = []
        self.next_id = 1

    def key_of(self, color):
        return color if self.cfg.get("color_pens") else "stylet"

    def release_all(self):
        ev = [("up", t.id, t.key, t.x, t.y) for t in self.tracks if t.down]
        self.tracks = []
        return ev

    def update(self, points, max_dist=140.0):
        """points : liste de (x, y, couleur) en pixels écran. Renvoie la liste d'événements."""
        c = self.cfg
        a = float(c.get("smoothing", 0.45))
        events = []
        pts = list(points)[: int(c.get("max_pens", 4)) + 2]
        # appariement glouton par distance croissante (même couleur obligatoire si option active)
        pairs = []
        for ti, t in enumerate(self.tracks):
            for pi, (x, y, col) in enumerate(pts):
                d = math.hypot(t.x - x, t.y - y)
                if c.get("color_pens") and t.key != self.key_of(col):
                    d += 80.0  # couleur différente : possible (reflet), mais pénalisé
                if d <= max_dist:
                    pairs.append((d, ti, pi))
        pairs.sort()
        used_t, used_p = set(), set()
        for d, ti, pi in pairs:
            if ti in used_t or pi in used_p:
                continue
            used_t.add(ti)
            used_p.add(pi)
            t = self.tracks[ti]
            x, y, _ = pts[pi]
            t.x, t.y = a * t.x + (1 - a) * x, a * t.y + (1 - a) * y
            t.seen += 1
            t.lost = 0
        survivors = []
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.lost += 1
                if t.lost >= int(c.get("off_frames", 3)):
                    if t.down:
                        events.append(("up", t.id, t.key, t.x, t.y))
                    continue
            survivors.append(t)
        self.tracks = survivors
        for pi, (x, y, col) in enumerate(pts):
            if pi not in used_p and len(self.tracks) < int(c.get("max_pens", 4)):
                self.tracks.append(Track(self.next_id, self.key_of(col), x, y))
                self.next_id += 1
        for t in self.tracks:
            if t.lost:
                continue
            if not t.down and t.seen >= int(c.get("on_frames", 2)):
                t.down = True
                events.append(("down", t.id, t.key, t.x, t.y))
            elif t.down:
                events.append(("move", t.id, t.key, t.x, t.y))
        return events


# ----------------------------------------------------------------------------
# Caméra infrarouge (stylet à LED IR 850/940 nm)
# ----------------------------------------------------------------------------
class IRBackground:
    """
    Modèle du fond infrarouge (soleil, lampes, reflets fixes) : on le soustrait
    pour ne garder que la LED du stylet. Mis à jour lentement quand aucun stylet
    n'est visible.
    """

    def __init__(self, rate=0.02):
        self.bg = None
        self.rate = rate

    def reset(self):
        self.bg = None

    def apply(self, gray, update=True):
        g = gray.astype(np.float32)
        if self.bg is None or self.bg.shape != g.shape:
            self.bg = g.copy()
        out = np.clip(g - self.bg, 0, 255).astype(np.uint8)
        return out

    def learn(self, gray):
        g = gray.astype(np.float32)
        if self.bg is None or self.bg.shape != g.shape:
            self.bg = g.copy()
        else:
            cv2.accumulateWeighted(g, self.bg, self.rate)


def detect_blobs_ir(frame, background=None, threshold=200, min_area=2, max_area=400, roi=None, max_blobs=6):
    """Image infrarouge (niveaux de gris) → liste de (x, y, surface, "ir") normalisés."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    h, w = gray.shape
    work = background.apply(gray) if background is not None else gray
    work = cv2.GaussianBlur(work, (3, 3), 0)
    _, mask = cv2.threshold(work, threshold, 255, cv2.THRESH_BINARY)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    poly = expand_poly(roi) if roi else None
    out = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if not (min_area <= area <= max_area):
            continue
        cx, cy = cents[i][0] / w, cents[i][1] / h
        if poly and not point_in_poly(cx, cy, poly):
            continue
        out.append((cx, cy, area, "ir"))
    if background is not None and not out:
        background.learn(gray)   # aucun stylet : le fond peut être appris
    out.sort(key=lambda t: -t[2])
    return out[:max_blobs]
