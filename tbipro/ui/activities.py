# -*- coding: utf-8 -*-
"""Activités de classe : chronomètre/minuteur, nuage de mots collaboratif, carte mentale."""
import asyncio
import json
import math
import random
import re
import threading
import time
from collections import Counter

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .keyboard import DIALOG_CSS, TextDialog, VirtualKeyboard, projected_dialog
from .mindmap import mindmap_bounds, draw_mindmap, parse_outline


# ============================================================================
# Chronomètre / minuteur (panneau flottant sur le tableau ou l'annotation)
# ============================================================================
class TimerPanel(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("timer")
        self.setStyleSheet("""
            QFrame#timer { background: rgba(15,23,42,235); border-radius: 16px; }
            QLabel#digits { color: #f8fafc; font: 700 64px "Consolas","Segoe UI"; }
            QLabel#mode { color: #7dd3fc; font: 600 13px "Segoe UI"; }
            QPushButton { background:#1e293b; color:#f1f5f9; border-radius:10px; min-width:54px; min-height:50px;
                          font: 600 18px "Segoe UI Emoji","Segoe UI"; border:0; }
            QPushButton:pressed { background:#0369a1; }
        """)
        self.countdown = True
        self.total = 5 * 60.0          # durée du minuteur
        self.elapsed = 0.0
        self.running = False
        self.t_start = 0.0
        self.finished = False
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 12)
        self.mode_lbl = QLabel()
        self.mode_lbl.setObjectName("mode")
        self.mode_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(self.mode_lbl)
        self.digits = QLabel()
        self.digits.setObjectName("digits")
        self.digits.setAlignment(Qt.AlignCenter)
        v.addWidget(self.digits)
        g = QGridLayout()
        g.setSpacing(6)
        btns = [("−1", lambda: self.adjust(-60)), ("+1", lambda: self.adjust(60)), ("+5", lambda: self.adjust(300)),
                ("⏯️", self.toggle), ("⟲", self.reset), ("⏱️", self.switch_mode), ("✖", self.hide)]
        for i, (t, fn) in enumerate(btns):
            b = QPushButton(t)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            g.addWidget(b, i // 4, i % 4)
        v.addLayout(g)
        self.timer = QTimer(self, interval=200, timeout=self.tick)
        self.refresh()
        self.hide()

    def value(self):
        e = self.elapsed + (time.time() - self.t_start if self.running else 0)
        return max(0.0, self.total - e) if self.countdown else e

    def toggle(self):
        if self.running:
            self.elapsed += time.time() - self.t_start
            self.running = False
            self.timer.stop()
        else:
            if self.countdown and self.value() <= 0:
                self.reset()
            self.t_start = time.time()
            self.running = True
            self.finished = False
            self.timer.start()
        self.refresh()

    def reset(self):
        self.running = False
        self.elapsed = 0.0
        self.finished = False
        self.timer.stop()
        self.refresh()

    def adjust(self, sec):
        if self.countdown:
            self.total = max(10.0, self.total + sec)
        self.refresh()

    def switch_mode(self):
        self.countdown = not self.countdown
        self.reset()

    def tick(self):
        if self.countdown and self.running and self.value() <= 0:
            self.elapsed = self.total
            self.running = False
            self.finished = True
            self.timer.stop()
            for i in range(3):
                QTimer.singleShot(i * 400, QApplication.beep)
            self._flash = 0
            QTimer.singleShot(0, self._blink)
        self.refresh()

    def _blink(self):
        self._flash += 1
        self.digits.setVisible(self._flash % 2 == 0)
        if self._flash < 12:
            QTimer.singleShot(300, self._blink)
        else:
            self.digits.setVisible(True)

    def refresh(self):
        v = self.value()
        m, s = divmod(int(math.ceil(v) if self.countdown else int(v)), 60)
        self.digits.setText(f"{m:02d}:{s:02d}")
        warn = self.countdown and (v <= 10 and (self.running or self.finished))
        self.digits.setStyleSheet("color:#f87171;" if warn else "")
        state = "en cours" if self.running else ("terminé !" if self.finished else "prêt")
        self.mode_lbl.setText(("⏳ MINUTEUR" if self.countdown else "⏱️ CHRONOMÈTRE") + f" — {state}")

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.adjustSize()
            p = self.parentWidget()
            self.move(p.width() - self.width() - 20, 20)
            self.raise_()


# ============================================================================
# Nuage de mots
# ============================================================================
STUDENT_PAGE = """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Nuage de mots</title>
<style>body{margin:0;font:18px system-ui,sans-serif;background:#0f172a;color:#f1f5f9;display:flex;min-height:100vh;
align-items:center;justify-content:center}.c{width:min(92vw,480px);text-align:center}
h1{font-size:22px;color:#7dd3fc}#q{font-size:20px;margin:10px 0 20px}
input{width:100%;box-sizing:border-box;padding:16px;font-size:20px;border-radius:12px;border:0}
button{margin-top:14px;width:100%;padding:16px;font-size:20px;border:0;border-radius:12px;background:#0284c7;color:#fff;font-weight:700}
#msg{margin-top:14px;min-height:24px;color:#86efac}</style></head><body><div class="c">
<h1>☁️ Nuage de mots</h1><div id="q"></div>
<form id="f"><input id="m" maxlength="40" autocomplete="off" placeholder="Votre mot ou expression" required>
<button>Envoyer</button></form><div id="msg"></div></div>
<script>
const q=document.getElementById('q'),msg=document.getElementById('msg');
async function etat(){try{const r=await fetch('/etat');const e=await r.json();q.textContent=e.question||'';
if(!e.ouvert){msg.style.color='#fca5a5';msg.textContent='Les réponses sont fermées.';}}catch(e){}}
etat();setInterval(etat,4000);
document.getElementById('f').onsubmit=async ev=>{ev.preventDefault();const i=document.getElementById('m');
try{const r=await fetch('/mot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mot:i.value})});
const j=await r.json();msg.style.color=j.ok?'#86efac':'#fca5a5';msg.textContent=j.message;if(j.ok)i.value='';}
catch(e){msg.style.color='#fca5a5';msg.textContent='Envoi impossible.';}};
</script></body></html>"""


class ActivityServer:
    """Petit serveur web (HTTP) : les élèves envoient leurs mots depuis leur téléphone."""
    _inst = None

    @classmethod
    def get(cls, port=8444):
        if cls._inst is None:
            cls._inst = cls(port)
            cls._inst.start()
        return cls._inst

    def __init__(self, port):
        self.port = port
        self.words = []
        self.question = ""
        self.open = True
        self.per_ip = Counter()
        self.lock = threading.Lock()
        self.error = ""
        from ..sources import lan_ips
        self.url = f"http://{lan_ips()[0]}:{port}"

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def clear(self):
        with self.lock:
            self.words.clear()
            self.per_ip.clear()

    def add(self, word, ip="prof"):
        w = re.sub(r"\s+", " ", (word or "")).strip().strip(".,;:!?\"'«»()").strip()[:40]
        if not w:
            return False, "Mot vide."
        with self.lock:
            if not self.open and ip != "prof":
                return False, "Les réponses sont fermées."
            if ip != "prof" and self.per_ip[ip] >= 10:
                return False, "Vous avez déjà envoyé 10 mots."
            self.per_ip[ip] += 1
            self.words.append(w)
        return True, f"Merci ! « {w} » a été ajouté."

    def counts(self):
        with self.lock:
            groups = {}
            for w in self.words:
                k = w.lower()
                groups.setdefault(k, Counter())[w] += 1
        return {c.most_common(1)[0][0]: sum(c.values()) for c in groups.values()}

    def _run(self):
        try:
            from aiohttp import web
        except ImportError:
            self.error = "Module aiohttp manquant"
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def page(request):
            return web.Response(text=STUDENT_PAGE, content_type="text/html")

        async def etat(request):
            return web.json_response({"question": self.question, "ouvert": self.open})

        async def mot(request):
            try:
                data = await request.json()
            except Exception:
                return web.json_response({"ok": False, "message": "Requête invalide."})
            ok, m = self.add(str(data.get("mot", "")), request.remote or "?")
            return web.json_response({"ok": ok, "message": m})

        app = web.Application()
        app.router.add_get("/", page)
        app.router.add_get("/etat", etat)
        app.router.add_post("/mot", mot)
        try:
            runner = web.AppRunner(app, access_log=None)
            loop.run_until_complete(runner.setup())
            loop.run_until_complete(web.TCPSite(runner, "0.0.0.0", self.port).start())
        except Exception as e:
            self.error = f"Serveur du nuage de mots indisponible : {e}"
            return
        loop.run_forever()


CLOUD_COLORS = ["#1d4ed8", "#dc2626", "#059669", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#4d7c0f", "#b45309"]


def render_cloud(counts, w=1400, h=800, seed=7, transparent=False):
    """Nuage de mots : taille selon la fréquence, placement en spirale sans chevauchement."""
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.transparent if transparent else QColor("white"))
    if not counts:
        return img
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    rng = random.Random(seed)
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:120]
    mx, mn = items[0][1], items[-1][1]
    placed = []
    scale = 1.0
    for attempt in range(4):                       # si tout ne rentre pas, on réduit
        placed.clear()
        ok_all = True
        for i, (word, n) in enumerate(items):
            t = (n - mn) / (mx - mn) if mx > mn else 1.0
            size = int((22 + 88 * math.sqrt(t)) * scale * (1.15 if i == 0 else 1))
            f = QFont("Segoe UI", 10, QFont.Bold if t > 0.4 else QFont.DemiBold)
            f.setPixelSize(max(12, size))
            fm = QFontMetricsF(f)
            bw, bh = fm.horizontalAdvance(word) + 8, fm.height()
            pos = None
            a = rng.random() * 6.28
            for k in range(2500):
                r = 3.2 * math.sqrt(k) * 3
                ang = a + k * 0.35
                x = w / 2 + r * math.cos(ang) * 1.6 - bw / 2
                y = h / 2 + r * math.sin(ang) - bh / 2
                rect = QRectF(x, y, bw, bh)
                if x < 4 or y < 4 or x + bw > w - 4 or y + bh > h - 4:
                    continue
                if all(not rect.intersects(q[0]) for q in placed):
                    pos = rect
                    break
            if pos is None:
                ok_all = False
                continue
            placed.append((pos, word, f, CLOUD_COLORS[i % len(CLOUD_COLORS)], fm.ascent()))
        if ok_all:
            break
        scale *= 0.82
    for rect, word, f, col, asc in placed:
        p.setFont(f)
        p.setPen(QColor(col))
        p.drawText(QPointF(rect.x() + 4, rect.y() + asc), word)
    p.end()
    return img


class WordCloudDialog(QDialog):
    def __init__(self, canvas, parent=None, screen=None):
        super().__init__(parent)
        self.canvas = canvas
        self.srv = ActivityServer.get()
        self.setWindowTitle("Nuage de mots")
        self.setStyleSheet(DIALOG_CSS + "QLabel#info{color:#94a3b8;font-size:11pt;} QLabel#q{font-size:15pt;}")
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 0)
        t = QLabel("☁️ Nuage de mots")
        t.setObjectName("title")
        left.addWidget(t)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        left.addWidget(self.qr)
        self.url = QLabel(self.srv.url)
        self.url.setAlignment(Qt.AlignCenter)
        self.url.setStyleSheet("font-size:16pt;font-weight:700;color:#fde68a;")
        left.addWidget(self.url)
        info = QLabel("Les élèves scannent le QR code (même Wi-Fi) et envoient leurs mots.")
        info.setObjectName("info")
        info.setWordWrap(True)
        left.addWidget(info)
        self.q_lbl = QLabel("Question : (aucune)")
        self.q_lbl.setObjectName("q")
        self.q_lbl.setWordWrap(True)
        left.addWidget(self.q_lbl)
        for text, fn in [("✏️ Poser la question", self.set_question), ("➕ Ajouter un mot", self.add_word),
                         ("⏸️ Fermer les réponses", self.toggle_open), ("🗑️ Vider le nuage", self.clear),
                         ("📋 Insérer dans le tableau", self.insert)]:
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            if text.startswith("📋"):
                b.setObjectName("ok")
            if text.startswith("⏸️"):
                self.open_btn = b
            left.addWidget(b)
        left.addStretch(1)
        close = QPushButton("✖ Fermer")
        close.setObjectName("cancel")
        close.clicked.connect(self.accept)
        left.addWidget(close)
        right = QVBoxLayout()
        root.addLayout(right, 1)
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("info")
        right.addWidget(self.count_lbl)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background:white;border-radius:12px;")
        self.view.setMinimumSize(600, 400)
        right.addWidget(self.view, 1)
        try:
            from .control import qr_pixmap
            self.qr.setPixmap(qr_pixmap(self.srv.url, 220))
        except Exception:
            pass
        self._last = None
        self.timer = QTimer(self, interval=1000, timeout=self.refresh)
        self.timer.start()
        projected_dialog(self, screen, full=True)
        QTimer.singleShot(50, self.refresh)

    def refresh(self):
        c = self.srv.counts()
        n = sum(c.values())
        err = f" — {self.srv.error}" if self.srv.error else ""
        self.count_lbl.setText(f"{n} réponse(s), {len(c)} mot(s) différent(s){err}")
        key = (tuple(sorted(c.items())), self.view.width(), self.view.height())
        if key == self._last:
            return
        self._last = key
        w, h = max(600, self.view.width() - 10), max(400, self.view.height() - 10)
        self.view.setPixmap(QPixmap.fromImage(render_cloud(c, w, h)))

    def set_question(self):
        d = TextDialog("Question posée aux élèves", self.srv.question, self, self.screen())
        if d.exec():
            self.srv.question = d.text().strip()
            self.q_lbl.setText("Question : " + (self.srv.question or "(aucune)"))

    def add_word(self):
        d = TextDialog("Ajouter un mot", "", self, self.screen())
        if d.exec():
            self.srv.add(d.text())
            self.refresh()

    def toggle_open(self):
        self.srv.open = not self.srv.open
        self.open_btn.setText("⏸️ Fermer les réponses" if self.srv.open else "▶️ Rouvrir les réponses")

    def clear(self):
        self.srv.clear()
        self.refresh()

    def insert(self):
        c = self.srv.counts()
        if not c:
            return
        W, H = self.canvas.page["size"]
        img = render_cloud(c, int(W * 0.8), int(H * 0.75), transparent=False)
        self.canvas.insert_qimage(img, "", max_frac=0.85)
        self.accept()


# ============================================================================
# Carte mentale
# ============================================================================
EXAMPLE = """Le récit
    Personnages
        Héros
        Opposant
    Cadre
        Lieu
        Époque
    Schéma narratif
        Situation initiale
        Péripéties
        Situation finale
    Narrateur"""


class MindmapDialog(QDialog):
    def __init__(self, canvas, parent=None, screen=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setWindowTitle("Carte mentale")
        self.setStyleSheet(DIALOG_CSS + "QPlainTextEdit{font-size:15pt;} QLabel#info{color:#94a3b8;font-size:11pt;}")
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 1)
        t = QLabel("🧠 Carte mentale")
        t.setObjectName("title")
        left.addWidget(t)
        info = QLabel("1re ligne : idée centrale. Puis une branche par ligne ; « ⇥ Sous-idée » (ou 4 espaces) "
                      "pour une sous-branche.")
        info.setObjectName("info")
        info.setWordWrap(True)
        left.addWidget(info)
        self.edit = QPlainTextEdit(EXAMPLE)
        left.addWidget(self.edit, 1)
        left.addWidget(VirtualKeyboard(self.edit))
        right = QVBoxLayout()
        root.addLayout(right, 1)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet("background:white;border-radius:12px;")
        self.view.setMinimumSize(500, 400)
        right.addWidget(self.view, 1)
        row = QHBoxLayout()
        bc = QPushButton("✖ Annuler")
        bc.setObjectName("cancel")
        bc.clicked.connect(self.reject)
        bo = QPushButton("📋 Insérer dans le tableau")
        bo.setObjectName("ok")
        bo.clicked.connect(self.insert)
        row.addWidget(bc)
        row.addWidget(bo)
        right.addLayout(row)
        self.edit.textChanged.connect(lambda: self.preview_timer.start())
        self.preview_timer = QTimer(self, singleShot=True, interval=300, timeout=self.preview)
        projected_dialog(self, screen, full=True)
        QTimer.singleShot(50, self.preview)

    def _item(self, cx, cy, s=1.0):
        tree = parse_outline(self.edit.toPlainText())
        return None if tree is None else {"k": "mindmap", "p": [cx, cy], "tree": tree, "s": s}

    def _fit(self, W, H, frac=0.92):
        it = self._item(0, 0)
        if it is None:
            return None
        b = mindmap_bounds(it)
        s = min(1.0, W * frac / max(b.width(), 1), H * frac / max(b.height(), 1))
        it["s"] = s
        b = mindmap_bounds(it)
        it["p"] = [W / 2 - b.center().x(), H / 2 - b.center().y()]
        return it

    def preview(self):
        w, h = max(500, self.view.width() - 10), max(400, self.view.height() - 10)
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(QColor("white"))
        it = self._fit(w, h)
        if it:
            p = QPainter(img)
            draw_mindmap(p, it)
            p.end()
        self.view.setPixmap(QPixmap.fromImage(img))

    def insert(self):
        W, H = self.canvas.page["size"]
        it = self._fit(W, H, 0.85)
        if it:
            self.canvas.add_item(it)
        self.accept()


# ============================================================================
# Tirage au sort (élèves) et dé
# ============================================================================
class PickerDialog(QDialog):
    def __init__(self, parent=None, screen=None):
        super().__init__(parent)
        import os
        from ..config import app_dir
        self.path = os.path.join(app_dir(), "eleves.txt")
        self.setWindowTitle("Tirage au sort")
        self.setStyleSheet(DIALOG_CSS + """
            QLabel#big { font: 800 72px "Segoe UI"; color: #fde68a; }
            QLabel#info { color:#94a3b8; font-size:11pt; }
            QPlainTextEdit { font-size: 14pt; }""")
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 1)
        t = QLabel("🎲 Tirage au sort")
        t.setObjectName("title")
        left.addWidget(t)
        info = QLabel("Liste des élèves (un nom par ligne). Elle est gardée pour la prochaine fois.")
        info.setObjectName("info")
        info.setWordWrap(True)
        left.addWidget(info)
        self.edit = QPlainTextEdit()
        try:
            self.edit.setPlainText(open(self.path, encoding="utf-8").read())
        except OSError:
            self.edit.setPlainText("Amine\nSalma\nYoussef\nKhadija\nOmar\nFatima Zahra")
        left.addWidget(self.edit, 1)
        kb = QPushButton("⌨️ Clavier")
        kb.clicked.connect(lambda: self._kb())
        left.addWidget(kb)
        right = QVBoxLayout()
        root.addLayout(right, 1)
        self.big = QLabel("?")
        self.big.setObjectName("big")
        self.big.setAlignment(Qt.AlignCenter)
        self.big.setWordWrap(True)
        self.big.setMinimumHeight(260)
        self.big.setStyleSheet("background:#1e293b;border-radius:18px;")
        right.addWidget(self.big, 1)
        self.history = QLabel("")
        self.history.setObjectName("info")
        self.history.setWordWrap(True)
        right.addWidget(self.history)
        row = QHBoxLayout()
        self.no_repeat = QPushButton("Sans remise : OUI")
        self.no_repeat.clicked.connect(self._toggle_rep)
        self.avoid = True
        row.addWidget(self.no_repeat)
        reset = QPushButton("⟲ Réinitialiser")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        right.addLayout(row)
        row = QHBoxLayout()
        go = QPushButton("🎯 Tirer un élève")
        go.setObjectName("ok")
        go.clicked.connect(self.draw_name)
        dice = QPushButton("🎲 Lancer le dé")
        dice.clicked.connect(self.roll)
        row.addWidget(go, 2)
        row.addWidget(dice, 1)
        right.addLayout(row)
        close = QPushButton("✖ Fermer")
        close.setObjectName("cancel")
        close.clicked.connect(self.accept)
        right.addWidget(close)
        self.drawn = []
        self.anim = QTimer(self, interval=70, timeout=self._spin)
        self.spin_left = 0
        projected_dialog(self, screen, size=(1200, 700))

    def _kb(self):
        d = QDialog(self)
        d.setStyleSheet(DIALOG_CSS)
        v = QVBoxLayout(d)
        v.addWidget(VirtualKeyboard(self.edit))
        b = QPushButton("OK")
        b.setObjectName("ok")
        b.clicked.connect(d.accept)
        v.addWidget(b)
        projected_dialog(d, self.screen(), size=(1000, 420))
        d.exec()

    def names(self):
        return [n.strip() for n in self.edit.toPlainText().splitlines() if n.strip()]

    def _toggle_rep(self):
        self.avoid = not self.avoid
        self.no_repeat.setText("Sans remise : " + ("OUI" if self.avoid else "NON"))

    def _reset(self):
        self.drawn = []
        self.history.setText("")
        self.big.setText("?")

    def draw_name(self):
        pool = [n for n in self.names() if not (self.avoid and n in self.drawn)]
        if not pool:
            self.big.setText("Tout le monde\na été tiré !")
            return
        self.pool = pool
        self.final = random.choice(pool)
        self.spin_left = 18
        self.anim.start()

    def _spin(self):
        self.spin_left -= 1
        if self.spin_left <= 0:
            self.anim.stop()
            self.big.setText(self.final)
            self.drawn.append(self.final)
            self.history.setText("Déjà tirés : " + ", ".join(self.drawn))
            return
        self.big.setText(random.choice(self.pool))

    def roll(self):
        faces = "⚀⚁⚂⚃⚄⚅"
        self.final = random.choice(faces)
        self.pool = list(faces)
        self.spin_left = 12
        self.anim.start()

    def done(self, r):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(self.edit.toPlainText())
        except OSError:
            pass
        super().done(r)


# ============================================================================
# Gestion des pages (aperçus)
# ============================================================================
class PagesDialog(QDialog):
    def __init__(self, canvas, parent=None, screen=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea, QToolButton
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        self.QToolButton, self.QIcon, self.QSize = QToolButton, QIcon, QSize
        self.canvas = canvas
        self.sel = canvas.index
        self.setWindowTitle("Pages")
        self.setStyleSheet(DIALOG_CSS + """
            QToolButton { background:#1e293b; border:3px solid transparent; border-radius:12px; color:#e2e8f0;
                          font-size:12pt; }
            QToolButton[sel="true"] { border-color:#38bdf8; }
            QScrollBar:vertical { width:30px; }""")
        v = QVBoxLayout(self)
        t = QLabel("🗂️ Pages du tableau — touchez une page pour la sélectionner")
        t.setObjectName("title")
        v.addWidget(t)
        area = QScrollArea()
        area.setWidgetResizable(True)
        self.holder = QWidget()
        self.grid = QGridLayout(self.holder)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        area.setWidget(self.holder)
        v.addWidget(area, 1)
        row = QHBoxLayout()
        for text, fn in [("👁️ Afficher", self.open_page), ("⧉ Dupliquer", self.dup), ("⬅️ Avancer", lambda: self.move(-1)),
                         ("➡️ Reculer", lambda: self.move(1)), ("🗑️ Supprimer", self.delete), ("✖ Fermer", self.accept)]:
            b = QPushButton(text)
            if text.startswith("👁"):
                b.setObjectName("ok")
            if text.startswith("✖"):
                b.setObjectName("cancel")
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        v.addLayout(row)
        projected_dialog(self, screen, full=True)
        self.fill()

    def fill(self):
        g = self.grid
        while g.count():
            g.takeAt(0).widget().deleteLater()
        cols = max(2, (self.width() - 80) // 300)
        self.btns = []
        for i in range(len(self.canvas.pages)):
            b = self.QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(self.QIcon(QPixmap.fromImage(self.canvas.page_thumbnail(i, 260))))
            b.setIconSize(self.QSize(260, 160))
            b.setText(f"Page {i + 1}")
            b.setFixedSize(286, 210)
            b.setProperty("sel", i == self.sel)
            b.clicked.connect(lambda _=False, i=i: self.pick(i))
            g.addWidget(b, i // cols, i % cols)
            self.btns.append(b)

    def pick(self, i):
        self.sel = i
        for j, b in enumerate(self.btns):
            b.setProperty("sel", j == i)
            b.style().unpolish(b)
            b.style().polish(b)

    def open_page(self):
        self.canvas.go_page(self.sel)
        self.accept()

    def dup(self):
        import copy
        c = self.canvas
        pg = c.pages[self.sel]
        new = {k: (copy.copy(v) if k == "items" else v) for k, v in pg.items() if not k.startswith("_")}
        new["items"] = list(pg["items"])
        new["undo"], new["redo"] = [], []
        c.pages.insert(self.sel + 1, new)
        self.sel += 1
        self.fill()

    def move(self, d):
        c = self.canvas
        j = self.sel + d
        if 0 <= j < len(c.pages):
            c.pages[self.sel], c.pages[j] = c.pages[j], c.pages[self.sel]
            self.sel = j
            self.fill()

    def delete(self):
        c = self.canvas
        if len(c.pages) <= 1:
            return
        del c.pages[self.sel]
        self.sel = min(self.sel, len(c.pages) - 1)
        c.index = min(c.index, len(c.pages) - 1)
        self.fill()

    def done(self, r):
        self.canvas.invalidate()
        super().done(r)
