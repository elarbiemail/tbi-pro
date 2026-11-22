# -*- coding: utf-8 -*-
"""
Reconnaissance :
  • des formes tracées à main levée (hors ligne) : ligne, flèche, cercle/ellipse,
    rectangle/carré, triangle, polygone ;
  • de l'écriture manuscrite (en ligne, service de reconnaissance d'écriture de Google
    Input Tools, langue française), convertie en texte.
"""
import json
import math
import urllib.request

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None


def _path_len(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _resample(pts, n=64):
    L = _path_len(pts)
    if L == 0:
        return [pts[0]] * n
    step, out, acc = L / (n - 1), [pts[0]], 0.0
    pts = [tuple(p) for p in pts]
    i = 1
    prev = pts[0]
    while i < len(pts) and len(out) < n:
        d = math.dist(prev, pts[i])
        if acc + d >= step and d > 0:
            t = (step - acc) / d
            q = (prev[0] + t * (pts[i][0] - prev[0]), prev[1] + t * (pts[i][1] - prev[1]))
            out.append(q)
            prev, acc = q, 0.0
        else:
            acc += d
            prev = pts[i]
            i += 1
    while len(out) < n:
        out.append(pts[-1])
    return out


def _line_dev(pts, a, b):
    ax, ay = a
    bx, by = b
    L = math.dist(a, b) or 1
    return max(abs((bx - ax) * (ay - y) - (ax - x) * (by - ay)) / L for x, y in pts)


def _snap_angle(deg, tol=7):
    for target in (0, 45, 90, 135, 180, -45, -90, -135, -180):
        if abs(deg - target) <= tol:
            return target
    return deg


def recognize_shape(pts):
    """Trait (liste de points) → objet forme propre, ou None si rien de reconnu."""
    if len(pts) < 4:
        return None
    pts = [tuple(p) for p in pts]
    L = _path_len(pts)
    if L < 25:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    closed = math.dist(pts[0], pts[-1]) < 0.22 * L
    rs = _resample(pts, 64)

    if not closed:
        a, b = pts[0], pts[-1]
        if _line_dev(rs, a, b) < 0.06 * L + 3:
            # ligne droite, angle aimanté si presque horizontal / vertical / 45°
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            sa = math.radians(_snap_angle(ang))
            d = math.dist(a, b)
            b = (a[0] + d * math.cos(sa), a[1] + d * math.sin(sa))
            return {"k": "line", "p1": list(a), "p2": list(b)}
        # flèche : un segment principal puis un petit crochet « < » à la fin
        n = len(rs)
        for cut in range(int(n * 0.6), int(n * 0.92)):
            main = rs[:cut]
            if _line_dev(main, main[0], main[-1]) < 0.05 * L + 3:
                tail = rs[cut:]
                if _path_len(tail) < 0.45 * _path_len(main):
                    return {"k": "arrow", "p1": list(main[0]), "p2": list(main[-1])}
        return None

    if cv2 is None:
        return None
    cnt = np.array(rs, np.float32).reshape(-1, 1, 2)
    cx, cy = float(np.mean(xs)), float(np.mean(ys))
    # cercle / ellipse : distances au centre régulières
    try:
        (ex, ey), (MA, ma), ang = cv2.fitEllipse(cnt)
    except Exception:
        return None
    approx = cv2.approxPolyDP(cnt, 0.045 * L, True)
    nv = len(approx)
    # écart du tracé à l'ellipse ajustée
    a_, b_ = MA / 2 or 1, ma / 2 or 1
    t = math.radians(ang)
    devs = []
    for x, y in rs:
        dx, dy = x - ex, y - ey
        u = dx * math.cos(t) + dy * math.sin(t)
        v = -dx * math.sin(t) + dy * math.cos(t)
        devs.append(abs(math.hypot(u / a_, v / b_) - 1))
    ell_err = float(np.mean(devs))

    if nv == 3:
        tri = [list(map(float, p[0])) for p in approx]
        return {"k": "poly", "pts": tri}
    if nv == 4 and ell_err > 0.07:
        (rx, ry), (rw, rh), rang = cv2.minAreaRect(cnt)
        rang = _snap_angle(rang, 8)
        if abs(rang) in (90, 180):
            rw, rh, rang = rh, rw, 0
        if rang == -90:
            rang = 0
        if max(rw, rh) and min(rw, rh) / max(rw, rh) > 0.9:   # presque carré → carré
            rw = rh = (rw + rh) / 2
        it = {"k": "rect", "p1": [rx - rw / 2, ry - rh / 2], "p2": [rx + rw / 2, ry + rh / 2]}
        if rang:
            it["rot"] = rang
        return it
    if ell_err < 0.16:
        if min(MA, ma) / max(MA, ma) > 0.85:                 # presque rond → cercle
            r = (MA + ma) / 4
            return {"k": "ellipse", "p1": [ex - r, ey - r], "p2": [ex + r, ey + r]}
        # ellipse : axes alignés sur son propre repère, puis pivotée
        rot = _snap_angle(ang, 8) % 180
        if rot == 90:                                        # verticale/horizontale : pas de rotation
            MA, ma, rot = ma, MA, 0
        it = {"k": "ellipse", "p1": [ex - MA / 2, ey - ma / 2], "p2": [ex + MA / 2, ey + ma / 2]}
        if rot:
            it["rot"] = rot
        return it
    if 5 <= nv <= 8:
        return {"k": "poly", "pts": [list(map(float, p[0])) for p in approx]}
    return None


# ----------------------------------------------------------------------------
# Écriture manuscrite → texte
# ----------------------------------------------------------------------------
HW_URL = "https://inputtools.google.com/request?ime=handwriting&app=mobilesearch&cs=1&oe=UTF-8"


def recognize_handwriting(strokes, width, height, lang="fr", timeout=10):
    """
    strokes : liste de traits, chaque trait = liste de [x, y].
    Renvoie la liste des propositions (la meilleure en premier).
    """
    ink = []
    t = 0
    for s in strokes:
        xs = [int(p[0]) for p in s]
        ys = [int(p[1]) for p in s]
        ts = list(range(t, t + 10 * len(s), 10))
        t += 10 * len(s) + 200
        ink.append([xs, ys, ts])
    body = {"options": "enable_pre_space",
            "requests": [{"writing_guide": {"writing_area_width": int(width), "writing_area_height": int(height)},
                          "ink": ink, "language": lang}]}
    req = urllib.request.Request(HW_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "TBIPro/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data or data[0] != "SUCCESS":
        raise RuntimeError("réponse inattendue du service")
    return list(data[1][0][1])


# ----------------------------------------------------------------------------
# Croquis → icônes (même principe que Google AutoDraw)
# ----------------------------------------------------------------------------
AD_URL = "https://inputtools.google.com/request?ime=handwriting&app=autodraw&dbg=1&cs=1&oe=UTF-8"


def recognize_sketch(strokes, width, height, timeout=10):
    """Dessin à main levée → liste de noms d'objets probables (en anglais : « cat », « house »…)."""
    ink = []
    t = 0
    for s in strokes:
        xs = [int(p[0]) for p in s]
        ys = [int(p[1]) for p in s]
        ink.append([xs, ys, list(range(t, t + 10 * len(s), 10))])
        t += 10 * len(s) + 200
    body = {"input_type": 0, "requests": [{"language": "autodraw", "ink": ink,
                                           "writing_guide": {"width": int(width), "height": int(height)}}]}
    req = urllib.request.Request(AD_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "TBIPro/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data or data[0] != "SUCCESS":
        raise RuntimeError("réponse inattendue du service")
    return [c for c in data[1][0][1] if c][:10]


def icon_for(name, timeout=8):
    """Première icône couleur libre (Fluent Emoji, Noto, OpenMoji, Twemoji) correspondant au nom → SVG."""
    import urllib.parse
    q = urllib.parse.quote(name.replace("-", " "))
    url = f"https://api.iconify.design/search?limit=3&prefixes=fluent-emoji-flat,noto,openmoji,twemoji&query={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "TBIPro/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        icons = json.loads(r.read().decode("utf-8")).get("icons", [])
    if not icons:
        return None
    prefix, icon = icons[0].split(":", 1)
    req = urllib.request.Request(f"https://api.iconify.design/{prefix}/{icon}.svg?height=256",
                                 headers={"User-Agent": "TBIPro/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()
