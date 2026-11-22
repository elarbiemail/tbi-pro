# -*- coding: utf-8 -*-
"""Fenêtres affichées sur l'écran projeté : tableau blanc, annotation, bouton flottant, calibrage."""
import datetime
import os
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton, QVBoxLayout, QWidget

from ..config import documents_dir
from .. import vision
from .activities import MindmapDialog, PagesDialog, PickerDialog, TimerPanel, WordCloudDialog
from .canvas import InkCanvas
from .keyboard import TextDialog
from .library import LibraryDialog
from .toolbar import Toolbar


class ToolsMixin:
    """Actions communes au tableau et à l'annotation : bibliothèque, minuteur, nuage, carte, texte."""

    def _setup_tools(self):
        self.timer_panel = TimerPanel(self)
        self.canvas.text_requested.connect(
            lambda pos, key: QTimer.singleShot(0, lambda: self._ask_text(pos, key)))
        self.canvas.edit_text_requested.connect(
            lambda it: QTimer.singleShot(0, lambda: self._edit_text(it)))

    def _scr(self):
        return self.screen_ref or self.screen()

    def _ask_text(self, pos, key):
        d = TextDialog("Écrire un texte", "", self, self._scr())
        if d.exec():
            self.canvas.add_text(pos, d.text(), key)
        self.raise_()

    def _edit_text(self, it):
        d = TextDialog("Modifier le texte", it.get("t", ""), self, self._scr())
        if d.exec() and d.text().strip():
            self.canvas.replace_text(it, d.text())
        self.raise_()

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        st = self.toolbar.state()
        dlg = QColorDialog(QColor(st.color), self)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        if dlg.exec():
            self.toolbar.set_color(dlg.selectedColor().name())

    def common_action(self, act):
        if act == "color":
            self._pick_color()
        elif act == "picker":
            PickerDialog(self, self._scr()).exec()
        elif act == "pages":
            PagesDialog(self.canvas, self, self._scr()).exec()
        elif act == "library":
            LibraryDialog(self.canvas, self, self._scr()).exec()
        elif act == "timer":
            self.timer_panel.toggle_visible()
        elif act == "cloud":
            WordCloudDialog(self.canvas, self, self._scr()).exec()
        elif act == "mindmap":
            MindmapDialog(self.canvas, self, self._scr()).exec()
        else:
            return False
        self.toolbar.refresh()
        self.raise_()
        return True


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%Hh%M-%S")


class ProjectedWindow(QWidget):
    """Fenêtre plein écran sans bordure, posée sur l'écran projeté."""

    def __init__(self, flags=Qt.Window):
        super().__init__(None, flags | Qt.FramelessWindowHint)
        self.screen_ref = None

    def show_on(self, screen):
        self.screen_ref = screen
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()


# ----------------------------------------------------------------------------
class BoardWindow(ToolsMixin, ProjectedWindow):
    mode_requested = Signal(str)
    panel_requested = Signal()

    def __init__(self):
        super().__init__(Qt.Window | Qt.WindowStaysOnTopHint)
        self.setWindowTitle("TBI Pro — Tableau blanc")
        self.canvas = InkCanvas(False, self)
        self.toolbar = Toolbar(self.canvas, "board", self)
        self.toolbar.mode_requested.connect(self.mode_requested)
        self.toolbar.panel_requested.connect(self.panel_requested)
        self.toolbar.action.connect(self.on_action)
        self.autosave_path = None
        self._setup_tools()
        self._autosave_timer = QTimer(self, interval=120000, timeout=self._autosave)   # toutes les 2 minutes
        self._autosave_timer.start()
        self._autosave_sig = None

    def _autosave(self):
        """Sauvegarde automatique de sécurité dans Documents/TBI Pro/Sauvegardes automatiques."""
        c = self.canvas
        if not any(pg["items"] or pg.get("bgimg") for pg in c.pages):
            return
        sig = (len(c.pages), tuple(len(pg["items"]) for pg in c.pages), tuple(id(pg["items"]) for pg in c.pages))
        if sig == self._autosave_sig:
            return
        self._autosave_sig = sig
        d = os.path.join(documents_dir(), "Sauvegardes automatiques")
        os.makedirs(d, exist_ok=True)
        try:
            c.save(os.path.join(d, "derniere_session.tbi"))
        except Exception as e:
            print("Sauvegarde automatique impossible :", e)

    def resizeEvent(self, e):
        self.canvas.setGeometry(self.rect())
        self.toolbar.place()
        super().resizeEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.mode_requested.emit("souris")
        elif e.key() in (Qt.Key_Right, Qt.Key_PageDown):
            self.toolbar._next_page()
            self.toolbar.refresh()
        elif e.key() in (Qt.Key_Left, Qt.Key_PageUp):
            self.canvas.go_page(self.canvas.index - 1)
        elif e.key() == Qt.Key_Z and e.modifiers() & Qt.ControlModifier:
            self.canvas.undo()
        elif e.key() == Qt.Key_Y and e.modifiers() & Qt.ControlModifier:
            self.canvas.redo()

    def _dialog(self):
        return QFileDialog.Option.DontUseNativeDialog  # boîte Qt : utilisable au stylet, sur l'écran projeté

    def on_action(self, act):
        c = self.canvas
        if self.common_action(act):
            return
        if act == "save":
            if not self.autosave_path:
                self.autosave_path = os.path.join(documents_dir(), f"Tableau_{stamp()}.tbi")
            c.save(self.autosave_path)
            c.toast("Enregistré : " + os.path.basename(self.autosave_path))
        elif act == "pdf":
            path = os.path.join(documents_dir(), f"Tableau_{stamp()}.pdf")
            c.export_pdf(path)
            c.toast("PDF créé : " + os.path.basename(path))
        elif act == "open":
            path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un tableau", documents_dir(),
                                                  "Tableaux TBI Pro (*.tbi)", options=self._dialog())
            if path:
                c.load(path)
                self.autosave_path = path
                c.toast("Ouvert : " + os.path.basename(path))
        elif act == "pdfimport":
            path, _ = QFileDialog.getOpenFileName(self, "Importer un PDF", os.path.expanduser("~"),
                                                  "Documents PDF (*.pdf)", options=self._dialog())
            if path:
                try:
                    n = c.import_pdf(path)
                    c.toast(f"{n} page(s) importée(s) : écrivez dessus !")
                except Exception as e:
                    c.toast(f"Import impossible : {e}")
        elif act == "image":
            path, _ = QFileDialog.getOpenFileName(self, "Insérer une image", os.path.expanduser("~"),
                                                  "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)", options=self._dialog())
            if path:
                c.insert_image(path)
        self.toolbar.refresh()
        self.raise_()


# ----------------------------------------------------------------------------
class OverlayWindow(ToolsMixin, ProjectedWindow):
    """Calque transparent pour écrire par-dessus n'importe quel logiciel."""
    mode_requested = Signal(str)
    panel_requested = Signal()

    def __init__(self):
        super().__init__(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("TBI Pro — Annotation")
        self.canvas = InkCanvas(True, self)
        self.toolbar = Toolbar(self.canvas, "overlay", self)
        self.toolbar.mode_requested.connect(self.mode_requested)
        self.toolbar.panel_requested.connect(self.panel_requested)
        self.toolbar.action.connect(self.on_action)
        self._setup_tools()

    def resizeEvent(self, e):
        self.canvas.setGeometry(self.rect())
        self.toolbar.place()
        super().resizeEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.mode_requested.emit("souris")

    def _grab_screen(self, hide_all):
        scr = self.screen_ref or self.screen()
        if hide_all:
            self.hide()
        else:
            self.toolbar.hide()
        QApplication.processEvents()
        time.sleep(0.15)
        QApplication.processEvents()
        pm = scr.grabWindow(0)
        if hide_all:
            self.show()
        else:
            self.toolbar.show()
        self.raise_()
        return pm

    def on_action(self, act):
        c = self.canvas
        if self.common_action(act):
            return
        if act == "freeze":
            if c.frozen is None:
                c.frozen = self._grab_screen(hide_all=True)
                c.toast("Écran figé : écrivez dessus")
            else:
                c.frozen = None
                c.toast("Écran libéré")
            c.invalidate()
        elif act == "capture":
            pm = self._grab_screen(hide_all=False)
            d = os.path.join(documents_dir(), "Captures")
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, f"Capture_{stamp()}.png")
            pm.save(path)
            c.toast("Capture enregistrée")


# ----------------------------------------------------------------------------
class Floater(QWidget):
    """Petit bouton toujours visible en mode souris, pour passer en annotation / tableau."""
    mode_requested = Signal(str)
    panel_requested = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        style = ("QPushButton{background:rgba(15,23,42,225);color:white;border-radius:30px;"
                 "font:600 24px 'Segoe UI Emoji','Segoe UI';border:2px solid #38bdf8;}"
                 "QPushButton:pressed{background:#0c4a6e;}")
        self.extra = []
        for icon, tip, fn in [("🖊️", "Annoter l'écran", lambda: self.mode_requested.emit("annoter")),
                              ("📋", "Tableau blanc", lambda: self.mode_requested.emit("tableau")),
                              ("⚙️", "Panneau de contrôle", self.panel_requested.emit)]:
            b = QPushButton(icon)
            b.setToolTip(tip)
            b.setFixedSize(60, 60)
            b.setStyleSheet(style)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, f=fn: f())
            b.clicked.connect(self.fold)
            b.hide()
            self.extra.append(b)
            lay.addWidget(b)
        self.main = QPushButton("✍️")
        self.main.setToolTip("TBI Pro")
        self.main.setFixedSize(60, 60)
        self.main.setStyleSheet(style)
        self.main.setFocusPolicy(Qt.NoFocus)
        self.main.clicked.connect(self.toggle)
        lay.addWidget(self.main)
        self.screen_ref = None

    def toggle(self):
        vis = not self.extra[0].isVisible()
        for b in self.extra:
            b.setVisible(vis)
        self.adjustSize()
        self.place()

    def fold(self):
        for b in self.extra:
            b.hide()
        self.adjustSize()

    def show_on(self, screen):
        self.screen_ref = screen
        self.fold()
        self.place()
        self.show()
        self.raise_()

    def place(self):
        if not self.screen_ref:
            return
        g = self.screen_ref.availableGeometry()
        self.adjustSize()
        self.move(g.right() - self.width() - 20, g.bottom() - self.height() - 20)


# ----------------------------------------------------------------------------
class CalibWindow(ProjectedWindow):
    """
    Calibrage :
      - « stylet » : 4 cibles ; on appuie le stylet au centre de chacune ;
      - « auto »   : projection noire puis blanche, la zone est trouvée automatiquement.
    Émet finished(H, roi) ou failed(message).
    """
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, source, mode, finger=False):
        super().__init__(Qt.Window | Qt.WindowStaysOnTopHint)
        self.source, self.mode, self.finger = source, mode, finger
        self.targets, self.i, self.samples, self.last_seen = [], 0, [], 0
        self.cam_pts = []
        self.fill = QColor("black")
        self.message = ""
        self.auto_step, self.auto_t, self.shots = 0, 0, []
        self.timer = QTimer(self, interval=30, timeout=self._tick)

    def start(self, screen):
        self.show_on(screen)
        g = screen.geometry()
        self.targets = vision.target_points(g.width(), g.height())
        if self.mode == "auto":
            self.auto_step, self.auto_t = 0, time.time()
            self.message = "Calibrage automatique… ne bougez pas la caméra"
        elif self.finger:
            self.message = "Placez l'index au centre de la cible jaune et pincez (pouce + index)"
        else:
            self.message = "Appuyez le stylet au centre de la cible jaune"
        self.timer.start()
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.timer.stop()
            self.close()
            self.failed.emit("Calibrage annulé")

    # appelé par le contrôleur avec les points bruts de la caméra (normalisés)
    def feed(self, blobs):
        if self.mode != "pen" or self.i >= 4:
            return
        blobs = [b for b in blobs if len(b) < 5 or b[4]]   # doigt : seulement quand on pince
        now = time.time()
        if blobs:
            self.samples.append(blobs[0][:2])
            self.last_seen = now
        elif len(self.samples) >= 10 and now - self.last_seen > 0.25:
            pts = np.array(self.samples[3:], float)
            self.cam_pts.append(tuple(np.median(pts, axis=0)))
            self.samples = []
            self.i += 1
            if self.i == 4:
                H = vision.homography(self.cam_pts, self.targets)
                self._done(H)
        elif self.samples and len(self.samples) < 10 and now - self.last_seen > 0.4:
            self.samples = []
        self.update()

    def _tick(self):
        if self.mode != "auto":
            return
        dt = time.time() - self.auto_t
        if self.auto_step in (0, 2):                    # projeter noir puis blanc, attendre
            self.fill = QColor("black" if self.auto_step == 0 else "white")
            self.update()
            if dt > 1.6:
                self.source.request_snapshot()
                self.auto_step += 1
                self.auto_t = time.time()
        elif self.auto_step in (1, 3):                  # attendre l'image
            snap = self.source.get_snapshot()
            if snap is not None:
                self.shots.append(snap)
                self.auto_step += 1
                self.auto_t = time.time()
                if self.auto_step == 4:
                    quad = vision.find_projection_quad(self.shots[0], self.shots[1])
                    if quad is None:
                        self._fail("Zone projetée introuvable : vérifiez que la caméra voit toute la projection.")
                        return
                    g = self.geometry()
                    H = vision.homography(quad, [(0, 0), (g.width(), 0), (g.width(), g.height()), (0, g.height())])
                    self._done(H)
            elif dt > 4:
                self._fail("La caméra ne répond pas.")

    def _done(self, H):
        self.timer.stop()
        g = self.geometry()
        roi = vision.camera_roi(H, g.width(), g.height())
        self.close()
        self.finished.emit(H, roi)

    def _fail(self, msg):
        self.timer.stop()
        self.close()
        self.failed.emit(msg)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.fill)
        if self.mode == "auto":
            return
        p.setRenderHint(QPainter.Antialiasing)
        for j, (x, y) in enumerate(self.targets):
            # couleurs sombres : les cibles ne doivent pas être prises pour la LED
            col = QColor(0, 150, 150) if j == self.i else (QColor(0, 110, 0) if j < self.i else QColor(60, 60, 60))
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(x, y), 30, 30)
            p.drawLine(QPointF(x - 48, y), QPointF(x + 48, y))
            p.drawLine(QPointF(x, y - 48), QPointF(x, y + 48))
            p.setBrush(col)
            p.drawEllipse(QPointF(x, y), 4, 4)
        f = QFont("Segoe UI", 18, QFont.Bold)
        p.setFont(f)
        p.setPen(QColor(150, 150, 150))
        r = QRectF(0, self.height() / 2 - 60, self.width(), 40)
        p.drawText(r, Qt.AlignCenter, f"Calibrage {min(self.i + 1, 4)}/4 — {self.message}")
        f.setPointSize(13)
        p.setFont(f)
        txt = "Échap = annuler"
        if self.samples:
            txt = "Maintenez…" if len(self.samples) < 10 else ("Relâchez" if self.finger else "Relâchez le stylet")
            p.setPen(QColor(0, 150, 0))
        p.drawText(QRectF(0, self.height() / 2, self.width(), 40), Qt.AlignCenter, txt)
