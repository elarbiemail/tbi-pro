# -*- coding: utf-8 -*-
"""
TBI Pro — contrôleur principal.

Flux : source caméra → points (normalisés) → calibrage (homographie) → suivi
multi-stylets → événements down/move/up → selon le mode :
  • Souris   : le 1er stylet pilote la souris du système (tous les logiciels) ;
  • Annoter  : calque transparent par-dessus l'écran, multi-stylets ;
  • Tableau  : tableau blanc plein écran, multi-stylets.
"""
import os
import sys
import time
import traceback

import numpy as np
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QAbstractButton, QApplication, QMessageBox

from .config import APP_NAME, Config, app_dir, resource_path
from .mouse import SystemMouse
from .sources import make_source
from . import vision
from .ui.canvas import InkCanvas
from .ui.control import ControlPanel
from .ui.windows import BoardWindow, CalibWindow, Floater, OverlayWindow


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cfg = Config()
        self.screens = QGuiApplication.screens()
        self.screen = self._pick_screen()
        self.mode = "souris"
        self.source = None
        self.tracker = vision.PenTracker(self.cfg)
        self.mouse = SystemMouse()
        self.H = None
        self.calib = None
        self.last_seq = -1
        self.mouse_pid = None
        self.dwell = None          # mode laser : (x, y, t0, déjà cliqué)
        self.ptr_target = {}       # id pointeur → ("canvas", canvas) | ("btn", bouton, clé) | ("os",)
        self.finger_dwell = {}     # doigt « maintien » : id → [x, y, t0, cliqué]

        self.panel = ControlPanel(self.cfg, self.screens)
        self.board = BoardWindow()
        self.overlay = OverlayWindow()
        self.floater = Floater()
        for w in (self.board, self.overlay, self.floater):
            w.mode_requested.connect(self.set_mode)
            w.panel_requested.connect(self.show_panel)
        p = self.panel
        p.mode_requested.connect(self.set_mode)
        p.calibrate_requested.connect(self.calibrate)
        p.source_changed.connect(self.restart_source)
        p.params_changed.connect(self.apply_params)
        p.screen_changed.connect(self.change_screen)
        p.relearn_requested.connect(self.relearn_ir)
        p.select_screen(self.screens.index(self.screen))
        p.closeEvent = self._on_close

        self.save_timer = QTimer(self, singleShot=True, interval=800, timeout=self.cfg.save)
        self.load_calibration()
        self.restart_source()

        self.timer = QTimer(self, interval=4, timeout=self.tick)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.start()
        self.ui_timer = QTimer(self, interval=150, timeout=self.refresh_ui)
        self.ui_timer.start()

        p.show()
        self.set_mode("souris")

    # ------------------------------------------------------------------ écrans
    def _pick_screen(self):
        for s in self.screens:
            if s.name() == self.cfg.get("screen"):
                return s
        prim = QGuiApplication.primaryScreen()
        others = [s for s in self.screens if s is not prim]
        return others[0] if others else prim

    def change_screen(self, idx):
        self.screens = QGuiApplication.screens()
        if 0 <= idx < len(self.screens):
            self.screen = self.screens[idx]
            self.cfg["screen"] = self.screen.name()
            self.load_calibration()
            self.cfg.save()
            self.set_mode(self.mode)

    # ------------------------------------------------------------------ calibrage
    def load_calibration(self):
        H = self.cfg.get("homography")
        if H is None:
            self.H = None
            return
        H = np.array(H, float)
        cs = self.cfg.get("calib_size")
        g = self.screen.geometry()
        if cs and (cs[0] != g.width() or cs[1] != g.height()):
            S = np.diag([g.width() / cs[0], g.height() / cs[1], 1.0])
            H = S @ H
        self.H = H

    def calibrate(self, mode):
        if self.calib:
            return
        self.set_mode("souris")
        self.floater.hide()
        self.source.set_params(roi=None)
        self.calib = CalibWindow(self.source, mode, finger=self.cfg.get("pointer") == "doigt")
        self.calib.finished.connect(self._calib_ok)
        self.calib.failed.connect(self._calib_fail)
        self.calib.start(self.screen)

    def _calib_ok(self, H, roi):
        g = self.screen.geometry()
        self.cfg["homography"] = np.asarray(H).tolist()
        self.cfg["calib_size"] = [g.width(), g.height()]
        self.cfg["roi"] = [list(map(float, p)) for p in roi]
        self.H = np.asarray(H, float)
        self.calib = None
        self.apply_params()
        self.cfg.save()
        self.set_mode("souris")
        self.panel.statusBar().showMessage("Calibrage réussi", 5000)

    def _calib_fail(self, msg):
        self.calib = None
        self.apply_params()
        self.set_mode("souris")
        self.panel.statusBar().showMessage(msg, 8000)

    # ------------------------------------------------------------------ source
    def restart_source(self):
        if self.source:
            self.source.stop()
        self.source = make_source(self.cfg)
        self.source.start()
        self.apply_params()
        self.last_seq = -1
        self.panel.set_url(getattr(self.source, "url", ""))
        self.cfg.save()

    def apply_params(self):
        c = self.cfg
        self.source.set_params(threshold=c["threshold"], min_area=c["min_area"], max_area=c["max_area"],
                               roi=None if self.calib else c.get("roi"), mode=c.get("pointer", "led"),
                               crop=bool(c.get("hand_crop", True)))
        self.save_timer.start()

    def relearn_ir(self):
        if hasattr(self.source, "relearn_background"):
            self.source.relearn_background()
            self.panel.statusBar().showMessage("Fond infrarouge réinitialisé : il est réappris quand aucun stylet n'est visible", 6000)

    # ------------------------------------------------------------------ boucle principale
    def tick(self):
        try:
            seq, blobs, t = self.source.latest()
            if seq == self.last_seq:
                if self.tracker.tracks and time.time() - t > 0.4:   # caméra muette : on relâche tout
                    self.dispatch(self.tracker.release_all())
                return
            self.last_seq = seq
            if self.calib:
                self.calib.feed(blobs)
                return
            if self.H is None:
                return
            g = self.screen.geometry()
            W, Hh = g.width(), g.height()
            dwell = self.cfg.get("pointer") == "doigt" and self.cfg.get("finger_click") == "maintien"
            pts = []
            for b in blobs:
                x, y = vision.apply_h(self.H, b[0], b[1])
                if -30 <= x <= W + 30 and -30 <= y <= Hh + 30:
                    pressed = False if dwell else (bool(b[4]) if len(b) > 4 else True)
                    pts.append((min(max(x, 0), W - 1), min(max(y, 0), Hh - 1), b[3], pressed))
            events = self.tracker.update(pts)
            if dwell:
                events = self._dwell_clicks(events)
            self.dispatch(events)
        except Exception:
            traceback.print_exc()

    def _dwell_clicks(self, events):
        """Doigt immobile pendant ~1 s → clic (appui + relâchement) à cet endroit."""
        out = []
        delay = float(self.cfg.get("dwell_seconds", 1.0))
        now = time.time()
        for ev in events:
            kind, pid, key, x, y = ev
            out.append(ev)
            if kind == "hover":
                d = self.finger_dwell.get(pid)
                if d is None or np.hypot(x - d[0], y - d[1]) > 22:
                    self.finger_dwell[pid] = [x, y, now, False]
                elif not d[3] and now - d[2] >= delay:
                    d[3] = True
                    out += [("down", pid, key, d[0], d[1]), ("up", pid, key, d[0], d[1])]
            elif kind == "leave":
                self.finger_dwell.pop(pid, None)
        return out

    # ------------------------------------------------------------------ distribution des événements
    def dispatch(self, events):
        for ev in events:
            kind, pid, key, x, y = ev
            if self.mode == "souris":
                self._to_mouse(kind, pid, x, y)
            else:
                self._to_window(kind, pid, key, x, y)

    def _to_mouse(self, kind, pid, x, y):
        if self.mouse_pid is None and kind in ("down", "hover"):
            self.mouse_pid = pid
        if pid != self.mouse_pid:
            return
        if kind == "hover":                      # doigt sans appui : le curseur suit l'index
            self.mouse.move(self.screen, x, y)
            return
        if kind == "leave":
            self.mouse_pid, self.dwell = None, None
            return
        laser = bool(self.cfg.get("laser"))
        if kind in ("down", "move"):
            self.mouse.move(self.screen, x, y)
            if not laser and kind == "down":
                self.mouse.press()
            if laser:
                now = time.time()
                if self.dwell is None or np.hypot(x - self.dwell[0], y - self.dwell[1]) > 18:
                    self.dwell = [x, y, now, False]
                elif not self.dwell[3] and now - self.dwell[2] >= float(self.cfg.get("dwell_seconds", 1.0)):
                    self.mouse.click()
                    self.dwell[3] = True
        else:  # up
            if not laser:
                self.mouse.release()
            if self.cfg.get("pointer") != "doigt":   # le doigt reste visible : on garde le même pointeur
                self.mouse_pid = None
            self.dwell = None

    def _active_window(self):
        return self.board if self.mode == "tableau" else self.overlay

    def _to_window(self, kind, pid, key, x, y):
        g = self.screen.geometry()
        gpos = QPoint(int(g.x() + x), int(g.y() + y))
        cv = self._active_window().canvas
        if kind == "hover":
            cv.set_hover(pid, QPointF(cv.mapFromGlobal(QPointF(gpos))))
            return
        if kind == "leave":
            cv.set_hover(pid, None)
            return
        if kind == "down":
            cv.set_hover(pid, None)
            if QApplication.activeModalWidget() is not None:          # boîte de dialogue ouverte
                self.ptr_target[pid] = ("os",)
                self.mouse.move(self.screen, x, y)
                self.mouse.press()
                return
            win = self._active_window()
            w = win.childAt(win.mapFromGlobal(gpos))
            while w is not None and w is not win and not isinstance(w, (QAbstractButton, InkCanvas)):
                w = w.parentWidget()
            if isinstance(w, QAbstractButton):
                w.setDown(True)
                self.ptr_target[pid] = ("btn", w, key)
            elif isinstance(w, InkCanvas):
                w.pen_down(pid, key, QPointF(w.mapFromGlobal(QPointF(gpos))))
                self.ptr_target[pid] = ("canvas", w)
            return
        tgt = self.ptr_target.get(pid)
        if not tgt:
            return
        if kind == "move":
            if tgt[0] == "canvas":
                tgt[1].pen_move(pid, QPointF(tgt[1].mapFromGlobal(QPointF(x + g.x(), y + g.y()))))
            elif tgt[0] == "os":
                self.mouse.move(self.screen, x, y)
            return
        # up
        self.ptr_target.pop(pid, None)
        if tgt[0] == "canvas":
            tgt[1].pen_up(pid)
        elif tgt[0] == "os":
            self.mouse.release()
        elif tgt[0] == "btn":
            btn, k = tgt[1], tgt[2]
            btn.setDown(False)
            win = self._active_window()
            under = win.childAt(win.mapFromGlobal(gpos))
            if under is btn or (under is not None and btn.isAncestorOf(under)):
                tb = getattr(win, "toolbar", None)
                if tb is not None:
                    tb.active_key = k          # la barre règle le stylet qui l'a touchée
                    tb.refresh()
                btn.click()

    # ------------------------------------------------------------------ modes
    def set_mode(self, mode):
        self.dispatch(self.tracker.release_all())
        self.mouse.release()
        self.ptr_target.clear()
        self.mouse_pid = None
        for w in (self.board, self.overlay):
            w.canvas.hovers.clear()
        self.mode = mode
        if mode == "souris":
            self.board.hide()
            self.overlay.hide()
            if self.H is not None and not self.calib:
                self.floater.show_on(self.screen)
        elif mode == "annoter":
            self.board.hide()
            self.floater.hide()
            self.overlay.show_on(self.screen)
        elif mode == "tableau":
            self.overlay.hide()
            self.floater.hide()
            self.board.show_on(self.screen)
        self.panel.set_mode(mode)

    def show_panel(self):
        if self.panel.screen() is self.screen and self.mode != "souris":
            self.set_mode("souris")      # même écran : on libère la vue pour le panneau
        self.panel.showNormal()
        self.panel.raise_()
        self.panel.activateWindow()

    # ------------------------------------------------------------------ interface
    def refresh_ui(self):
        p = self.panel
        st = self.source.status()
        p.status_lbl.setText(st)
        p.calib_lbl.setText("✅ Calibré" if self.H is not None else "⚠️ Non calibré : lancez un calibrage")
        p.chip_cam.setText(("🟢 Caméra " + f"{self.source.fps:.0f} img/s") if self.source.connected() else "🔴 Caméra en attente")
        p.chip_cal.setText("🎯 Calibré" if self.H is not None else "⚠️ À calibrer")
        if p.isVisible() and not p.isMinimized():
            _, blobs, _ = self.source.latest()
            p.show_preview(self.source.preview(), blobs, None if self.calib else self.cfg.get("roi"))

    def _on_close(self, e):
        self.dispatch(self.tracker.release_all())
        self.mouse.release()
        self.source.stop()
        self.cfg.save()
        e.accept()
        QApplication.quit()


def main():
    log = os.path.join(app_dir(), "tbipro.log")
    if getattr(sys, "frozen", False):                 # exécutable sans console : journal dans un fichier
        sys.stdout = sys.stderr = open(log, "a", encoding="utf-8", buffering=1)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon = resource_path("icon.ico")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))
    app.setQuitOnLastWindowClosed(False)
    try:
        ctrl = Controller(app)
    except Exception as e:
        traceback.print_exc()
        QMessageBox.critical(None, APP_NAME, f"Erreur au démarrage :\n{e}\n\nJournal : {log}")
        return 1
    app._ctrl = ctrl
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
