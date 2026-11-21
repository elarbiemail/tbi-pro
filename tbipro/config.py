# -*- coding: utf-8 -*-
"""Réglages persistants de TBI Pro (fichier JSON dans le dossier utilisateur)."""
import json
import os
import sys

APP_NAME = "TBI Pro"
VERSION = "1.0.0"


def app_dir():
    base = os.environ.get("APPDATA") if sys.platform.startswith("win") else os.path.expanduser("~/.config")
    d = os.path.join(base or os.path.expanduser("~"), "TBIPro")
    os.makedirs(d, exist_ok=True)
    return d


def documents_dir():
    d = os.path.join(os.path.expanduser("~"), "Documents", "TBI Pro")
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(*parts):
    """Chemin d'une ressource, y compris dans l'exécutable PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if hasattr(sys, "_MEIPASS"):
        base = os.path.join(base, "tbipro")
    return os.path.join(base, *parts)


DEFAULTS = {
    "source": "phone",          # "phone" (QR code), "webcam" (webcam, DroidCam, Iriun) ou "ir" (caméra infrarouge)
    "webcam": "0",              # index ou URL pour la source webcam
    "ir_camera": "0",           # index ou URL de la caméra infrarouge
    "ir_exposure": None,        # exposition manuelle de la caméra IR (ex. -6), None = auto
    "port": 8443,
    "screen": "",               # nom de l'écran projeté ("" = écran secondaire s'il existe)
    "threshold": 225,
    "min_area": 2,
    "max_area": 400,
    "smoothing": 0.45,
    "on_frames": 2,
    "off_frames": 3,
    "pointer": "led",           # "led" (stylet à LED) ou "doigt" (index de la main)
    "finger_click": "pincer",   # mode doigt : "pincer" (pouce + index) ou "maintien" (doigt immobile)
    "color_pens": True,         # identifier les stylets par la couleur de leur LED
    "max_pens": 4,
    "laser": False,             # mode souris : clic par maintien au lieu de LED = clic
    "dwell_seconds": 1.0,
    "homography": None,         # caméra (coordonnées normalisées 0-1) → écran (pixels logiques)
    "calib_size": None,         # taille de l'écran lors du calibrage
    "roi": None,                # contour de la projection dans l'image (normalisé)
}


class Config(dict):
    def __init__(self):
        super().__init__(DEFAULTS)
        self.path = os.path.join(app_dir(), "config.json")
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.update(json.load(f))
        except FileNotFoundError:
            pass
        except Exception as e:
            print("Réglages illisibles, valeurs par défaut :", e)

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Impossible d'enregistrer les réglages :", e)
