# -*- coding: utf-8 -*-
"""Panneau de contrôle (sur l'écran de l'ordinateur de l'enseignant)."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMainWindow, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from ..config import APP_NAME, VERSION
from ..sources import SOURCES

PEN_COLORS = {"blanc": "#ffffff", "rouge": "#f87171", "vert": "#4ade80", "bleu": "#60a5fa", "ir": "#f0abfc",
              "doigt": "#facc15"}

CSS = """
QMainWindow { background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0b1220, stop:1 #111c33); }
QWidget { color:#e2e8f0; font: 10pt "Segoe UI"; }
QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; border:0; }
QFrame#header { background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0369a1, stop:1 #7c3aed); border-radius:14px; }
QLabel#appname { font: 700 18pt "Segoe UI"; color:white; }
QLabel#tagline { color:#e0f2fe; font-size:10pt; }
QLabel#chip { background:rgba(255,255,255,0.18); color:white; border-radius:12px; padding:6px 12px; font-weight:600; }
QGroupBox { background:rgba(30,41,59,0.75); border:1px solid #24324a; border-radius:14px; margin-top:18px;
            padding:14px 12px 12px 12px; font-weight:600; }
QGroupBox::title { subcontrol-origin: margin; left:14px; padding:2px 8px; color:#7dd3fc; background:#0f172a;
                   border-radius:8px; }
QPushButton { background:#1e293b; border:1px solid #334155; border-radius:10px; padding:9px 14px; }
QPushButton:hover { background:#273449; border-color:#38bdf8; }
QPushButton:pressed { background:#0c4a6e; }
QPushButton[mode="true"] { font-size:12pt; font-weight:700; padding:14px; }
QPushButton[sel="true"] { background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #0284c7, stop:1 #6d28d9);
                          border-color:#7dd3fc; color:white; }
QComboBox, QLineEdit, QSpinBox { background:#0f172a; border:1px solid #334155; border-radius:8px; padding:7px; }
QComboBox:hover, QLineEdit:focus { border-color:#38bdf8; }
QSlider::groove:horizontal { height:6px; background:#1e293b; border-radius:3px; }
QSlider::sub-page:horizontal { background:#0ea5e9; border-radius:3px; }
QSlider::handle:horizontal { width:18px; margin:-7px 0; border-radius:9px; background:#f8fafc; border:2px solid #0ea5e9; }
QCheckBox::indicator { width:18px; height:18px; }
QScrollBar:vertical { width:14px; background:transparent; }
QScrollBar::handle:vertical { background:#334155; border-radius:7px; min-height:40px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QLabel#status { font-weight:600; color:#a7f3d0; }
QLabel#hint { color:#94a3b8; font-size:9pt; }
QStatusBar { color:#a7f3d0; }
"""


def qr_pixmap(text, size=200):
    """QR code dessiné avec QPainter (pas besoin de Pillow)."""
    import qrcode
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    m = qr.get_matrix()
    n = len(m)
    pm = QPixmap(size, size)
    pm.fill(Qt.white)
    p = QPainter(pm)
    cell = size / n
    p.setPen(Qt.NoPen)
    p.setBrush(Qt.black)
    for y, row in enumerate(m):
        for x, v in enumerate(row):
            if v:
                p.drawRect(QRectF(x * cell, y * cell, cell + 0.5, cell + 0.5))
    p.end()
    return pm


def preview_qimage(prev):
    kind, data = prev
    if kind == "jpeg":
        img = QImage()
        img.loadFromData(data)
        return img
    arr = np.ascontiguousarray(data[:, :, ::-1])
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class ControlPanel(QMainWindow):
    source_changed = Signal()
    mode_requested = Signal(str)
    calibrate_requested = Signal(str)
    screen_changed = Signal(int)
    params_changed = Signal()
    relearn_requested = Signal()

    def __init__(self, cfg, screens):
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(f"{APP_NAME} {VERSION} — Panneau de contrôle")
        self.setStyleSheet(CSS)
        self.resize(1120, 800)
        self.setMinimumSize(760, 480)
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 12, 12, 6)
        # ------------------------------------------------ en-tête
        head = QFrame()
        head.setObjectName("header")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 10, 18, 10)
        logo = QLabel()
        from ..config import resource_path
        import os
        ico = resource_path("icon.ico")
        if os.path.exists(ico):
            logo.setPixmap(QPixmap(ico).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        hl.addWidget(logo)
        tv = QVBoxLayout()
        name = QLabel(f"{APP_NAME}")
        name.setObjectName("appname")
        tag = QLabel("Tableau blanc interactif — caméra, stylet ou doigt")
        tag.setObjectName("tagline")
        tv.addWidget(name)
        tv.addWidget(tag)
        hl.addLayout(tv, 1)
        self.chip_cam = QLabel("Caméra : …")
        self.chip_cam.setObjectName("chip")
        self.chip_cal = QLabel("Calibrage : …")
        self.chip_cal.setObjectName("chip")
        hl.addWidget(self.chip_cam)
        hl.addWidget(self.chip_cal)
        outer.addWidget(head)
        lay = QHBoxLayout()
        outer.addLayout(lay, 1)

        # ------------------------------------------------ colonne gauche (défilante)
        left_w = QWidget()
        left = QVBoxLayout(left_w)
        left.setContentsMargins(0, 0, 8, 0)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setWidget(left_w)
        sa.setMinimumWidth(430)
        lay.addWidget(sa, 0)

        g = QGroupBox("1. Caméra")
        f = QVBoxLayout(g)
        self.src_combo = QComboBox()
        for k, (label, _) in SOURCES.items():
            self.src_combo.addItem(label, k)
        self.src_combo.setCurrentIndex(max(0, self.src_combo.findData(cfg["source"])))
        f.addWidget(self.src_combo)
        row = QHBoxLayout()
        self.cam_edit = QLineEdit()
        self.cam_edit.setPlaceholderText("Numéro de caméra (0, 1…) ou adresse http://…")
        row.addWidget(self.cam_edit, 1)
        self.btn_apply = QPushButton("Appliquer")
        row.addWidget(self.btn_apply)
        self.cam_row = QWidget()
        self.cam_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f.addWidget(self.cam_row)
        self.qr_lbl = QLabel()
        self.qr_lbl.setAlignment(Qt.AlignCenter)
        f.addWidget(self.qr_lbl)
        self.url_lbl = QLabel()
        self.url_lbl.setAlignment(Qt.AlignCenter)
        self.url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        f.addWidget(self.url_lbl)
        self.hint_lbl = QLabel()
        self.hint_lbl.setObjectName("hint")
        self.hint_lbl.setWordWrap(True)
        f.addWidget(self.hint_lbl)
        self.btn_relearn = QPushButton("Réapprendre le fond infrarouge")
        f.addWidget(self.btn_relearn)
        self.status_lbl = QLabel("…")
        self.status_lbl.setObjectName("status")
        self.status_lbl.setWordWrap(True)
        f.addWidget(self.status_lbl)
        left.addWidget(g)

        g = QGroupBox("2. Écran projeté et calibrage")
        f = QVBoxLayout(g)
        self.screen_combo = QComboBox()
        self.set_screens(screens)
        f.addWidget(self.screen_combo)
        row = QHBoxLayout()
        self.btn_cal_pen = QPushButton("🎯 Calibrer au stylet")
        self.btn_cal_auto = QPushButton("⚡ Calibrage auto")
        row.addWidget(self.btn_cal_pen)
        row.addWidget(self.btn_cal_auto)
        f.addLayout(row)
        self.calib_lbl = QLabel()
        self.calib_lbl.setObjectName("hint")
        f.addWidget(self.calib_lbl)
        left.addWidget(g)

        g = QGroupBox("3. Pointeur")
        f = QFormLayout(g)
        self.ptr_combo = QComboBox()
        self.ptr_combo.addItem("✏️ Stylet à LED", "led")
        self.ptr_combo.addItem("☝️ Doigt (le pointeur suit l'index)", "doigt")
        self.ptr_combo.setCurrentIndex(max(0, self.ptr_combo.findData(cfg.get("pointer", "led"))))
        f.addRow("Pointer avec", self.ptr_combo)
        self.click_combo = QComboBox()
        self.click_combo.addItem("Pincer le pouce et l'index", "pincer")
        self.click_combo.addItem("Garder le doigt immobile 1 s", "maintien")
        self.click_combo.setCurrentIndex(max(0, self.click_combo.findData(cfg.get("finger_click", "pincer"))))
        f.addRow("Clic avec le doigt", self.click_combo)
        self.crop_chk = QCheckBox("Zoomer sur la projection avant la détection (plus précis)")
        self.crop_chk.setChecked(bool(cfg.get("hand_crop", True)))
        f.addRow(self.crop_chk)
        self.ptr_hint = QLabel("Mode doigt : caméra en exposition normale. Pincer = clic maintenu (écrire, glisser) ; "
                               "« immobile 1 s » = simple clic (souris, boutons). Non disponible avec la caméra infrarouge.")
        self.ptr_hint.setObjectName("hint")
        self.ptr_hint.setWordWrap(True)
        f.addRow(self.ptr_hint)
        left.addWidget(g)

        g = QGroupBox("4. Mode")
        f = QGridLayout(g)
        self.mode_btns = {}
        for i, (m, txt) in enumerate([("souris", "🖱️ Souris"), ("annoter", "🖊️ Annoter"), ("tableau", "📋 Tableau")]):
            b = QPushButton(txt)
            b.setProperty("mode", True)
            b.clicked.connect(lambda _=False, m=m: self.mode_requested.emit(m))
            self.mode_btns[m] = b
            f.addWidget(b, 0, i)
        self.laser_chk = QCheckBox("Pointeur laser en mode souris (clic = point immobile 1 s)")
        self.laser_chk.setChecked(bool(cfg.get("laser")))
        f.addWidget(self.laser_chk, 1, 0, 1, 3)
        left.addWidget(g)
        left.addStretch(1)

        # ------------------------------------------------ colonne droite (défilante)
        right_w = QWidget()
        right = QVBoxLayout(right_w)
        right.setContentsMargins(0, 0, 8, 0)
        sa2 = QScrollArea()
        sa2.setWidgetResizable(True)
        sa2.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa2.setWidget(right_w)
        lay.addWidget(sa2, 1)
        g = QGroupBox("Vue de la caméra")
        f = QVBoxLayout(g)
        self.preview = QLabel("Aucune image")
        self.preview.setMinimumSize(480, 270)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#020617;border-radius:8px;")
        f.addWidget(self.preview, 1)
        self.pens_lbl = QLabel("Stylets : —")
        f.addWidget(self.pens_lbl)
        right.addWidget(g, 1)

        g = QGroupBox("Réglages de détection")
        f = QFormLayout(g)
        self.sl_thr = self._slider(50, 255, cfg["threshold"])
        self.sl_min = self._slider(1, 60, cfg["min_area"])
        self.sl_max = self._slider(20, 3000, cfg["max_area"])
        self.sl_smooth = self._slider(0, 95, int(cfg["smoothing"] * 100))
        f.addRow("Seuil de luminosité", self.sl_thr)
        f.addRow("Taille mini du point", self.sl_min)
        f.addRow("Taille maxi du point", self.sl_max)
        f.addRow("Stabilisation du pointeur", self.sl_smooth)
        self.color_chk = QCheckBox("Distinguer les stylets par la couleur de la LED")
        self.color_chk.setChecked(bool(cfg["color_pens"]))
        f.addRow(self.color_chk)
        self.pens_spin = QSpinBox()
        self.pens_spin.setRange(1, 6)
        self.pens_spin.setValue(int(cfg["max_pens"]))
        f.addRow("Stylets simultanés (max)", self.pens_spin)
        right.addWidget(g)

        # signaux
        self.src_combo.currentIndexChanged.connect(self._on_src)
        self.btn_apply.clicked.connect(self._on_src)
        self.btn_cal_pen.clicked.connect(lambda: self.calibrate_requested.emit("pen"))
        self.btn_cal_auto.clicked.connect(lambda: self.calibrate_requested.emit("auto"))
        self.screen_combo.currentIndexChanged.connect(self.screen_changed)
        self.btn_relearn.clicked.connect(self.relearn_requested)
        for w in (self.sl_thr, self.sl_min, self.sl_max, self.sl_smooth):
            w.valueChanged.connect(self._on_params)
        self.color_chk.toggled.connect(self._on_params)
        self.pens_spin.valueChanged.connect(self._on_params)
        self.laser_chk.toggled.connect(self._on_params)
        self.ptr_combo.currentIndexChanged.connect(self._on_params)
        self.click_combo.currentIndexChanged.connect(self._on_params)
        self.crop_chk.toggled.connect(self._on_params)
        self._sync_src_widgets()
        self._sync_ptr_widgets()

    def _slider(self, a, b, v):
        s = QSlider(Qt.Horizontal)
        s.setRange(a, b)
        s.setValue(int(v))
        return s

    def set_screens(self, screens):
        self.screen_combo.blockSignals(True)
        self.screen_combo.clear()
        for i, s in enumerate(screens):
            g = s.geometry()
            self.screen_combo.addItem(f"Écran {i + 1} : {s.name()} ({g.width()}×{g.height()})", s.name())
        self.screen_combo.blockSignals(False)

    def select_screen(self, idx):
        self.screen_combo.blockSignals(True)
        self.screen_combo.setCurrentIndex(idx)
        self.screen_combo.blockSignals(False)

    def _sync_src_widgets(self):
        k = self.src_combo.currentData()
        self.cam_row.setVisible(k in ("webcam", "ir"))
        self.qr_lbl.setVisible(k == "phone")
        self.url_lbl.setVisible(k == "phone")
        self.btn_relearn.setVisible(k == "ir")
        self.cam_edit.setText(str(self.cfg.get("ir_camera" if k == "ir" else "webcam", "0")))
        hints = {
            "phone": "Scannez le QR code avec le portable (même Wi-Fi que le PC). Si un avertissement de sécurité "
                     "s'affiche : « Paramètres avancés » → « Continuer vers le site ». Autorisez ensuite la caméra.",
            "webcam": "Webcam USB, ou portable utilisé comme webcam avec DroidCam / Iriun (souvent la caméra 1). "
                      "Une adresse http://IP:4747/video fonctionne aussi avec DroidCam.",
            "ir": "Caméra infrarouge (ou webcam équipée d'un filtre passe-IR) et stylet à LED IR 850/940 nm. "
                  "Le fond infrarouge (soleil, lampes) est appris et soustrait automatiquement.",
        }
        self.hint_lbl.setText(hints.get(k, ""))

    def _on_src(self):
        k = self.src_combo.currentData()
        self.cfg["source"] = k
        if self.sender() is self.btn_apply:
            self.cfg["ir_camera" if k == "ir" else "webcam"] = self.cam_edit.text().strip() or "0"
        self._sync_src_widgets()
        self.source_changed.emit()

    def _on_params(self):
        c = self.cfg
        c["threshold"] = self.sl_thr.value()
        c["min_area"] = self.sl_min.value()
        c["max_area"] = max(self.sl_max.value(), c["min_area"] + 1)
        c["smoothing"] = self.sl_smooth.value() / 100.0
        c["color_pens"] = self.color_chk.isChecked()
        c["max_pens"] = self.pens_spin.value()
        c["laser"] = self.laser_chk.isChecked()
        c["pointer"] = self.ptr_combo.currentData()
        c["finger_click"] = self.click_combo.currentData()
        c["hand_crop"] = self.crop_chk.isChecked()
        self._sync_ptr_widgets()
        self.params_changed.emit()

    def _sync_ptr_widgets(self):
        doigt = self.ptr_combo.currentData() == "doigt"
        self.click_combo.setEnabled(doigt)
        self.crop_chk.setEnabled(doigt)
        self.ptr_hint.setVisible(doigt)
        for w in (self.sl_thr, self.sl_min, self.sl_max, self.color_chk):
            w.setEnabled(not doigt)

    def set_url(self, url):
        if url:
            self.qr_lbl.setPixmap(qr_pixmap(url, 200))
            self.url_lbl.setText(url)

    def set_mode(self, mode):
        for m, b in self.mode_btns.items():
            b.setProperty("sel", m == mode)
            b.style().unpolish(b)
            b.style().polish(b)

    def show_preview(self, prev, blobs, roi):
        if prev is None:
            return
        img = preview_qimage(prev)
        if img.isNull():
            return
        pm = QPixmap.fromImage(img).scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = pm.width(), pm.height()
        if roi:
            p.setPen(QPen(QColor("#38bdf8"), 2))
            p.drawPolygon(QPolygonF([QPointF(x * W, y * H) for x, y in roi]))
        for b in blobs:
            col = QColor(PEN_COLORS.get(b[3], "#ffffff"))
            p.setPen(QPen(col, 3))
            p.setBrush(col if (len(b) > 4 and b[4]) else Qt.NoBrush)
            p.drawEllipse(QPointF(b[0] * W, b[1] * H), 12, 12)
        p.end()
        self.preview.setPixmap(pm)
        names = ", ".join(b[3] + (" (pincé)" if len(b) > 4 and b[4] else "") for b in blobs) or "aucun"
        self.pens_lbl.setText(f"Stylets vus : {names}")
