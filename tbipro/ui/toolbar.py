# -*- coding: utf-8 -*-
"""Barre d'outils flottante, à gros boutons utilisables au stylet."""
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .canvas import PALETTE, WIDTHS

BTN = 54

STYLE = """
QFrame#tb { background: rgba(15,23,42,235); border-radius: 14px; }
QPushButton { background: #1e293b; color: #f1f5f9; border: 2px solid transparent; border-radius: 10px;
              font: 600 20px "Segoe UI Emoji","Segoe UI",sans-serif; }
QPushButton:pressed, QPushButton[down="true"] { background: #334155; }
QPushButton[sel="true"] { border-color: #38bdf8; background: #0c4a6e; }
QPushButton[mode="true"] { font-size: 13px; }
QLabel { color: #cbd5e1; font: 600 12px "Segoe UI",sans-serif; }
"""

TOOLS = [("pen", "✏️", "Stylo"), ("marker", "🖍️", "Surligneur"), ("eraser", "🧽", "Gomme"), ("move", "✋", "Déplacer"),
         ("line", "╱", "Ligne"), ("arrow", "➚", "Flèche"), ("rect", "▭", "Rectangle"), ("ellipse", "◯", "Ellipse"),
         ("text", "🔤", "Texte (clavier virtuel)"), ("compass", "🧭", "Compas : appuyer au centre, glisser pour le rayon")]


class Toolbar(QFrame):
    mode_requested = Signal(str)       # "souris", "annoter", "tableau"
    panel_requested = Signal()
    action = Signal(str)               # actions qui demandent la fenêtre hôte (fichiers, capture…)

    def __init__(self, canvas, kind, parent=None):
        super().__init__(parent)
        self.setObjectName("tb")
        self.setStyleSheet(STYLE)
        self.canvas, self.kind = canvas, kind
        self.active_key = "souris"     # stylet qui a touché la barre en dernier
        self.collapsed = False
        self.side = "left"
        self.tool_btns, self.color_btns, self.width_btns = {}, {}, {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        top = QGridLayout()
        top.setSpacing(6)
        self.btn_fold = self._btn("☰", "Réduire / déplier la barre", self.toggle_fold)
        self.btn_side = self._btn("⇆", "Changer de côté", self.toggle_side)
        top.addWidget(self.btn_fold, 0, 0)
        top.addWidget(self.btn_side, 0, 1)
        outer.addLayout(top)

        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        self.page_lbl = None
        B = self._btn
        sections = []
        modes = [B("🖱️", "Mode souris (piloter l'ordinateur)", lambda: self.mode_requested.emit("souris"))]
        if kind == "board":
            modes.append(B("🖊️", "Annoter l'écran", lambda: self.mode_requested.emit("annoter")))
        else:
            modes.append(B("📋", "Tableau blanc", lambda: self.mode_requested.emit("tableau")))
        modes.append(B("⚙️", "Panneau de contrôle", self.panel_requested.emit))
        sections.append(modes)
        tools = []
        for t, icon, tip in TOOLS:
            b = B(icon, tip, lambda t=t: self.set_tool(t))
            self.tool_btns[t] = b
            tools.append(b)
        sections.append(tools)
        colors = []
        for c in PALETTE:
            b = B("", c, lambda c=c: self.set_color(c))
            b.setStyleSheet(f"QPushButton{{background:{c};}} QPushButton[sel=\"true\"]{{border-color:#38bdf8;}}")
            self.color_btns[c] = b
            colors.append(b)
        for name, icon in [("fin", "•"), ("moyen", "●"), ("epais", "⬤")]:
            b = B(icon, f"Épaisseur {name}", lambda n=name: self.set_width(n))
            self.width_btns[name] = b
            colors.append(b)
        sections.append(colors)
        edit = [B("↶", "Annuler", self._do(self.canvas.undo)), B("↷", "Rétablir", self._do(self.canvas.redo)),
                B("🗑️", "Effacer la page", self._do(self.canvas.clear_page))]
        sections.append([B("📏", "Règle (glisser pour déplacer, ⟳ pour tourner, tracer le long du bord)",
                           self._do(lambda: self.canvas.toggle_instrument("regle"))),
                         B("📐", "Équerre", self._do(lambda: self.canvas.toggle_instrument("equerre"))),
                         B("◠", "Rapporteur", self._do(lambda: self.canvas.toggle_instrument("rapporteur"))),
                         B("🖼️", "Bibliothèque d'images (pictogrammes, banques libres en ligne, mes ressources)",
                           lambda: self.action.emit("library")),
                         B("⏱️", "Chronomètre / minuteur", lambda: self.action.emit("timer")),
                         B("☁️", "Nuage de mots (les élèves participent par QR code)", lambda: self.action.emit("cloud")),
                         B("🧠", "Carte mentale", lambda: self.action.emit("mindmap"))])
        if kind == "board":
            edit.append(B("▦", "Changer le fond", self._do(self.canvas.cycle_background)))
            sections.append(edit)
            self.page_lbl = QLabel("1 / 1")
            self.page_lbl.setAlignment(Qt.AlignCenter)
            sections.append([B("◀", "Page précédente", self._do(lambda: self.canvas.go_page(self.canvas.index - 1))),
                             B("▶", "Page suivante (crée une page à la fin)", self._do(self._next_page)),
                             B("➕", "Nouvelle page", self._do(self.canvas.add_page)),
                             B("❌", "Supprimer la page", self._do(self.canvas.delete_page)),
                             self.page_lbl])
            sections.append([B("💾", "Enregistrer (Documents/TBI Pro)", lambda: self.action.emit("save")),
                             B("📂", "Ouvrir un tableau", lambda: self.action.emit("open")),
                             B("📄", "Exporter en PDF", lambda: self.action.emit("pdf"))])
        else:
            edit += [B("❄️", "Figer / libérer l'écran", lambda: self.action.emit("freeze")),
                     B("📸", "Capture (Documents/TBI Pro)", lambda: self.action.emit("capture"))]
            sections.append(edit)
        sections.append([B("✖", "Quitter (mode souris)", lambda: self.mode_requested.emit("souris"))])
        self.sections = sections
        self.cols = 0
        self._layout(3)
        outer.addWidget(self.body)
        self.canvas.changed.connect(self.refresh)
        self.refresh()

    # -------------------------------------------------------------- construction
    def _btn(self, text, tip, fn):
        b = QPushButton(text)
        b.setToolTip(tip)
        b.setFixedSize(BTN, BTN)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(lambda _=False, f=fn: f())
        return b

    def _layout(self, cols):
        if cols == self.cols:
            return
        self.cols = cols
        g = self.grid
        while g.count():
            g.takeAt(0)
        r = 0
        for si, sec in enumerate(self.sections):
            if si:
                if not hasattr(self, "_seps"):
                    self._seps = []
                if len(self._seps) < si:
                    self._seps.append(self._sep())
                g.addWidget(self._seps[si - 1], r, 0, 1, cols)
                r += 1
            for i, w in enumerate(sec):
                if isinstance(w, QLabel):
                    r += (i + cols - 1) // cols if i % cols else i // cols
                    g.addWidget(w, r, 0, 1, cols)
                    r += 1
                    break
                g.addWidget(w, r + i // cols, i % cols)
            else:
                r += (len(sec) + cols - 1) // cols
                continue

    def _sep(self):
        s = QFrame()
        s.setFixedHeight(2)
        s.setStyleSheet("background:#334155;")
        return s

    def _do(self, fn):
        def run():
            fn()
            self.refresh()
        return run

    def _next_page(self):
        c = self.canvas
        if c.index >= len(c.pages) - 1:
            c.add_page()
        else:
            c.go_page(c.index + 1)

    # -------------------------------------------------------------- réglages du stylet actif
    def state(self):
        return self.canvas.tool_for(self.active_key)

    def set_tool(self, t):
        self.state().tool = t
        self.refresh()

    def set_color(self, c):
        st = self.state()
        st.color = c
        if st.tool in ("eraser", "move"):
            st.tool = "pen"
        self.refresh()

    def set_width(self, n):
        self.state().width = WIDTHS[n]
        self.refresh()

    def refresh(self):
        st = self.state()
        for t, b in self.tool_btns.items():
            self._mark(b, st.tool == t)
        for c, b in self.color_btns.items():
            self._mark(b, st.color.lower() == c.lower())
        for n, b in self.width_btns.items():
            self._mark(b, st.width == WIDTHS[n])
        if self.page_lbl is not None:
            self.page_lbl.setText(f"Page {self.canvas.index + 1} / {len(self.canvas.pages)}")

    @staticmethod
    def _mark(b, sel):
        if b.property("sel") != sel:
            b.setProperty("sel", sel)
            b.style().unpolish(b)
            b.style().polish(b)

    # -------------------------------------------------------------- placement
    def toggle_fold(self):
        self.collapsed = not self.collapsed
        self.body.setVisible(not self.collapsed)
        self.adjustSize()
        self.place()

    def toggle_side(self):
        self.side = "right" if self.side == "left" else "left"
        self.place()

    def place(self):
        p = self.parentWidget()
        if not p:
            return
        self.adjustSize()
        for cols in (3, 4, 5, 6):
            self._layout(cols)
            self.body.adjustSize()
            self.adjustSize()
            if self.height() <= p.height() - 24:
                break
        x = 12 if self.side == "left" else p.width() - self.width() - 12
        y = max(12, (p.height() - self.height()) // 2)
        self.move(QPoint(x, y))
        self.raise_()
