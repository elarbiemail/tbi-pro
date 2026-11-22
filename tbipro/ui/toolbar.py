# -*- coding: utf-8 -*-
"""
Barre latérale à masquage automatique, utilisable au stylet / au doigt.

  • Barre principale : les outils les plus utilisés (modes, sélection, stylos, gomme,
    écriture→texte, formes, couleurs, épaisseurs, annuler/rétablir…).
  • Panneau « ⋯ Plus » : instruments, projecteur/rideau, bibliothèque, activités, pages, fichiers.
  • Sans interaction pendant quelques secondes, la barre se replie en un petit onglet
    au bord de l'écran (📌 pour l'épingler).
"""
from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .canvas import FILLABLE, PALETTE, WIDTHS

BTN = 52
AUTOHIDE_MS = 9000

STYLE = """
QFrame#tb, QFrame#more { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 rgba(15,23,42,240), stop:1 rgba(30,27,75,240));
                          border: 1px solid rgba(125,211,252,0.25); border-radius: 18px; }
QPushButton { background: rgba(30,41,59,0.95); color: #f1f5f9; border: 2px solid transparent; border-radius: 12px;
              font: 600 19px "Segoe UI Emoji","Segoe UI",sans-serif; }
QPushButton:hover { border-color: rgba(56,189,248,0.6); }
QPushButton:pressed, QPushButton[down="true"] { background: #334155; }
QPushButton[sel="true"] { border-color: #38bdf8; background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #075985, stop:1 #4c1d95); }
QPushButton#small { font-size: 15px; background: transparent; }
QLabel { color: #cbd5e1; font: 600 11px "Segoe UI",sans-serif; }
QLabel#section { color: #7dd3fc; font: 700 11px "Segoe UI"; padding-top: 4px; }
"""

TAB_STYLE = ("QPushButton{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0284c7,stop:1 #7c3aed);color:white;"
             "border-radius:14px;font:700 16px 'Segoe UI Emoji','Segoe UI';border:2px solid rgba(255,255,255,0.5);}"
             "QPushButton:pressed{background:#0c4a6e;}")

PRIMARY_TOOLS = [("select", "🖐️", "Sélection : déplacer, agrandir, pivoter, dupliquer, supprimer"),
                 ("pen", "✏️", "Stylo"), ("marker", "🖍️", "Surligneur"), ("eraser", "🧽", "Gomme"),
                 ("handwrite", "✍️", "Écriture → texte (reconnaissance de l'écriture manuscrite)"),
                 ("magic", "🪄", "Stylo de formes : cercle, rectangle, triangle, ligne, flèche reconnus"),
                 ("autodraw", "🖌️", "Croquis → icône : dessinez un objet, choisissez l'icône proposée"),
                 ("text", "🔤", "Texte (clavier virtuel)"),
                 ("postit", "🗒️", "Post-it : touchez la page puis écrivez la note (agrandissable avec 🖐️)"),
                 ("line", "╱", "Ligne"), ("arrow", "➚", "Flèche"), ("rect", "▭", "Rectangle"),
                 ("ellipse", "◯", "Ellipse / cercle"), ("triangle", "△", "Triangle"), ("star", "☆", "Étoile")]


def _shadow(w):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(28)
    eff.setOffset(0, 6)
    eff.setColor(QColor(0, 0, 0, 150))
    w.setGraphicsEffect(eff)


class Toolbar(QFrame):
    mode_requested = Signal(str)       # "souris", "annoter", "tableau"
    panel_requested = Signal()
    action = Signal(str)               # actions demandant la fenêtre hôte

    def __init__(self, canvas, kind, parent=None):
        super().__init__(parent)
        self.setObjectName("tb")
        self.setStyleSheet(STYLE)
        _shadow(self)
        self.canvas, self.kind = canvas, kind
        self.active_key = "souris"     # stylet qui a touché la barre en dernier
        self.side = "bottom"            # barre horizontale en bas (ou en haut)
        self.pinned = False
        self.tool_btns, self.color_btns, self.width_btns = {}, {}, {}
        self.page_lbl = None

        # ------------------------------------------------ barre principale
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        top = QVBoxLayout()
        top.setSpacing(4)
        self.btn_pin = self._btn("📌", "Épingler la barre (ne plus la masquer)", self.toggle_pin, small=True)
        top.addWidget(self.btn_pin)
        top.addWidget(self._btn("⇅", "Barre en haut / en bas", self.toggle_side, small=True))
        top.addWidget(self._btn("⌄", "Masquer la barre", self.hide_bar, small=True))
        outer.addLayout(top)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)
        outer.addWidget(self.body)

        B = self._btn
        modes = [B("🖱️", "Mode souris (piloter l'ordinateur)", lambda: self.mode_requested.emit("souris"))]
        if kind == "board":
            modes.append(B("🖊️", "Annoter l'écran", lambda: self.mode_requested.emit("annoter")))
        else:
            modes.append(B("📋", "Tableau blanc", lambda: self.mode_requested.emit("tableau")))
        self.btn_more = B("⋯", "Plus d'outils : instruments, bibliothèque, activités, pages, fichiers", self.toggle_more)
        modes.append(self.btn_more)
        tools = []
        for t, icon, tip in PRIMARY_TOOLS:
            b = B(icon, tip, lambda t=t: self.set_tool(t))
            self.tool_btns[t] = b
            tools.append(b)
        colors = []
        for c in PALETTE:
            b = B("", c, lambda c=c: self.set_color(c))
            b.setStyleSheet(f"QPushButton{{background:{c};border:2px solid rgba(255,255,255,0.25);}}"
                            f"QPushButton[sel=\"true\"]{{border:3px solid #38bdf8;}}")
            self.color_btns[c] = b
            colors.append(b)
        colors.append(B("🎨", "Autre couleur…", lambda: self.action.emit("color")))
        for name, icon in [("fin", "•"), ("moyen", "●"), ("epais", "⬤")]:
            b = B(icon, f"Épaisseur {name}", lambda n=name: self.set_width(n))
            self.width_btns[name] = b
            colors.append(b)
        self.btn_fill = B("◧", "Formes pleines / vides", self.toggle_fill)
        colors.append(self.btn_fill)
        edit = [B("↶", "Annuler", self._do(self.canvas.undo)), B("↷", "Rétablir", self._do(self.canvas.redo)),
                B("🗑️", "Effacer la page", self._do(self.canvas.clear_page))]
        if kind == "board":
            edit.append(B("▶", "Page suivante (crée une page à la fin)", self._do(self._next_page)))
        else:
            edit.append(B("📸", "Capture d'écran / vidéo", lambda: self.action.emit("capture")))
        self.sections = [modes, tools, colors, edit]
        self._seps = []
        self.cols = 0
        self._layout(3)

        # ------------------------------------------------ panneau « Plus »
        self.more = QFrame(parent)
        self.more.setObjectName("more")
        self.more.setStyleSheet(STYLE)
        _shadow(self.more)
        mv = QHBoxLayout(self.more)
        mv.setContentsMargins(12, 10, 12, 10)
        mv.setSpacing(14)

        def section(title, items, cols=None):
            box = QVBoxLayout()
            box.setSpacing(4)
            lbl = QLabel(title)
            lbl.setObjectName("section")
            box.addWidget(lbl)
            g = QGridLayout()
            g.setSpacing(6)
            cols = cols or max(2, (len(items) + 1) // 2)       # deux rangées
            for i, w in enumerate(items):
                g.addWidget(w, i // cols, i % cols)
            box.addLayout(g)
            box.addStretch(1)
            mv.addLayout(box)

        ins = lambda k: self._do(lambda: self.canvas.toggle_instrument(k))
        compass = B("🧭", "Compas : appuyer au centre, glisser pour le rayon", lambda: self.set_tool("compass"))
        self.tool_btns["compass"] = compass
        section("GÉOMÉTRIE", [B("📏", "Règle", ins("regle")), B("📐", "Équerre", ins("equerre")),
                              B("◠", "Rapporteur", ins("rapporteur")), compass])
        section("PRÉSENTER", [B("🔦", "Projecteur (spot) : seule une zone reste visible", ins("projecteur")),
                              B("🎭", "Rideau : cacher puis dévoiler progressivement", ins("rideau")),
                              B("⏱️", "Minuteur / chronomètre", lambda: self.action.emit("timer")),
                              B("🎲", "Tirage au sort (élèves, dé)", lambda: self.action.emit("picker"))])
        section("RESSOURCES ET ACTIVITÉS", [
            B("🖼️", "Bibliothèque d'images", lambda: self.action.emit("library")),
            B("☁️", "Nuage de mots (QR code élèves)", lambda: self.action.emit("cloud")),
            B("🧠", "Carte mentale", lambda: self.action.emit("mindmap")),
            B("📸", "Capture d'écran / vidéo avec éditeur", lambda: self.action.emit("capture")),
            B("⚙️", "Panneau de contrôle", self.panel_requested.emit)])
        if kind == "board":
            self.page_lbl = QLabel("Page 1 / 1")
            self.page_lbl.setAlignment(Qt.AlignCenter)
            section("PAGES", [self.page_lbl,B("◀", "Page précédente", self._do(lambda: self.canvas.go_page(self.canvas.index - 1))),
                              B("▶", "Page suivante", self._do(self._next_page)),
                              B("➕", "Nouvelle page", self._do(self.canvas.add_page)),
                              B("🗂️", "Gérer les pages (aperçus, réordonner, dupliquer)", lambda: self.action.emit("pages")),
                              B("▦", "Changer le fond (Seyès, repère, millimétré…)", self._do(self.canvas.cycle_background)),
                              B("❌", "Supprimer la page", self._do(self.canvas.delete_page))])
            section("FICHIERS", [B("💾", "Enregistrer (Documents/TBI Pro)", lambda: self.action.emit("save")),
                                 B("📂", "Ouvrir un tableau", lambda: self.action.emit("open")),
                                 B("📥", "Importer un PDF ou une présentation exportée en PDF", lambda: self.action.emit("pdfimport")),
                                 B("📄", "Exporter en PDF", lambda: self.action.emit("pdf"))])
        else:
            section("ÉCRAN", [B("❄️", "Figer / libérer l'écran", lambda: self.action.emit("freeze")),
                              B("📸", "Capture d'écran / vidéo", lambda: self.action.emit("capture"))])
        self.more.hide()

        # ------------------------------------------------ onglet (barre masquée)
        self.tab = QPushButton("☰  Outils", parent)
        self.tab.setToolTip("Afficher la barre d'outils")
        self.tab.setFixedSize(120, 40)
        self.tab.setStyleSheet(TAB_STYLE)
        self.tab.setFocusPolicy(Qt.NoFocus)
        self.tab.clicked.connect(lambda _=False: self.show_bar())
        self.tab.hide()

        self.hide_timer = QTimer(self, singleShot=True, interval=AUTOHIDE_MS, timeout=self._auto_hide)
        self.canvas.changed.connect(self.refresh)
        self.refresh()
        self.hide_timer.start()

    # -------------------------------------------------------------- construction
    def _btn(self, text, tip, fn, small=False):
        b = QPushButton(text)
        b.setToolTip(tip)
        if small:
            b.setObjectName("small")
            b.setFixedSize(38, 34)
        else:
            b.setFixedSize(BTN, BTN)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(lambda _=False, f=fn: (self.poke(), f()))
        return b

    def _sep(self):
        s = QFrame()
        s.setFixedWidth(2)
        s.setStyleSheet("background:rgba(125,211,252,0.18);border-radius:1px;")
        return s

    def _layout(self, rows):
        """Sections côte à côte, chacune sur « rows » rangées, séparées par un trait vertical."""
        if rows == self.cols:
            return
        self.cols = rows
        g = self.grid
        while g.count():
            g.takeAt(0)
        c = 0
        for si, sec in enumerate(self.sections):
            if si:
                if len(self._seps) < si:
                    self._seps.append(self._sep())
                g.addWidget(self._seps[si - 1], 0, c, rows, 1)
                c += 1
            ncol = (len(sec) + rows - 1) // rows
            for i, w in enumerate(sec):
                g.addWidget(w, i % rows, c + i // rows)
            c += ncol

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

    # -------------------------------------------------------------- masquage automatique
    def poke(self):
        """Interaction avec la barre : on repousse le masquage automatique."""
        if not self.pinned:
            self.hide_timer.start()

    def _auto_hide(self):
        if not self.pinned and self.isVisible():
            self.hide_bar()

    def hide_bar(self):
        self.hide()
        self.more.hide()
        self.tab.show()
        self.place()

    def show_bar(self):
        self.tab.hide()
        self.show()
        self.place()
        self.poke()

    def toggle_pin(self):
        self.pinned = not self.pinned
        self._mark(self.btn_pin, self.pinned)
        if self.pinned:
            self.hide_timer.stop()
        else:
            self.hide_timer.start()

    def toggle_more(self):
        self.more.setVisible(not self.more.isVisible())
        self._mark(self.btn_more, self.more.isVisible())
        self.place()

    # -------------------------------------------------------------- réglages du stylet actif
    def state(self):
        return self.canvas.tool_for(self.active_key)

    def set_tool(self, t):
        self.state().tool = t
        if t != "select":
            self.canvas.selected = None
            self.canvas.update()
        self.refresh()

    def set_color(self, c):
        st = self.state()
        st.color = c
        if st.tool in ("eraser", "select"):
            st.tool = "pen"
        sel = self.canvas.selected
        if sel is not None and "c" in sel:                  # recolorer l'objet sélectionné
            self.canvas.recolor_selected(c)
        self.refresh()

    def set_width(self, n):
        self.state().width = WIDTHS[n]
        self.refresh()

    def toggle_fill(self):
        st = self.state()
        st.fill = not st.fill
        self.refresh()

    def refresh(self):
        st = self.state()
        for t, b in self.tool_btns.items():
            self._mark(b, st.tool == t)
        for c, b in self.color_btns.items():
            self._mark(b, st.color.lower() == c.lower())
        for n, b in self.width_btns.items():
            self._mark(b, st.width == WIDTHS[n])
        self._mark(self.btn_fill, st.fill)
        if self.page_lbl is not None:
            self.page_lbl.setText(f"Page {self.canvas.index + 1} / {len(self.canvas.pages)}")

    @staticmethod
    def _mark(b, sel):
        if b.property("sel") != sel:
            b.setProperty("sel", sel)
            b.style().unpolish(b)
            b.style().polish(b)

    # -------------------------------------------------------------- placement
    def toggle_side(self):
        self.side = "top" if self.side == "bottom" else "bottom"
        self.place()

    def place(self):
        p = self.parentWidget()
        if not p:
            return
        for rows in (1, 2, 3, 4):
            self._layout(rows)
            self.body.adjustSize()
            self.adjustSize()
            if self.width() <= p.width() - 24:
                break
        x = max(12, (p.width() - self.width()) // 2)
        y = p.height() - self.height() - 12 if self.side == "bottom" else 12
        self.move(QPoint(x, y))
        self.raise_()
        if self.more.isVisible():
            self.more.adjustSize()
            mx = max(12, min(p.width() - self.more.width() - 12, (p.width() - self.more.width()) // 2))
            my = y - self.more.height() - 10 if self.side == "bottom" else y + self.height() + 10
            self.more.move(mx, max(12, my))
            self.more.raise_()
        ty = p.height() - self.tab.height() if self.side == "bottom" else 0
        self.tab.move((p.width() - self.tab.width()) // 2, ty)
        self.tab.raise_()
