# -*- coding: utf-8 -*-
"""
Bibliothèque d'images :
  • Pictogrammes intégrés (hors ligne) par catégories ;
  • Banques libres en ligne : ARASAAC (pictogrammes éducatifs, en français), Iconify (icônes
    couleur OpenMoji / Noto / Twemoji / Fluent), Openverse (photos et illustrations Creative
    Commons), Wikimedia Commons ;
  • Mes ressources (Documents/TBI Pro/Ressources) et fichier quelconque.
Un toucher sur une vignette insère l'image dans le tableau (crédit ajouté si la licence l'exige).
"""
import html
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QByteArray, QObject, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from ..config import documents_dir
from .keyboard import DIALOG_CSS, TextDialog, projected_dialog

UA = {"User-Agent": "TBIPro/1.0 (tableau interactif scolaire; contact: enseignant)"}
THUMB = 112

LIB_CSS = DIALOG_CSS + """
QToolButton { background:#f8fafc; border:2px solid #334155; border-radius:12px; }
QToolButton:pressed { border-color:#38bdf8; background:#e0f2fe; }
QPushButton#cat { min-height:44px; font-size:12pt; padding:4px 10px; }
QPushButton#cat[sel="true"] { background:#0369a1; }
QScrollBar:vertical { width:34px; background:#1e293b; }
QScrollBar::handle:vertical { background:#64748b; border-radius:8px; min-height:60px; }
QComboBox { background:#1e293b; padding:8px; font-size:13pt; border-radius:8px; }
QLabel#info { color:#94a3b8; font-size:10pt; }
"""

# (libellé, requête française, requête anglaise)
CATEGORIES = [
    ("🏫 École", "école", "school"), ("🐾 Animaux", "animal", "animal"), ("🧍 Corps", "corps", "body"),
    ("😀 Émotions", "émotion", "emotion"), ("🍎 Aliments", "aliment", "food"), ("🌳 Nature", "nature", "nature"),
    ("⛅ Météo", "météo", "weather"), ("🚗 Transports", "transport", "transport"), ("👩‍🔧 Métiers", "métier", "job"),
    ("🏠 Maison", "maison", "house"), ("⚽ Sport", "sport", "sport"), ("🎵 Musique", "musique", "music"),
    ("🔬 Sciences", "science", "science"), ("🌍 Géographie", "carte", "map"), ("🏛️ Histoire", "histoire", "history"),
    ("👨‍👩‍👧 Famille", "famille", "family"), ("👕 Vêtements", "vêtement", "clothes"), ("📚 Lecture", "livre", "book"),
    ("🪐 Espace", "planète", "planet"), ("🏰 Monuments", "monument", "monument"), ("🍇 Fruits", "fruit", "fruit"),
    ("🎻 Instruments", "instrument de musique", "musical instrument"), ("🛠️ Outils", "outil", "tool"),
    ("♻️ Écologie", "recyclage", "recycling"), ("🇲🇦 Maroc", "Maroc", "Morocco"), ("🧪 Chimie", "chimie", "chemistry"),
    ("➗ Maths", "mathématiques", "mathematics"),
]

EMOJI = {
    "École": "📚📖✏️🖊️🖍️📏📐✂️📎🗂️📝🎒🏫👩‍🏫👨‍🏫🧑‍🎓🔤🔢➕➖✖️➗🟰💡❓❗🔍🧮🗓️⏰🔔🏆🥇🎓🖥️💻📱🖨️",
    "Animaux": "🐶🐱🐭🐹🐰🦊🐻🐼🐨🐯🦁🐮🐷🐸🐵🐔🐧🐦🦆🦅🦉🐴🦄🐝🐛🦋🐌🐞🐢🐍🦎🐙🦀🐟🐬🐳🦈🐊🐘🦒🐪🐑🐐🦌",
    "Nature": "🌳🌲🌴🌵🌷🌹🌻🌼🍀🍁🍂🌾🌊🏔️⛰️🌋🏝️🏜️🌍🌎🌏🌙⭐🌟☀️🌈🔥💧❄️🪨🪵🌱🍄",
    "Météo": "☀️🌤️⛅🌥️☁️🌦️🌧️⛈️🌩️🌨️❄️☃️⛄🌬️💨🌪️🌫️🌈☔⚡🌡️",
    "Aliments": "🍎🍐🍊🍋🍌🍉🍇🍓🫐🍒🍑🥭🍍🥥🥝🍅🥕🌽🥔🥦🧅🧄🍞🥐🧀🥚🍗🥩🐟🍚🍝🍕🥗🍲🥛☕🍵🧃🍰🍪🫖",
    "Corps et émotions": "😀😃😄😁😆😊🙂😉😍🤩😎🤔😐😮😢😭😡😱😴🤒🤗👍👎👏🙌👋✋🤚👌✌️👂👃👀👁️👄🦷🦶🦵💪🧠❤️",
    "Personnes et métiers": "👶🧒👦👧🧑👨👩🧓👴👵👨‍⚕️👩‍⚕️👨‍🍳👩‍🌾👨‍🔧👩‍🔬👨‍🚀👩‍🚒👮👷💂🧑‍🎨🧑‍✈️🧑‍🏫🧑‍💻🤝👪",
    "Transports et lieux": "🚗🚕🚌🚎🚓🚑🚒🚚🚜🚲🛵🏍️🚂🚆🚇✈️🚁🚀⛵🚢⚓🏠🏡🏫🏥🏦🏪🏛️🕌⛪🏰🗼🌉🏟️🏙️🗺️🧭",
    "Sport, arts et loisirs": "⚽🏀🏈⚾🎾🏐🏉🏓🏸🥊🥋⛳🏊🚴🏃🧗🎨🖌️🎭🎬🎤🎧🎵🎶🎹🥁🎸🎻🎺📷🎲🧩♟️🪁",
    "Sciences et symboles": "🔬🔭🧪🧫🧬⚗️🧲⚙️🔧🔨🪛💡🔋🔌🌡️⚖️🧮📊📈📉📌📍✅❌⭕❗❓⚠️🚫♻️➡️⬅️⬆️⬇️↔️🔄🔢🕐",
    "Mains et gestes": "👍👎👌✌️🤞🤟🤘🤙👈👉👆👇☝️✋🤚🖐️🖖👋🤝🙏✍️💪👏🙌🫶🤲👐✊👊🫵",
    "Maths et flèches": "➕➖✖️➗🟰♾️💯🔢#️⃣*️⃣0️⃣1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣🔟⬆️↗️➡️↘️⬇️↙️⬅️↖️↕️↔️↩️↪️⤴️⤵️🔃🔄🔺🔻🔷🔶🔵🟢🟡🟠🔴🟣⬛⬜",
    "Objets du quotidien": "⌚📱💻⌨️🖱️🖨️📷📺📻⏰⏳💡🔦🕯️🧹🧺🧻🧼🪥🧴🛏️🛋️🪑🚪🪟🔑🔒🧰🪜🧲✉️📦🎁🛒💰💳",
    "Fêtes et calendrier": "🎉🎊🎈🎂🎁🎆🎇✨🕌🌙⭐🪔🏮🎄🎃🎓🏆🥇📅🗓️⏰☀️🌅🌄🌃🌌",
    "Plantes et fleurs": "🌱🌿☘️🍀🎍🪴🌵🌴🌳🌲🍁🍂🍃🌾🌷🌹🥀🌺🌸🌼🌻💐🪻🪷🍄🌰",
    "Vêtements": "👕👖👗👔🧥🥼🦺👘🥻🩱🩳👙🧣🧤🧦👟👞👠👡👢🥾🧢👒🎩🎓👑💍👓🕶️🎒👜",
}

# Drapeaux (code ISO → nom) : images libres flagcdn.com (domaine public)
FLAGS = ("ma:Maroc|dz:Algérie|tn:Tunisie|ly:Libye|eg:Égypte|mr:Mauritanie|sn:Sénégal|ml:Mali|ne:Niger|td:Tchad|"
         "sd:Soudan|ss:Soudan du Sud|et:Éthiopie|so:Somalie|dj:Djibouti|er:Érythrée|ke:Kenya|tz:Tanzanie|ug:Ouganda|"
         "rw:Rwanda|bi:Burundi|cd:RD Congo|cg:Congo|ga:Gabon|cm:Cameroun|ng:Nigeria|gh:Ghana|ci:Côte d'Ivoire|"
         "bf:Burkina Faso|gn:Guinée|gw:Guinée-Bissau|sl:Sierra Leone|lr:Liberia|tg:Togo|bj:Bénin|cf:Centrafrique|"
         "gq:Guinée équatoriale|ao:Angola|zm:Zambie|zw:Zimbabwe|mw:Malawi|mz:Mozambique|mg:Madagascar|"
         "za:Afrique du Sud|na:Namibie|bw:Botswana|ls:Lesotho|sz:Eswatini|cv:Cap-Vert|km:Comores|mu:Maurice|"
         "sc:Seychelles|eh:Sahara occidental|sa:Arabie saoudite|ae:Émirats arabes unis|qa:Qatar|kw:Koweït|"
         "bh:Bahreïn|om:Oman|ye:Yémen|jo:Jordanie|ps:Palestine|lb:Liban|sy:Syrie|iq:Irak|ir:Iran|tr:Turquie|"
         "fr:France|be:Belgique|ch:Suisse|lu:Luxembourg|mc:Monaco|es:Espagne|pt:Portugal|it:Italie|de:Allemagne|"
         "at:Autriche|nl:Pays-Bas|gb:Royaume-Uni|ie:Irlande|dk:Danemark|se:Suède|no:Norvège|fi:Finlande|is:Islande|"
         "pl:Pologne|cz:Tchéquie|sk:Slovaquie|hu:Hongrie|ro:Roumanie|bg:Bulgarie|gr:Grèce|hr:Croatie|si:Slovénie|"
         "rs:Serbie|ba:Bosnie-Herzégovine|al:Albanie|mk:Macédoine du Nord|me:Monténégro|ua:Ukraine|ru:Russie|"
         "by:Biélorussie|lt:Lituanie|lv:Lettonie|ee:Estonie|md:Moldavie|mt:Malte|cy:Chypre|us:États-Unis|ca:Canada|"
         "mx:Mexique|br:Brésil|ar:Argentine|cl:Chili|co:Colombie|pe:Pérou|ve:Venezuela|uy:Uruguay|py:Paraguay|"
         "bo:Bolivie|ec:Équateur|cu:Cuba|ht:Haïti|do:République dominicaine|jm:Jamaïque|cn:Chine|jp:Japon|"
         "kr:Corée du Sud|kp:Corée du Nord|in:Inde|pk:Pakistan|bd:Bangladesh|af:Afghanistan|id:Indonésie|"
         "my:Malaisie|sg:Singapour|th:Thaïlande|vn:Viêt Nam|ph:Philippines|au:Australie|nz:Nouvelle-Zélande|"
         "kz:Kazakhstan|uz:Ouzbékistan|mn:Mongolie|np:Népal|lk:Sri Lanka|il:Israël|eu:Union européenne|un:ONU")


def emoji_image(ch, size=256):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    f = QFont("Segoe UI Emoji")
    f.setPixelSize(int(size * 0.78))
    p.setFont(f)
    p.drawText(img.rect(), Qt.AlignCenter, ch)
    p.end()
    return img


def split_emoji(s):
    """Découpe une chaîne d'emoji en caractères visibles (gère ZWJ et sélecteurs de variante)."""
    out, cur = [], ""
    for ch in s:
        if cur and ch not in ("‍", "️") and not cur.endswith("‍") and not (0x1F3FB <= ord(ch) <= 0x1F3FF):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip(htmltext):
    return html.unescape(re.sub(r"<[^>]+>", "", htmltext or "")).strip()


def image_from_bytes(data, svg=False, size=512):
    if svg:
        from PySide6.QtSvg import QSvgRenderer
        r = QSvgRenderer(QByteArray(data))
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        r.render(p)
        p.end()
        return img
    img = QImage()
    img.loadFromData(QByteArray(data))
    if not img.isNull() and max(img.width(), img.height()) > 1600:
        img = img.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return img


# ----------------------------------------------------------------------------
# Banques en ligne : chaque fonction renvoie une liste de résultats
#   {"thumb": url, "full": url, "svg": bool, "credit": texte}
# ----------------------------------------------------------------------------
def search_arasaac(q_fr, q_en):
    data = json.loads(_get("https://api.arasaac.org/v1/pictograms/fr/search/" + urllib.parse.quote(q_fr)))
    out = []
    for it in data[:80]:
        i = it["_id"]
        base = f"https://static.arasaac.org/pictograms/{i}/{i}"
        out.append({"thumb": base + "_300.png", "full": base + "_500.png", "svg": False,
                    "credit": "Pictogramme ARASAAC (S. Palao), CC BY-NC-SA"})
    return out


ICON_CREDITS = {"openmoji": "OpenMoji, CC BY-SA 4.0", "twemoji": "Twemoji, CC BY 4.0", "noto": "", "fluent-emoji-flat": ""}


def search_iconify(q_fr, q_en):
    url = ("https://api.iconify.design/search?limit=96&prefixes=noto,openmoji,fluent-emoji-flat,twemoji&query="
           + urllib.parse.quote(q_en or q_fr))
    data = json.loads(_get(url))
    out = []
    for name in data.get("icons", []):
        prefix, icon = name.split(":", 1)
        u = f"https://api.iconify.design/{prefix}/{icon}.svg?height=256"
        out.append({"thumb": u, "full": u, "svg": True, "credit": ICON_CREDITS.get(prefix, "")})
    return out


def search_openverse(q_fr, q_en, category=""):
    params = {"q": q_en or q_fr, "page_size": 40, "license": "cc0,pdm,by,by-sa", "mature": "false"}
    if category:
        params["category"] = category
    data = json.loads(_get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)))
    out = []
    for it in data.get("results", []):
        lic = (it.get("license") or "").lower()
        if lic in ("cc0", "pdm"):
            credit = ""
        else:
            credit = f"{(it.get('creator') or 'Auteur inconnu')[:40]} — CC {lic.upper()} {it.get('license_version') or ''}".strip()
        out.append({"thumb": it.get("thumbnail") or it.get("url"), "full": it.get("url"), "svg": False, "credit": credit})
    return out


def search_openverse_illus(q_fr, q_en):
    return search_openverse(q_fr, q_en, "illustration")


def search_openverse_photo(q_fr, q_en):
    return search_openverse(q_fr, q_en, "photograph")


def search_wikimedia(q_fr, q_en):
    params = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 40,
              "gsrsearch": f"{q_fr} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|extmetadata",
              "iiurlwidth": 320}
    data = json.loads(_get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)))
    out = []
    for pg in sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0)):
        ii = (pg.get("imageinfo") or [{}])[0]
        thumb = ii.get("thumburl")
        if not thumb:
            continue
        md = ii.get("extmetadata", {})
        artist = _strip(md.get("Artist", {}).get("value", ""))[:40]
        lic = _strip(md.get("LicenseShortName", {}).get("value", ""))
        full = thumb.replace("/320px-", "/1200px-") if "/320px-" in thumb else ii.get("url")
        credit = "" if lic.lower() in ("public domain", "cc0", "domaine public") else f"{artist or 'Wikimedia Commons'} — {lic}"
        out.append({"thumb": thumb, "full": full, "svg": False, "credit": credit})
    return out


def search_flags(q_fr, q_en):
    import unicodedata

    def norm(t):
        return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    q = norm(q_fr or "")
    out = []
    for pair in FLAGS.split("|"):
        code, name = pair.split(":", 1)
        if not q or q in norm(name) or q in ("drapeau", "drapeaux", "pays", "monde", "flag") or len(q) < 2:
            out.append({"thumb": f"https://flagcdn.com/w160/{code}.png", "full": f"https://flagcdn.com/w640/{code}.png",
                        "svg": False, "credit": "", "label": name})
    return out


def search_met(q_fr, q_en):
    """Œuvres d'art du domaine public (Metropolitan Museum of Art, licence CC0)."""
    ids = json.loads(_get("https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&isPublicDomain=true&q="
                          + urllib.parse.quote(q_en or q_fr))).get("objectIDs") or []
    out = []
    lock = threading.Lock()

    def one(i):
        try:
            o = json.loads(_get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{i}", 10))
            if o.get("isPublicDomain") and o.get("primaryImageSmall"):
                with lock:
                    out.append({"thumb": o["primaryImageSmall"], "full": o.get("primaryImage") or o["primaryImageSmall"],
                                "svg": False, "credit": "", "label": (o.get("title") or "")[:60]})
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, ids[:36]))
    return out


def search_icons_simple(q_fr, q_en):
    url = ("https://api.iconify.design/search?limit=120&prefixes=mdi,tabler,ph,material-symbols,carbon&query="
           + urllib.parse.quote(q_en or q_fr))
    data = json.loads(_get(url))
    out = []
    for name in data.get("icons", []):
        prefix, icon = name.split(":", 1)
        u = f"https://api.iconify.design/{prefix}/{icon}.svg?height=256&color=%230f172a"
        out.append({"thumb": u, "full": u, "svg": True, "credit": ""})
    return out


def search_maps(q_fr, q_en):
    return search_wikimedia(f"{q_fr} carte map", q_en)


PROVIDERS = [
    ("Pictogrammes ARASAAC (français)", search_arasaac),
    ("Icônes couleur (OpenMoji, Noto…)", search_iconify),
    ("Illustrations libres (Openverse)", search_openverse_illus),
    ("Photos libres (Openverse)", search_openverse_photo),
    ("Wikimedia Commons", search_wikimedia),
    ("Cartes et schémas (Wikimedia)", search_maps),
    ("Œuvres d'art — domaine public (Met Museum)", search_met),
    ("Icônes simples (Material, Tabler…)", search_icons_simple),
    ("Drapeaux du monde", search_flags),
]


class _Bridge(QObject):
    results = Signal(int, object, str)        # génération, liste, erreur
    thumb = Signal(int, int, object)          # génération, index, octets
    full = Signal(object, object, str)        # octets, résultat, erreur


# ----------------------------------------------------------------------------
class LibraryDialog(QDialog):
    def __init__(self, canvas, parent=None, screen=None):
        super().__init__(parent)
        self.canvas = canvas
        self.setWindowTitle("Bibliothèque d'images")
        self.setStyleSheet(LIB_CSS)
        self.pool = ThreadPoolExecutor(max_workers=6)
        self.bridge = _Bridge()
        self.bridge.results.connect(self._on_results)
        self.bridge.thumb.connect(self._on_thumb)
        self.bridge.full.connect(self._on_full)
        self.gen = 0
        self.results = []
        self.buttons = []
        projected_dialog(self, screen, full=True)      # taille connue avant de remplir les grilles

        lay = QVBoxLayout(self)
        head = QHBoxLayout()
        t = QLabel("🖼️ Bibliothèque d'images")
        t.setObjectName("title")
        head.addWidget(t, 1)
        close = QPushButton("✖ Fermer")
        close.setObjectName("cancel")
        close.setFixedWidth(160)
        close.clicked.connect(self.accept)
        head.addWidget(close)
        lay.addLayout(head)

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self._tab_emoji(), "Pictogrammes (hors ligne)")
        self.tabs.addTab(self._tab_online(), "🌐 Banques libres en ligne")
        self.tabs.addTab(self._tab_mine(), "📁 Mes ressources")
        self.info = QLabel("Touchez une image pour l'insérer dans le tableau, puis déplacez-la avec l'outil ✋.")
        self.info.setObjectName("info")
        lay.addWidget(self.info)

    # -------------------------------------------------------------- grilles
    def _grid_area(self):
        area = QScrollArea()
        area.setWidgetResizable(True)
        w = QWidget()
        g = QGridLayout(w)
        g.setSpacing(8)
        g.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        area.setWidget(w)
        return area, g

    def _cols(self):
        return max(4, (self.width() - 110) // (THUMB + 16))

    def _tile(self, icon=None, tip=""):
        b = QToolButton()
        b.setFixedSize(THUMB + 8, THUMB + 8)
        b.setIconSize(QSize(THUMB - 8, THUMB - 8))
        b.setFocusPolicy(Qt.NoFocus)
        b.setToolTip(tip)
        if icon is not None:
            b.setIcon(icon)
        return b

    # -------------------------------------------------------------- pictogrammes intégrés
    def _tab_emoji(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.emoji_cat = QComboBox()
        self.emoji_cat.addItems(list(EMOJI))
        v.addWidget(self.emoji_cat)
        area, self.emoji_grid = self._grid_area()
        v.addWidget(area, 1)
        self.emoji_cat.currentTextChanged.connect(self._fill_emoji)
        self._fill_emoji(self.emoji_cat.currentText())
        return w

    def _fill_emoji(self, cat):
        g = self.emoji_grid
        while g.count():
            g.takeAt(0).widget().deleteLater()
        cols = self._cols()
        for i, ch in enumerate(split_emoji(EMOJI[cat])):
            img = emoji_image(ch, 128)
            b = self._tile(QIcon(QPixmap.fromImage(img)))
            b.clicked.connect(lambda _=False, ch=ch: self._insert(emoji_image(ch, 384), ""))
            g.addWidget(b, i // cols, i % cols)

    # -------------------------------------------------------------- en ligne
    def _tab_online(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.provider = QComboBox()
        for name, _ in PROVIDERS:
            self.provider.addItem(name)
        row.addWidget(self.provider, 2)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher (ex. : volcan, cheval, fraction…)")
        self.search.returnPressed.connect(lambda: self.run_search(self.search.text(), self.search.text()))
        row.addWidget(self.search, 3)
        kb = QPushButton("⌨️")
        kb.setFixedWidth(64)
        kb.clicked.connect(self._keyboard_search)
        row.addWidget(kb)
        go = QPushButton("🔍 Chercher")
        go.setObjectName("ok")
        go.clicked.connect(lambda: self.run_search(self.search.text(), self.search.text()))
        row.addWidget(go)
        v.addLayout(row)
        cats = QGridLayout()
        cats.setSpacing(6)
        self.cat_btns = []
        for i, (label, fr, en) in enumerate(CATEGORIES):
            b = QPushButton(label)
            b.setObjectName("cat")
            b.clicked.connect(lambda _=False, fr=fr, en=en, b=b: self._cat(b, fr, en))
            self.cat_btns.append(b)
            cats.addWidget(b, i // 9, i % 9)
        flags = QPushButton("🏳️ Tous les drapeaux")
        flags.setObjectName("cat")
        flags.clicked.connect(lambda: (self.provider.setCurrentIndex(len(PROVIDERS) - 1), self.run_search("drapeaux", "flags")))
        cats.addWidget(flags, (len(CATEGORIES)) // 9, len(CATEGORIES) % 9)
        v.addLayout(cats)
        self.online_status = QLabel("Choisissez une banque et une catégorie, ou tapez un mot.")
        self.online_status.setObjectName("info")
        v.addWidget(self.online_status)
        area, self.online_grid = self._grid_area()
        v.addWidget(area, 1)
        self.provider.currentIndexChanged.connect(lambda _: self._last and self.run_search(*self._last))
        self._last = None
        return w

    def _keyboard_search(self):
        d = TextDialog("Rechercher une image", self.search.text(), self, self.screen())
        if d.exec():
            self.search.setText(d.text())
            self.run_search(d.text(), d.text())

    def _cat(self, btn, fr, en):
        for b in self.cat_btns:
            b.setProperty("sel", b is btn)
            b.style().unpolish(b)
            b.style().polish(b)
        self.run_search(fr, en)

    def run_search(self, q_fr, q_en):
        q_fr, q_en = q_fr.strip(), q_en.strip()
        if not q_fr:
            return
        self._last = (q_fr, q_en)
        self.gen += 1
        gen = self.gen
        name, fn = PROVIDERS[self.provider.currentIndex()]
        self.online_status.setText(f"Recherche « {q_fr} » dans {name}…")
        g = self.online_grid
        while g.count():
            g.takeAt(0).widget().deleteLater()
        self.buttons = []

        def job():
            try:
                self.bridge.results.emit(gen, fn(q_fr, q_en), "")
            except Exception as e:
                self.bridge.results.emit(gen, [], str(e))
        self.pool.submit(job)

    def _on_results(self, gen, results, err):
        if gen != self.gen:
            return
        if err:
            self.online_status.setText(f"Connexion impossible ({err[:80]}). Vérifiez Internet sur le PC.")
            return
        self.results = results
        self.online_status.setText(f"{len(results)} résultat(s). Touchez une image pour l'insérer."
                                   if results else "Aucun résultat : essayez un autre mot ou une autre banque.")
        cols = self._cols()
        for i, r in enumerate(results):
            b = self._tile(tip=r.get("label") or r["credit"])
            b.setText("…")
            b.clicked.connect(lambda _=False, r=r: self._download_full(r))
            self.online_grid.addWidget(b, i // cols, i % cols)
            self.buttons.append(b)

            def tj(i=i, r=r):
                try:
                    self.bridge.thumb.emit(gen, i, _get(r["thumb"]))
                except Exception:
                    pass
            self.pool.submit(tj)

    def _on_thumb(self, gen, i, data):
        if gen != self.gen or i >= len(self.buttons):
            return
        img = image_from_bytes(data, self.results[i]["svg"], 160)
        if not img.isNull():
            self.buttons[i].setText("")
            self.buttons[i].setIcon(QIcon(QPixmap.fromImage(img)))

    def _download_full(self, r):
        self.info.setText("Téléchargement de l'image…")

        def job():
            try:
                self.bridge.full.emit(_get(r["full"], 30), r, "")
            except Exception as e:
                self.bridge.full.emit(None, r, str(e))
        self.pool.submit(job)

    def _on_full(self, data, r, err):
        if err or not data:
            self.info.setText(f"Téléchargement impossible : {err[:80]}")
            return
        self._insert(image_from_bytes(data, r["svg"], 512), r["credit"])

    # -------------------------------------------------------------- mes ressources
    def _tab_mine(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.mine_dir = os.path.join(documents_dir(), "Ressources")
        os.makedirs(self.mine_dir, exist_ok=True)
        row = QHBoxLayout()
        lbl = QLabel(f"Déposez vos images dans : {self.mine_dir}")
        lbl.setObjectName("info")
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)
        rf = QPushButton("🔄 Actualiser")
        rf.clicked.connect(self._fill_mine)
        row.addWidget(rf)
        fb = QPushButton("📂 Autre fichier…")
        fb.clicked.connect(self._pick_file)
        row.addWidget(fb)
        v.addLayout(row)
        area, self.mine_grid = self._grid_area()
        v.addWidget(area, 1)
        self._fill_mine()
        return w

    def _fill_mine(self):
        g = self.mine_grid
        while g.count():
            g.takeAt(0).widget().deleteLater()
        files = []
        for root, _, names in os.walk(self.mine_dir):
            for n in sorted(names):
                if n.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg")):
                    files.append(os.path.join(root, n))
        for i, f in enumerate(files[:400]):
            b = self._tile(QIcon(f), os.path.basename(f))
            b.clicked.connect(lambda _=False, f=f: self._insert_file(f))
            g.addWidget(b, i // self._cols(), i % self._cols())

    def _insert_file(self, path):
        with open(path, "rb") as fh:
            data = fh.read()
        self._insert(image_from_bytes(data, path.lower().endswith(".svg"), 512), "")

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Insérer une image", os.path.expanduser("~"),
                                              "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.svg)",
                                              options=QFileDialog.Option.DontUseNativeDialog)
        if path:
            self._insert_file(path)

    # --------------------------------------------------------------
    def _insert(self, img, credit):
        if img is None or img.isNull():
            self.info.setText("Image illisible.")
            return
        self.canvas.insert_qimage(img, credit)
        self.info.setText("✅ Image insérée. Insérez-en d'autres, ou fermez la bibliothèque.")

    def done(self, r):
        self.gen += 1
        self.pool.shutdown(wait=False, cancel_futures=True)
        super().done(r)
