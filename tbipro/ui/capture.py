# -*- coding: utf-8 -*-
"""
Capture intégrée :
  • capture d'image : écran entier ou zone choisie au stylet ;
  • éditeur d'image : recadrer, flèche, cadre, stylo, surligneur, texte, flou (masquer des
    informations), couleurs, annuler, enregistrer, copier, insérer dans le tableau ;
  • enregistrement vidéo de l'écran (entier ou zone) en MP4 ;
  • éditeur vidéo : lecture, choix du début et de la fin (découpe), export MP4.
"""
import datetime
import math
import os
import queue
import threading
import time

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from ..config import documents_dir
from . import audio
from .keyboard import DIALOG_CSS, TextDialog, projected_dialog

EDIT_COLORS = ["#dc2626", "#f59e0b", "#16a34a", "#2563eb", "#9333ea", "#111827", "#ffffff"]


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%Hh%M-%S")


def captures_dir():
    d = os.path.join(documents_dir(), "Captures")
    os.makedirs(d, exist_ok=True)
    return d


def videos_dir():
    d = os.path.join(documents_dir(), "Vidéos")
    os.makedirs(d, exist_ok=True)
    return d


def grab_screen(screen, hide=()):
    """Capture l'écran en masquant un instant les éléments de TBI Pro (barre d'outils…)."""
    hidden = [w for w in hide if w is not None and w.isVisible()]
    for w in hidden:
        w.hide()
    QApplication.processEvents()
    time.sleep(0.15)
    QApplication.processEvents()
    pm = screen.grabWindow(0)
    for w in hidden:
        w.show()
    return pm.toImage()


def qimage_to_bgr(img):
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, np.uint8, count=img.bytesPerLine() * h).reshape(h, img.bytesPerLine())
    arr = arr[:, :w * 3].reshape(h, w, 3)
    return arr[:, :, ::-1].copy()


def bgr_to_qimage(arr):
    rgb = np.ascontiguousarray(arr[:, :, ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


# ============================================================================
# Choix d'une zone de l'écran
# ============================================================================
class RegionSelector(QDialog):
    """Image figée de l'écran, assombrie : on trace au stylet le rectangle à capturer."""

    def __init__(self, image, screen, title="Tracez la zone à capturer"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.image, self.title = image, title
        self.p0 = self.p1 = None
        self.rect_result = None
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, e):
        self.p0 = self.p1 = e.position()
        self.update()

    def mouseMoveEvent(self, e):
        if self.p0 is not None:
            self.p1 = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if self.p0 is None:
            return
        r = QRectF(self.p0, e.position()).normalized()
        if r.width() > 12 and r.height() > 12:
            sx = self.image.width() / self.width()
            sy = self.image.height() / self.height()
            self.rect_result = QRect(int(r.x() * sx), int(r.y() * sy), int(r.width() * sx), int(r.height() * sy))
            self.accept()
        else:
            self.p0 = None
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.reject()

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawImage(self.rect(), self.image)
        p.fillRect(self.rect(), QColor(2, 6, 23, 140))
        if self.p0 is not None:
            r = QRectF(self.p0, self.p1).normalized()
            sx = self.image.width() / self.width()
            sy = self.image.height() / self.height()
            p.drawImage(r, self.image, QRectF(r.x() * sx, r.y() * sy, r.width() * sx, r.height() * sy))
            p.setPen(QPen(QColor(56, 189, 248), 3, Qt.DashLine))
            p.drawRect(r)
            p.setPen(QColor("white"))
            p.setFont(QFont("Segoe UI", 12, QFont.Bold))
            p.drawText(r.topLeft() + QPointF(6, -8), f"{int(r.width() * sx)} × {int(r.height() * sy)}")
        p.setPen(QColor("white"))
        p.setFont(QFont("Segoe UI", 20, QFont.Bold))
        p.drawText(QRectF(0, 24, self.width(), 40), Qt.AlignCenter, self.title + "   (Échap = annuler)")


# ============================================================================
# Éditeur d'image
# ============================================================================
class _EditCanvas(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.ed = editor
        self.p0 = self.p1 = None
        self.path = []
        self.setMinimumSize(400, 300)

    def _geom(self):
        img = self.ed.image
        s = min(self.width() / img.width(), self.height() / img.height())
        w, h = img.width() * s, img.height() * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), s

    def to_img(self, pos):
        r, s = self._geom()
        return QPointF((pos.x() - r.x()) / s, (pos.y() - r.y()) / s)

    def mousePressEvent(self, e):
        q = self.to_img(e.position())
        if self.ed.tool == "text":
            self.ed.add_text(q)
            return
        self.p0 = self.p1 = q
        self.path = [q]
        self.update()

    def mouseMoveEvent(self, e):
        if self.p0 is None:
            return
        self.p1 = self.to_img(e.position())
        self.path.append(self.p1)
        self.update()

    def mouseReleaseEvent(self, e):
        if self.p0 is None:
            return
        self.ed.commit(self.p0, self.to_img(e.position()), self.path)
        self.p0 = None
        self.path = []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0b1220"))
        r, s = self._geom()
        p.drawImage(r, self.ed.image)
        if self.p0 is not None:
            p.save()
            p.translate(r.x(), r.y())
            p.scale(s, s)
            if self.ed.tool in ("crop", "blur"):
                rr = QRectF(self.p0, self.p1).normalized()
                p.setPen(QPen(QColor(56, 189, 248), 3 / s, Qt.DashLine))
                p.setBrush(QColor(56, 189, 248, 40))
                p.drawRect(rr)
            else:
                self.ed.paint_op(p, self.ed.tool, self.p0, self.p1, self.path)
            p.restore()


class ImageEditor(QDialog):
    def __init__(self, image, canvas=None, parent=None, screen=None):
        super().__init__(parent)
        self.image = image.convertToFormat(QImage.Format_ARGB32)
        self.canvas = canvas
        self.history = []
        self.tool = "arrow"
        self.color = "#dc2626"
        self.width = 6
        self.setWindowTitle("Éditeur de capture")
        self.setStyleSheet(DIALOG_CSS + """
            QPushButton { min-height:46px; font-size:15pt; }
            QPushButton[sel="true"] { background:#0369a1; border-color:#38bdf8; }
            QLabel#info { color:#94a3b8; font-size:11pt; }""")
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        t = QLabel("🖼️ Éditeur de capture")
        t.setObjectName("title")
        top.addWidget(t, 1)
        self.info = QLabel(f"{self.image.width()} × {self.image.height()} px")
        self.info.setObjectName("info")
        top.addWidget(self.info)
        root.addLayout(top)
        body = QHBoxLayout()
        root.addLayout(body, 1)
        side = QGridLayout()
        side.setSpacing(6)
        self.tool_btns = {}
        tools = [("crop", "✂️", "Recadrer"), ("arrow", "➚", "Flèche"), ("rect", "▭", "Cadre"),
                 ("ellipse", "◯", "Cercle"), ("pen", "✏️", "Stylo"), ("marker", "🖍️", "Surligneur"),
                 ("text", "🔤", "Texte"), ("blur", "🌫️", "Flouter (masquer)"), ("number", "①", "Numéro")]
        for i, (k, icon, tip) in enumerate(tools):
            b = QPushButton(icon)
            b.setToolTip(tip)
            b.setFixedSize(64, 54)
            b.clicked.connect(lambda _=False, k=k: self.set_tool(k))
            self.tool_btns[k] = b
            side.addWidget(b, i // 2, i % 2)
        r0 = (len(tools) + 1) // 2
        self.color_btns = {}
        for i, c in enumerate(EDIT_COLORS):
            b = QPushButton("")
            b.setFixedSize(64, 40)
            b.setStyleSheet(f"QPushButton{{background:{c};}} QPushButton[sel=\"true\"]{{border:3px solid #38bdf8;}}")
            b.clicked.connect(lambda _=False, c=c: self.set_color(c))
            self.color_btns[c] = b
            side.addWidget(b, r0 + i // 2, i % 2)
        r0 += (len(EDIT_COLORS) + 1) // 2
        for i, (w, icon) in enumerate([(3, "•"), (6, "●"), (12, "⬤")]):
            b = QPushButton(icon)
            b.setFixedSize(64, 46)
            b.clicked.connect(lambda _=False, w=w: setattr(self, "width", w))
            side.addWidget(b, r0 + i // 2, i % 2)
        r0 += 2
        und = QPushButton("↶")
        und.setToolTip("Annuler")
        und.setFixedSize(64, 54)
        und.clicked.connect(self.undo)
        side.addWidget(und, r0, 0)
        side.setRowStretch(r0 + 1, 1)
        sw = QWidget()
        sw.setLayout(side)
        body.addWidget(sw)
        self.view = _EditCanvas(self)
        body.addWidget(self.view, 1)
        row = QHBoxLayout()
        for text, fn, name in [("💾 Enregistrer", self.save, ""), ("📋 Copier", self.copy, ""),
                               ("📌 Insérer dans le tableau", self.insert, "ok"), ("✖ Fermer", self.reject, "cancel")]:
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            if text.startswith("📌") and canvas is None:
                b.setEnabled(False)
            row.addWidget(b)
        root.addLayout(row)
        self.counter = 1
        projected_dialog(self, screen, full=True)
        self.set_tool("arrow")
        self.set_color(self.color)

    def _mark(self, d, key):
        for k, b in d.items():
            b.setProperty("sel", k == key)
            b.style().unpolish(b)
            b.style().polish(b)

    def set_tool(self, k):
        self.tool = k
        self._mark(self.tool_btns, k)

    def set_color(self, c):
        self.color = c
        self._mark(self.color_btns, c)

    def _push(self):
        self.history.append(self.image.copy())
        del self.history[:-30]

    def undo(self):
        if self.history:
            self.image = self.history.pop()
            self.info.setText(f"{self.image.width()} × {self.image.height()} px")
            self.view.update()

    def paint_op(self, p, tool, p0, p1, path):
        col = QColor(self.color)
        w = self.width * max(1.0, self.image.width() / 1600)
        p.setRenderHint(QPainter.Antialiasing)
        if tool == "marker":
            col.setAlpha(110)
            w *= 3
        pen = QPen(col, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if tool in ("pen", "marker"):
            if len(path) > 1:
                p.drawPolyline(QPolygonF(path))
        elif tool == "rect":
            p.drawRect(QRectF(p0, p1).normalized())
        elif tool == "ellipse":
            p.drawEllipse(QRectF(p0, p1).normalized())
        elif tool == "arrow":
            p.drawLine(p0, p1)
            a = math.atan2(p1.y() - p0.y(), p1.x() - p0.x())
            L = max(18, w * 4)
            pts = [p1, QPointF(p1.x() - L * math.cos(a - 0.45), p1.y() - L * math.sin(a - 0.45)),
                   QPointF(p1.x() - L * math.cos(a + 0.45), p1.y() - L * math.sin(a + 0.45))]
            p.setBrush(col)
            p.drawPolygon(QPolygonF(pts))
        elif tool == "number":
            r = max(18, w * 3)
            p.setBrush(col)
            p.setPen(QPen(QColor("white"), 2))
            p.drawEllipse(p1, r, r)
            f = QFont("Segoe UI", 10, QFont.Bold)
            f.setPixelSize(int(r * 1.1))
            p.setFont(f)
            p.drawText(QRectF(p1.x() - r, p1.y() - r, 2 * r, 2 * r), Qt.AlignCenter, str(self.counter))

    def commit(self, p0, p1, path):
        img = self.image
        if self.tool == "crop":
            r = QRectF(p0, p1).normalized().toRect().intersected(img.rect())
            if r.width() > 8 and r.height() > 8:
                self._push()
                self.image = img.copy(r)
        elif self.tool == "blur":
            r = QRectF(p0, p1).normalized().toRect().intersected(img.rect())
            if r.width() > 4 and r.height() > 4:
                self._push()
                part = img.copy(r)
                k = max(6, min(r.width(), r.height()) // 8)
                small = part.scaled(max(1, r.width() // k), max(1, r.height() // k), Qt.IgnoreAspectRatio,
                                    Qt.FastTransformation)
                pix = small.scaled(r.width(), r.height(), Qt.IgnoreAspectRatio, Qt.FastTransformation)
                p = QPainter(self.image)
                p.drawImage(r.topLeft(), pix)
                p.end()
        else:
            self._push()
            p = QPainter(self.image)
            self.paint_op(p, self.tool, p0, p1, path)
            p.end()
            if self.tool == "number":
                self.counter += 1
        self.info.setText(f"{self.image.width()} × {self.image.height()} px")
        self.view.update()

    def add_text(self, pos):
        d = TextDialog("Texte sur la capture", "", self, self.screen())
        if d.exec() and d.text().strip():
            self._push()
            p = QPainter(self.image)
            f = QFont("Segoe UI", 10, QFont.Bold)
            f.setPixelSize(int(18 + self.width * 3 * max(1.0, self.image.width() / 1600)))
            p.setFont(f)
            p.setPen(QColor(self.color))
            p.drawText(pos, d.text())
            p.end()
            self.view.update()

    def save(self):
        path = os.path.join(captures_dir(), f"Capture_{stamp()}.png")
        self.image.save(path)
        self.info.setText("✅ Enregistré : " + os.path.basename(path))
        return path

    def copy(self):
        QGuiApplication.clipboard().setImage(self.image)
        self.info.setText("✅ Copié dans le presse-papiers")

    def insert(self):
        if self.canvas is not None:
            self.canvas.insert_qimage(self.image, "", max_frac=0.7)
        self.accept()


# ============================================================================
# Enregistrement vidéo de l'écran
# ============================================================================
class ScreenRecorder(QFrame):
    """
    Petit panneau flottant ⏺ 00:00 ⏸ ⏹. Les images sont encodées dans un fil séparé, au rythme
    de l'horloge (images répétées si la machine est lente) : le son reste synchronisé.
    """
    finished = Signal(str)

    def __init__(self, screen, region=None, fps=15, mic=False, system=False):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.screen_ref, self.region, self.fps = screen, region, fps
        self.setStyleSheet("""
            QFrame { background: rgba(15,23,42,235); border-radius: 14px; }
            QLabel { color: #fecaca; font: 700 18px "Consolas","Segoe UI"; padding: 0 8px; }
            QPushButton { background:#1e293b; color:white; border-radius:10px; min-width:48px; min-height:44px;
                          font: 600 18px "Segoe UI Emoji","Segoe UI"; border:0; }
            QPushButton:pressed { background:#0369a1; }""")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self.lbl = QLabel("⏺ 00:00")
        lay.addWidget(self.lbl)
        self.snd = QLabel(("🎤" if mic else "") + ("🔊" if system else ""))
        lay.addWidget(self.snd)
        self.btn_pause = QPushButton("⏸")
        self.btn_pause.setFocusPolicy(Qt.NoFocus)
        self.btn_pause.clicked.connect(self.toggle_pause)
        lay.addWidget(self.btn_pause)
        stop = QPushButton("⏹")
        stop.setFocusPolicy(Qt.NoFocus)
        stop.clicked.connect(self.stop)
        lay.addWidget(stop)
        base = os.path.join(videos_dir(), f"Video_{stamp()}")
        self.path = base + ".mp4"
        self.raw_path = base + "_image.avi" if (mic or system) or audio.ffmpeg_exe() else self.path
        self.wav_path = base + "_son.wav"
        self.audio = audio.AudioRecorder(mic, system) if (mic or system) else None
        self.q = queue.Queue(maxsize=120)
        self.paused = False
        self.elapsed = 0.0
        self.t_last = None
        self.writer_thread = None
        self.timer = QTimer(self, interval=int(1000 / fps), timeout=self._grab)
        self.timer.setTimerType(Qt.PreciseTimer)

    def start(self):
        g = self.screen_ref.geometry()
        self.adjustSize()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 12)
        self.show()
        first = self._frame()
        h, w = first.shape[:2]
        self.size_wh = (w - w % 2, h - h % 2)
        self.writer_thread = threading.Thread(target=self._writer, daemon=True)
        self.writer_thread.start()
        if self.audio:
            self.audio.start()
        self.t_last = time.time()
        self.q.put((0.0, first))
        self.timer.start()

    def _frame(self):
        img = self.screen_ref.grabWindow(0).toImage()
        if self.region is not None:
            img = img.copy(self.region)
        return qimage_to_bgr(img)

    def _grab(self):
        now = time.time()
        if not self.paused:
            self.elapsed += now - self.t_last
            try:
                self.q.put_nowait((self.elapsed, self._frame()))
            except queue.Full:
                pass
        self.t_last = now
        m, s = divmod(int(self.elapsed), 60)
        self.lbl.setText(("⏸ " if self.paused else "⏺ ") + f"{m:02d}:{s:02d}")

    def _writer(self):
        import cv2
        w, h = self.size_wh
        fourcc = cv2.VideoWriter_fourcc(*("MJPG" if self.raw_path.endswith(".avi") else "mp4v"))
        vw = cv2.VideoWriter(self.raw_path, fourcc, self.fps, (w, h))
        written, last = 0, None
        while True:
            item = self.q.get()
            if item is None:
                break
            t, f = item
            if f.shape[1] != w or f.shape[0] != h:
                f = cv2.resize(f, (w, h))
            target = int(round(t * self.fps)) + 1
            while written < target:                    # rattrapage : on répète l'image
                vw.write(f)
                written += 1
            last = f
        end = int(round(self.elapsed * self.fps)) + 1
        while last is not None and written < end:
            vw.write(last)
            written += 1
        vw.release()

    def toggle_pause(self):
        self.paused = not self.paused
        if self.audio:
            self.audio.paused = self.paused
        self.btn_pause.setText("▶" if self.paused else "⏸")

    def stop(self):
        self.timer.stop()
        self.lbl.setText("⏳ Finalisation…")
        self.btn_pause.setEnabled(False)
        QApplication.processEvents()
        self.q.put(None)
        if self.writer_thread:
            self.writer_thread.join(timeout=60)
        result = {"path": self.path, "err": ""}

        def finalize():
            wav = None
            if self.audio:
                wav, err = self.audio.stop(self.wav_path)
                if err:
                    result["err"] = "Son : " + err
            if self.raw_path != self.path:
                try:
                    audio.mux(self.raw_path, wav, self.path)
                    os.remove(self.raw_path)
                except Exception as e:                 # ffmpeg indisponible : on garde l'image seule
                    result["path"] = self.raw_path
                    result["err"] = f"Assemblage image/son impossible : {e}"
            if wav and os.path.exists(wav) and result["path"] == self.path:
                os.remove(wav)
        th = threading.Thread(target=finalize, daemon=True)
        th.start()
        while th.is_alive():
            QApplication.processEvents()
            time.sleep(0.05)
        self.hide()
        self.error = result["err"]
        self.finished.emit(result["path"])
        self.deleteLater()


# ============================================================================
# Éditeur vidéo (lecture + découpe)
# ============================================================================
class VideoEditor(QDialog):
    def __init__(self, path, parent=None, screen=None, note=""):
        super().__init__(parent)
        import cv2
        self.cv2 = cv2
        self.path = path
        self.cap = cv2.VideoCapture(path)
        self.n = max(1, int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 12
        self.start_f, self.end_f = 0, self.n - 1
        self.setWindowTitle("Éditeur vidéo")
        self.setStyleSheet(DIALOG_CSS + """
            QLabel#info { color:#94a3b8; font-size:12pt; }
            QSlider::groove:horizontal { height:14px; background:#1e293b; border-radius:7px; }
            QSlider::handle:horizontal { width:34px; margin:-12px 0; border-radius:17px; background:#38bdf8; }""")
        v = QVBoxLayout(self)
        t = QLabel("🎬 Éditeur vidéo — " + os.path.basename(path))
        t.setObjectName("title")
        v.addWidget(t)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(640, 360)
        self.view.setStyleSheet("background:#020617;border-radius:12px;")
        v.addWidget(self.view, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, self.n - 1)
        self.slider.valueChanged.connect(self.show_frame)
        v.addWidget(self.slider)
        self.info = QLabel()
        self.info.setObjectName("info")
        v.addWidget(self.info)
        row = QHBoxLayout()
        for text, fn, name in [("▶ Lire / ⏸", self.toggle_play, ""), ("🔊 Lire avec le son", self.play_external, ""),
                               ("⏮ Début ici", self.set_start, ""),
                               ("⏭ Fin ici", self.set_end, ""), ("✂️ Exporter la découpe", self.export, "ok"),
                               ("📁 Dossier Vidéos", self.open_folder, ""), ("✖ Fermer", self.reject, "cancel")]:
            b = QPushButton(text)
            if name:
                b.setObjectName(name)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            row.addWidget(b)
        v.addLayout(row)
        self.play_timer = QTimer(self, interval=int(1000 / self.fps), timeout=self._next)
        projected_dialog(self, screen, full=True)
        QTimer.singleShot(50, lambda: self.show_frame(0))
        if note:
            self.info.setText(note)

    def _read(self, i):
        self.cap.set(self.cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = self.cap.read()
        return f if ok else None

    def show_frame(self, i):
        f = self._read(i)
        if f is not None:
            img = bgr_to_qimage(f)
            self.view.setPixmap(QPixmap.fromImage(img).scaled(self.view.size(), Qt.KeepAspectRatio,
                                                               Qt.SmoothTransformation))
        tt = lambda k: f"{int(k / self.fps) // 60:02d}:{int(k / self.fps) % 60:02d}"
        self.info.setText(f"Position {tt(i)} / {tt(self.n - 1)}   —   Découpe : de {tt(self.start_f)} à {tt(self.end_f)}"
                          f"   ({tt(self.end_f - self.start_f)})")

    def toggle_play(self):
        if self.play_timer.isActive():
            self.play_timer.stop()
        else:
            if self.slider.value() >= self.end_f:
                self.slider.setValue(self.start_f)
            self.play_timer.start()

    def _next(self):
        i = self.slider.value() + 1
        if i > self.end_f:
            self.play_timer.stop()
            return
        self.slider.setValue(i)

    def set_start(self):
        self.start_f = min(self.slider.value(), self.end_f)
        self.show_frame(self.slider.value())

    def set_end(self):
        self.end_f = max(self.slider.value(), self.start_f)
        self.show_frame(self.slider.value())

    def play_external(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))

    def export(self):
        cv2 = self.cv2
        out = os.path.splitext(self.path)[0] + f"_decoupe_{stamp()}.mp4"
        if audio.ffmpeg_exe():                         # découpe avec le son
            try:
                audio.trim(self.path, self.start_f / self.fps, (self.end_f + 1) / self.fps, out)
                self.info.setText("✅ Vidéo exportée (avec le son) : " + os.path.basename(out))
                return out
            except Exception as e:
                print("Découpe ffmpeg impossible :", e)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_f)
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
        for _ in range(self.start_f, self.end_f + 1):
            ok, f = self.cap.read()
            if not ok:
                break
            vw.write(f)
        vw.release()
        self.info.setText("✅ Vidéo exportée : " + os.path.basename(out))
        return out

    def open_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(videos_dir()))

    def done(self, r):
        self.play_timer.stop()
        self.cap.release()
        super().done(r)


# ============================================================================
# Menu de capture
# ============================================================================
AUDIO_PREFS = {"mic": True, "sys": True}


class CaptureMenu(QDialog):
    """Choix : capture écran entier / zone, vidéo écran entier / zone, rouvrir une vidéo."""

    def __init__(self, parent=None, screen=None):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("Capture")
        self.setStyleSheet(DIALOG_CSS + "QPushButton{min-height:70px;font-size:15pt;text-align:left;padding-left:18px;}")
        v = QVBoxLayout(self)
        t = QLabel("📸 Capture d'écran et vidéo")
        t.setObjectName("title")
        v.addWidget(t)
        for key, text in [("img_full", "🖥️  Capturer tout l'écran"), ("img_zone", "✂️  Capturer une zone"),
                          ("vid_full", "🎬  Enregistrer l'écran en vidéo"), ("vid_zone", "🎯  Enregistrer une zone en vidéo"),
                          ("vid_edit", "🎞️  Ouvrir et découper une vidéo enregistrée")]:
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            v.addWidget(b)
            if key == "vid_zone":
                mic_ok, sys_ok, msg = audio.audio_available()
                row = QHBoxLayout()
                self.chk_mic = QCheckBox("🎤 Enregistrer ma voix (micro)")
                self.chk_sys = QCheckBox("🔊 Enregistrer les sons de l'ordinateur")
                for c, ok, key2 in ((self.chk_mic, mic_ok, "mic"), (self.chk_sys, sys_ok, "sys")):
                    c.setStyleSheet("QCheckBox{font-size:13pt;padding:6px;} QCheckBox::indicator{width:26px;height:26px;}")
                    c.setEnabled(ok)
                    c.setChecked(ok and AUDIO_PREFS.get(key2, True))
                    if not ok:
                        c.setToolTip(msg or "Périphérique introuvable")
                    row.addWidget(c)
                v.addLayout(row)
        c = QPushButton("✖  Annuler")
        c.setObjectName("cancel")
        c.clicked.connect(self.reject)
        v.addWidget(c)
        projected_dialog(self, screen, size=(760, 640))

    def _pick(self, k):
        self.choice = k
        AUDIO_PREFS["mic"] = self.chk_mic.isChecked()
        AUDIO_PREFS["sys"] = self.chk_sys.isChecked()
        self.accept()


class CaptureController:
    """Enchaîne menu → capture → éditeur. hide = éléments de TBI Pro à masquer pendant la capture."""

    def __init__(self, screen, canvas=None, parent=None, hide=()):
        self.screen, self.canvas, self.parent, self.hide = screen, canvas, parent, hide
        self.recorder = None

    def run(self):
        m = CaptureMenu(self.parent, self.screen)
        if not m.exec():
            return
        k = m.choice
        if k.startswith("img"):
            img = grab_screen(self.screen, self.hide)
            if k == "img_zone":
                sel = RegionSelector(img, self.screen)
                if not sel.exec():
                    return
                img = img.copy(sel.rect_result)
            ImageEditor(img, self.canvas, self.parent, self.screen).exec()
        elif k.startswith("vid_") and k != "vid_edit":
            region = None
            if k == "vid_zone":
                img = grab_screen(self.screen, self.hide)
                sel = RegionSelector(img, self.screen, "Tracez la zone à enregistrer")
                if not sel.exec():
                    return
                dpr = img.width() / self.screen.geometry().width()
                r = sel.rect_result
                region = QRect(r.x(), r.y(), r.width(), r.height()) if dpr else r
            self.recorder = ScreenRecorder(self.screen, region, mic=m.chk_mic.isChecked(), system=m.chk_sys.isChecked())
            self.recorder.finished.connect(self._recorded)
            self.recorder.start()
        elif k == "vid_edit":
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(self.parent, "Ouvrir une vidéo", videos_dir(), "Vidéos (*.mp4 *.avi *.mkv)",
                                                  options=QFileDialog.Option.DontUseNativeDialog)
            if path:
                VideoEditor(path, self.parent, self.screen).exec()

    def _recorded(self, path):
        note = getattr(self.recorder, "error", "")
        self.recorder = None
        if os.path.exists(path) and os.path.getsize(path) > 0:
            VideoEditor(path, self.parent, self.screen, note).exec()
