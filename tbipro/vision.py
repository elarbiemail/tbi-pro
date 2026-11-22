# -*- coding: utf-8 -*-
"""
Vision : détection des LED, classement par couleur, calibrage (homographie)
et suivi de plusieurs stylets.

Toutes les positions caméra sont NORMALISÉES (0-1) : le calibrage reste valable
même si la résolution de la caméra change.
"""
import math
import time

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
class OneEuro:
    """
    Filtre « One Euro » (Casiez et al., 2012) : très stable quand le pointeur bouge lentement
    (on peut viser précisément), réactif quand il bouge vite (pas de retard en écrivant).
    """

    def __init__(self, min_cutoff=1.0, beta=0.015, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.x = self.dx = self.t = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if self.x is None:
            self.x, self.dx, self.t = x, 0.0, t
            return x
        dt = max(1e-3, t - self.t)
        self.t = t
        dx = (x - self.x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        a = self._alpha(cutoff, dt)
        self.x = a * x + (1 - a) * self.x
        return self.x


class Track:
    __slots__ = ("id", "key", "x", "y", "seen", "lost", "down", "pressed", "unpressed", "fx", "fy")

    def __init__(self, tid, key, x, y, pressed=True):
        self.id, self.key, self.x, self.y = tid, key, x, y
        self.seen, self.lost, self.down = 1, 0, False
        self.pressed, self.unpressed = pressed, 0
        self.fx = self.fy = None


class PenTracker:
    """
    Associe les points détectés d'une image à l'autre et produit des événements :
      ("down", id, clé, x, y)  ("move", id, clé, x, y)  ("up", id, clé, x, y)
      ("hover", id, clé, x, y) : pointeur visible mais pas « appuyé » (doigt sans pincement)
      ("leave", id, clé, x, y) : pointeur disparu
    La clé identifie le stylet (sa couleur si l'option est active, sinon "stylet").
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.tracks = []
        self.next_id = 1

    def key_of(self, color):
        return color if self.cfg.get("color_pens") else "stylet"

    def release_all(self):
        ev = [("up" if t.down else "leave", t.id, t.key, t.x, t.y) for t in self.tracks]
        self.tracks = []
        return ev

    def update(self, points, max_dist=140.0):
        """points : liste de (x, y, couleur[, appuyé]) en pixels écran. Renvoie la liste d'événements."""
        c = self.cfg
        a = float(c.get("smoothing", 0.45))
        now = time.time()
        events = []
        pts = [(p[0], p[1], p[2], bool(p[3]) if len(p) > 3 else True) for p in points][: int(c.get("max_pens", 4)) + 2]
        # appariement glouton par distance croissante (même couleur obligatoire si option active)
        pairs = []
        for ti, t in enumerate(self.tracks):
            for pi, (x, y, col, _) in enumerate(pts):
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
            x, y, _, pr = pts[pi]
            if t.fx is None:
                # stabilisation 0 → presque brut ; 0,95 → très stable à l'arrêt
                mc = 0.05 + 4.0 * (1 - a) ** 2
                t.fx, t.fy = OneEuro(mc, 0.012), OneEuro(mc, 0.012)
                t.fx(t.x, now - 0.016)
                t.fy(t.y, now - 0.016)
            t.x, t.y = t.fx(x, now), t.fy(y, now)
            t.seen += 1
            t.lost = 0
            t.pressed = pr
        survivors = []
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.lost += 1
                if t.lost >= int(c.get("off_frames", 3)):
                    events.append(("up" if t.down else "leave", t.id, t.key, t.x, t.y))
                    continue
            survivors.append(t)
        self.tracks = survivors
        for pi, (x, y, col, pr) in enumerate(pts):
            if pi not in used_p and len(self.tracks) < int(c.get("max_pens", 4)):
                self.tracks.append(Track(self.next_id, self.key_of(col), x, y, pr))
                self.next_id += 1
        off = int(c.get("off_frames", 3))
        for t in self.tracks:
            if t.lost:
                continue
            if not t.down:
                if t.pressed and t.seen >= int(c.get("on_frames", 2)):
                    t.down, t.unpressed = True, 0
                    events.append(("down", t.id, t.key, t.x, t.y))
                else:
                    events.append(("hover", t.id, t.key, t.x, t.y))
            elif t.pressed:
                t.unpressed = 0
                events.append(("move", t.id, t.key, t.x, t.y))
            else:
                t.unpressed += 1
                if t.unpressed >= off:
                    t.down = False
                    events.append(("up", t.id, t.key, t.x, t.y))
                else:
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



# ----------------------------------------------------------------------------
# Doigt : l'index de la main sert de pointeur (MediaPipe Hand Landmarker)
# ----------------------------------------------------------------------------
PINCH_ON, PINCH_OFF = 0.30, 0.42        # hystérésis (rapport à la taille de la main)
PINCH_ON_M, PINCH_OFF_M = 0.030, 0.045  # hystérésis en mètres (coordonnées 3D « monde » de MediaPipe)


def pinch_ratio(lm):
    """Distance pouce-index rapportée à la taille de la main (poignet → base du majeur)."""
    def d(a, b):
        return math.hypot(lm[a][0] - lm[b][0], lm[a][1] - lm[b][1])
    return d(4, 8) / max(d(0, 9), 1e-6)


class PinchState:
    def __init__(self):
        self.pressed = False

    def update(self, ratio, metres=None):
        if metres is not None:          # mesure 3D : indépendante de l'orientation de la main
            if self.pressed and metres > PINCH_OFF_M:
                self.pressed = False
            elif not self.pressed and metres < PINCH_ON_M:
                self.pressed = True
            return self.pressed
        if self.pressed and ratio > PINCH_OFF:
            self.pressed = False
        elif not self.pressed and ratio < PINCH_ON:
            self.pressed = True
        return self.pressed


def crop_box(roi, w, h, margin=0.12):
    """Rectangle (pixels) englobant la projection + marge, pour zoomer avant la détection."""
    if not roi:
        return 0, 0, w, h
    xs = [p[0] for p in roi]
    ys = [p[1] for p in roi]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    mx, my = (x1 - x0) * margin, (y1 - y0) * margin
    x0, y0 = max(0.0, x0 - mx), max(0.0, y0 - my)
    x1, y1 = min(1.0, x1 + mx), min(1.0, y1 + my)
    if (x1 - x0) * (y1 - y0) > 0.8:      # la projection remplit déjà l'image
        return 0, 0, w, h
    return int(x0 * w), int(y0 * h), max(16, int((x1 - x0) * w)), max(16, int((y1 - y0) * h))


class HandDetector:
    """Détection de la main sur le PC (sources webcam) avec le paquet Python mediapipe."""

    def __init__(self, model_path, max_hands=2):
        from mediapipe.tasks.python import BaseOptions, vision as mpv
        import mediapipe as mp
        self.mp = mp
        opts = mpv.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=model_path),
                                         running_mode=mpv.RunningMode.VIDEO, num_hands=max_hands,
                                         min_hand_detection_confidence=0.55, min_hand_presence_confidence=0.55,
                                         min_tracking_confidence=0.6)
        self.lm = mpv.HandLandmarker.create_from_options(opts)
        self.pinch = {}
        self.t0 = time.time()
        self.last_ts = -1

    def detect(self, frame_bgr, roi=None, crop=True):
        """→ liste de (x, y, 0, "doigt", appuyé) normalisés (bout de l'index)."""
        H, W = frame_bgr.shape[:2]
        x0, y0, cw, ch = crop_box(roi, W, H) if crop else (0, 0, W, H)
        sub = frame_bgr[y0:y0 + ch, x0:x0 + cw]
        if cw < 640:                                   # agrandir : la main est plus nette pour le modèle
            f = 640 / cw
            sub = cv2.resize(sub, (int(cw * f), int(ch * f)), interpolation=cv2.INTER_CUBIC)
        rgb = np.ascontiguousarray(sub[:, :, ::-1])
        ts = int((time.time() - self.t0) * 1000)
        if ts <= self.last_ts:
            ts = self.last_ts + 1
        self.last_ts = ts
        res = self.lm.detect_for_video(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb), ts)
        out = []
        poly = expand_poly(roi, 0.08) if roi else None
        worlds = getattr(res, "hand_world_landmarks", None) or []
        for i, hand in enumerate(res.hand_landmarks or []):
            lm = [(p.x, p.y) for p in hand]
            label = res.handedness[i][0].category_name if res.handedness else str(i)
            st = self.pinch.setdefault(label, PinchState())
            metres = None
            if i < len(worlds):
                w4, w8 = worlds[i][4], worlds[i][8]
                metres = math.sqrt((w4.x - w8.x) ** 2 + (w4.y - w8.y) ** 2 + (w4.z - w8.z) ** 2)
            pressed = st.update(pinch_ratio(lm), metres)
            x, y = (x0 + lm[8][0] * cw) / W, (y0 + lm[8][1] * ch) / H
            if poly and not point_in_poly(x, y, poly):
                continue
            out.append((x, y, 0, "doigt", pressed))
        return out

    def close(self):
        try:
            self.lm.close()
        except Exception:
            pass
