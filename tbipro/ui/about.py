# -*- coding: utf-8 -*-
"""Fenêtres « Aide » (guide intégré, démarrage rapide, recherche) et « À propos »."""
import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap, QTextDocument
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..config import APP_NAME, VERSION, resource_path
from .keyboard import DIALOG_CSS, projected_dialog

REPO_URL = "https://github.com/elarbiemail/tbi-pro"

HELP_CSS = DIALOG_CSS + """
QTextBrowser { background:#f8fafc; color:#0f172a; border-radius:12px; padding:14px; font-size:13pt; }
QLineEdit { font-size:13pt; padding:8px; }
QLabel#info { color:#94a3b8; font-size:11pt; }
"""

QUICK_START = """
# Démarrage rapide

1. **Branchez le vidéoprojecteur** puis lancez TBI Pro : le panneau de contrôle s'ouvre sur l'écran du PC.
2. **Caméra** (section 1) :
   - *Portable* : scannez le QR code (même Wi-Fi). Si un avertissement apparaît : « Paramètres avancés » → « Continuer ». Touchez « Démarrer la caméra ».
   - *Webcam / DroidCam* ou *caméra infrarouge* : indiquez le numéro de caméra puis « Appliquer ».
3. **Écran projeté** (section 2) : choisissez l'écran du vidéoprojecteur.
4. **Pointeur** (section 3) : *stylet à LED* ou *doigt* (le pointeur suit l'index).
5. **Calibrage** : « 🎯 Calibrer au stylet » puis touchez le centre des 4 cibles. Avec le doigt : pointez l'index immobile 1 s sur chaque cible, ou pincez. « ⚡ Calibrage auto » fonctionne aussi avec le portable et la webcam.
6. **Mode** (section 4) : 🖱️ *Souris* (piloter tous les logiciels), 🖊️ *Annoter* (écrire par-dessus l'écran) ou 📋 *Tableau* (tableau blanc).

## Gestes utiles

| Je veux… | Je fais… |
|---|---|
| Écrire | ✏️ puis j'appuie la pointe du stylet (ou je pince pouce + index) |
| Déplacer / agrandir / pivoter un objet | 🖐️ puis je touche l'objet : glisser, coins, poignée ⟳ |
| Transformer un dessin en forme nette | 🪄 (ou ⬠ sur un trait sélectionné) |
| Transformer mon écriture en texte | ✍️ puis j'écris (Internet nécessaire) |
| Remplacer un croquis par une icône | 🖌️ puis je dessine et je choisis l'icône |
| Faire réapparaître la barre d'outils | je touche l'onglet « ☰ Outils » en bas de l'écran |
| Plus d'outils (règle, minuteur, bibliothèque…) | ⋯ dans la barre |
| Revenir au mode souris | 🖱️ ou la touche Échap |

## En cas de problème

- **Rien ne se passe** : vérifiez dans le panneau la « Vue de la caméra » : le stylet ou le doigt doit y être entouré.
- **Le curseur saute** (stylet) : baissez l'exposition de la caméra, montez le seuil de luminosité.
- **La main n'est pas vue** (doigt) : éclairez la main, remontez l'exposition sur le portable, tenez-vous de côté.
- **Décalage** : recalibrez.

Le guide complet est dans l'onglet « Guide complet ».
"""

CREDITS = """
<h2>{name} {version}</h2>
<p><b>Tableau blanc interactif à faible coût</b> : un vidéoprojecteur, un PC, une caméra (portable, webcam ou caméra
infrarouge) et un stylet à LED ou le doigt.</p>
<p>Conception : <b>El Arbi EL ADLOUNI</b> — enseignant de français et formateur, Sefrou (Maroc).<br>
Développement assisté par l'IA Claude (Anthropic).</p>
<p>Code source et mises à jour : <a href="{repo}">{repo}</a></p>
<h3>Composants et ressources libres</h3>
<ul>
<li>Interface : Qt / PySide6 (LGPL v3)</li>
<li>Vision : OpenCV (Apache 2.0), NumPy (BSD)</li>
<li>Détection de la main : Google MediaPipe Hand Landmarker (Apache 2.0)</li>
<li>Serveur local : aiohttp (Apache 2.0), cryptography (Apache 2.0 / BSD), qrcode (BSD)</li>
<li>Son et vidéo : soundcard (BSD), FFmpeg via imageio-ffmpeg (LGPL / GPL)</li>
<li>Pictogrammes : ARASAAC — Sergio Palao, Gouvernement d'Aragon (CC BY-NC-SA)</li>
<li>Icônes : OpenMoji (CC BY-SA 4.0), Noto Emoji (Apache 2.0), Twemoji (CC BY 4.0), Fluent Emoji (MIT),
Material Design Icons, Tabler, Phosphor, Carbon (licences libres) via Iconify</li>
<li>Images : Openverse (Creative Commons), Wikimedia Commons, The Metropolitan Museum of Art (Open Access CC0),
drapeaux flagcdn.com (domaine public)</li>
<li>Reconnaissance de l'écriture et des croquis : service en ligne Google Input Tools</li>
</ul>
<p style="color:#64748b">Les images insérées depuis les banques en ligne gardent la licence de leur auteur ; le crédit est
ajouté automatiquement sous l'image quand il est requis. Les pictogrammes ARASAAC sont réservés à un usage non commercial.</p>
"""


def guide_path():
    """Le guide (GUIDE.md) : dans l'exécutable ou à la racine du projet."""
    cands = []
    if hasattr(sys, "_MEIPASS"):
        cands.append(os.path.join(sys._MEIPASS, "GUIDE.md"))
    cands.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "GUIDE.md"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


class HelpDialog(QDialog):
    def __init__(self, parent=None, screen=None):
        super().__init__(parent)
        self.setWindowTitle(f"Aide — {APP_NAME}")
        self.setStyleSheet(HELP_CSS)
        v = QVBoxLayout(self)
        head = QHBoxLayout()
        t = QLabel("❓ Aide de TBI Pro")
        t.setObjectName("title")
        head.addWidget(t, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher dans l'aide (ex. : calibrage, post-it, vidéo)…")
        self.search.returnPressed.connect(self.find_next)
        head.addWidget(self.search, 2)
        b = QPushButton("🔍")
        b.setFixedWidth(60)
        b.clicked.connect(self.find_next)
        head.addWidget(b)
        close = QPushButton("✖ Fermer")
        close.setObjectName("cancel")
        close.clicked.connect(self.accept)
        head.addWidget(close)
        v.addLayout(head)
        self.tabs = QTabWidget()
        self.quick = QTextBrowser()
        self.quick.setMarkdown(QUICK_START)
        self.tabs.addTab(self.quick, "🚀 Démarrage rapide")
        self.full = QTextBrowser()
        self.full.setOpenExternalLinks(True)
        gp = guide_path()
        if gp:
            with open(gp, encoding="utf-8") as f:
                self.full.setMarkdown(f.read())
        else:
            self.full.setMarkdown(f"Guide introuvable. Consultez : {REPO_URL}")
        self.tabs.addTab(self.full, "📘 Guide complet")
        v.addWidget(self.tabs, 1)
        self.info = QLabel("Astuce : F1 ouvre cette aide depuis le panneau de contrôle.")
        self.info.setObjectName("info")
        v.addWidget(self.info)
        projected_dialog(self, screen, full=True)

    def find_next(self):
        q = self.search.text().strip()
        if not q:
            return
        view = self.tabs.currentWidget()
        if not view.find(q):
            cur = view.textCursor()                   # reprendre depuis le début
            cur.movePosition(cur.MoveOperation.Start)
            view.setTextCursor(cur)
            if not view.find(q):
                other = self.full if view is self.quick else self.quick
                self.tabs.setCurrentWidget(other)
                c2 = other.textCursor()
                c2.movePosition(c2.MoveOperation.Start)
                other.setTextCursor(c2)
                if not other.find(q):
                    self.info.setText(f"« {q} » introuvable dans l'aide.")
                    return
        self.info.setText(f"Résultat pour « {q} » — Entrée pour le suivant.")


class AboutDialog(QDialog):
    def __init__(self, parent=None, screen=None):
        super().__init__(parent)
        self.setWindowTitle(f"À propos — {APP_NAME}")
        self.setStyleSheet(HELP_CSS)
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        logo = QLabel()
        ico = resource_path("icon.ico")
        if os.path.exists(ico):
            logo.setPixmap(QPixmap(ico).scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        row.addWidget(logo)
        t = QLabel(f"{APP_NAME}\nversion {VERSION}")
        t.setObjectName("title")
        row.addWidget(t, 1)
        v.addLayout(row)
        txt = QTextBrowser()
        txt.setOpenExternalLinks(True)
        txt.setHtml(CREDITS.format(name=APP_NAME, version=VERSION, repo=REPO_URL))
        v.addWidget(txt, 1)
        row = QHBoxLayout()
        gh = QPushButton("🌐 Page du projet / mises à jour")
        gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        row.addWidget(gh)
        ok = QPushButton("OK")
        ok.setObjectName("ok")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        v.addLayout(row)
        projected_dialog(self, screen, size=(900, 700))
