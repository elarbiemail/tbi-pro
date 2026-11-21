# -*- coding: utf-8 -*-
"""Clavier virtuel AZERTY, utilisable au stylet ou au doigt (le clavier physique marche aussi)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

ROWS = [
    list("1234567890°+"),
    list("azertyuiop^$"),
    list("qsdfghjklmù*"),
    list("<wxcvbn,;:!"),
    list("éèàçêâîôû'-?"),
]

DIALOG_CSS = """
QDialog, QWidget { background:#0f172a; color:#f1f5f9; font: 12pt "Segoe UI"; }
QLineEdit, QPlainTextEdit { background:#f8fafc; color:#0f172a; border-radius:10px; padding:10px; font-size:20pt; }
QPushButton { background:#1e293b; border:1px solid #334155; border-radius:10px; min-height:52px; font-size:16pt; }
QPushButton:pressed { background:#0369a1; }
QPushButton#ok { background:#0284c7; font-weight:700; }
QPushButton#cancel { background:#7f1d1d; }
QLabel#title { font-size:16pt; font-weight:700; color:#7dd3fc; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:#1e293b; padding:12px 18px; border-radius:8px; margin:2px; font-size:12pt; }
QTabBar::tab:selected { background:#0369a1; }
QScrollArea { border:0; }
"""


class VirtualKeyboard(QWidget):
    def __init__(self, target, on_enter=None, parent=None):
        super().__init__(parent)
        self.target, self.on_enter, self.shift = target, on_enter, False
        g = QGridLayout(self)
        g.setSpacing(6)
        self.keys = []
        for r, row in enumerate(ROWS):
            for c, ch in enumerate(row):
                b = self._key(ch, lambda _=False, ch=ch: self.type(ch))
                self.keys.append((b, ch))
                g.addWidget(b, r, c)
        last = len(ROWS)
        g.addWidget(self._key("⇧ Maj", self.toggle_shift), last, 0, 1, 2)
        g.addWidget(self._key("Espace", lambda: self.type(" ")), last, 2, 1, 6)
        g.addWidget(self._key("⌫", self.backspace), last, 8, 1, 2)
        g.addWidget(self._key("↵", self.enter), last, 10, 1, 2)
        if isinstance(target, QPlainTextEdit):
            g.addWidget(self._key("⇥ Sous-idée", lambda: self.type("    ")), last + 1, 0, 1, 4)
            g.addWidget(self._key("⇤ Retrait", self.outdent), last + 1, 4, 1, 4)

    def _key(self, text, fn):
        b = QPushButton(text)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(lambda _=False: fn())
        return b

    def toggle_shift(self):
        self.shift = not self.shift
        for b, ch in self.keys:
            b.setText(ch.upper() if self.shift else ch)

    def type(self, ch):
        if self.shift:
            ch = ch.upper()
            self.toggle_shift()
        if isinstance(self.target, QLineEdit):
            self.target.insert(ch)
        else:
            self.target.insertPlainText(ch)
        self.target.setFocus()

    def backspace(self):
        if isinstance(self.target, QLineEdit):
            self.target.backspace()
        else:
            self.target.textCursor().deletePreviousChar()

    def outdent(self):
        cur = self.target.textCursor()
        cur.movePosition(cur.MoveOperation.StartOfLine)
        line = self.target.document().findBlock(cur.position()).text()
        n = min(4, len(line) - len(line.lstrip(" ")))
        for _ in range(n):
            cur.deleteChar()

    def enter(self):
        if isinstance(self.target, QLineEdit):
            if self.on_enter:
                self.on_enter()
        else:
            self.target.insertPlainText("\n")


def projected_dialog(dlg, screen, full=False, size=(1100, 720)):
    """Affiche une boîte de dialogue sur l'écran projeté, au premier plan."""
    dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
    g = screen.geometry() if screen else None
    if g is not None:
        if full:
            dlg.setGeometry(g.adjusted(40, 30, -40, -30))
        else:
            w, h = min(size[0], g.width() - 40), min(size[1], g.height() - 40)
            dlg.setGeometry(g.x() + (g.width() - w) // 2, g.y() + (g.height() - h) // 2, w, h)


class TextDialog(QDialog):
    """Saisie d'un texte court (outil Texte, recherche…)."""

    def __init__(self, title="Texte", initial="", parent=None, screen=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(DIALOG_CSS)
        lay = QVBoxLayout(self)
        t = QLabel(title)
        t.setObjectName("title")
        lay.addWidget(t)
        self.edit = QLineEdit(initial)
        lay.addWidget(self.edit)
        lay.addWidget(VirtualKeyboard(self.edit, self.accept))
        row = QHBoxLayout()
        bc = QPushButton("Annuler")
        bc.setObjectName("cancel")
        bc.clicked.connect(self.reject)
        bo = QPushButton("Valider")
        bo.setObjectName("ok")
        bo.clicked.connect(self.accept)
        row.addWidget(bc)
        row.addWidget(bo)
        lay.addLayout(row)
        projected_dialog(self, screen, size=(1000, 560))
        self.edit.setFocus()

    def text(self):
        return self.edit.text()
