# -*- coding: utf-8 -*-
"""
Modèle de détection de la main (MediaPipe Hand Landmarker, ~7,5 Mo).
Inclus dans l'exécutable s'il a été ajouté à la construction ; sinon téléchargé
une seule fois au premier usage du mode « Doigt » puis gardé dans %APPDATA%\\TBIPro.
"""
import os
import threading
import urllib.request

from .config import app_dir, resource_path

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/1/hand_landmarker.task")
MODEL_NAME = "hand_landmarker.task"

_state = {"status": "", "busy": False}
_lock = threading.Lock()


def model_path():
    """Chemin du modèle s'il est disponible, sinon None."""
    for p in (resource_path("phone", "mp", MODEL_NAME), os.path.join(app_dir(), MODEL_NAME)):
        if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
            return p
    return None


def status():
    return _state["status"]


def ensure_async(on_ready=None):
    """Télécharge le modèle en arrière-plan s'il manque."""
    if model_path():
        if on_ready:
            on_ready(model_path())
        return
    with _lock:
        if _state["busy"]:
            return
        _state["busy"] = True

    def run():
        dst = os.path.join(app_dir(), MODEL_NAME)
        tmp = dst + ".part"
        try:
            _state["status"] = "Téléchargement du modèle de la main (7 Mo)…"
            urllib.request.urlretrieve(MODEL_URL, tmp)
            os.replace(tmp, dst)
            _state["status"] = ""
            if on_ready:
                on_ready(dst)
        except Exception as e:
            _state["status"] = f"Modèle de la main non téléchargé (connexion Internet ?) : {e}"
        finally:
            _state["busy"] = False

    threading.Thread(target=run, daemon=True).start()
