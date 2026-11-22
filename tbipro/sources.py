# -*- coding: utf-8 -*-
"""
Sources caméra.

PhoneSource  : le PC sert une page web sécurisée (HTTPS) ; le portable l'ouvre via un
               QR code, filme la projection, détecte lui-même les LED et n'envoie que
               les positions (très faible latence, aucune appli à installer).
WebcamSource : webcam USB, ou portable utilisé comme webcam (DroidCam, Iriun) ; la
               détection se fait sur le PC avec OpenCV.
"""
import asyncio
import base64
import datetime
import ipaddress
import json
import mimetypes
import os
import socket
import ssl
import sys
import threading
import time

import numpy as np

from .config import app_dir, resource_path
from . import handmodel, vision

# Le registre Windows associe parfois .js à text/plain : les navigateurs refuseraient les modules.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")


def decode_jpeg(data):
    import cv2
    arr = np.frombuffer(data, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


class BaseSource:
    kind = "base"

    def __init__(self):
        self._lock = threading.Lock()
        self._seq = 0
        self._blobs = []
        self._t = 0.0
        self._preview = None          # ("jpeg", bytes) ou ("bgr", ndarray)
        self._snapshot = None
        self._snap_wanted = False
        self.params = {"threshold": 225, "min_area": 2, "max_area": 400, "roi": None, "mode": "led"}
        self.fps = 0.0
        self._fps_n, self._fps_t = 0, time.time()

    # appelé par la source quand de nouveaux points sont disponibles
    def _push(self, blobs):
        with self._lock:
            self._blobs = blobs
            self._seq += 1
            self._t = time.time()
        self._fps_n += 1
        dt = time.time() - self._fps_t
        if dt >= 1.0:
            self.fps, self._fps_n, self._fps_t = self._fps_n / dt, 0, time.time()

    def latest(self):
        with self._lock:
            return self._seq, list(self._blobs), self._t

    def preview(self):
        with self._lock:
            return self._preview

    def request_snapshot(self):
        with self._lock:
            self._snapshot = None
            self._snap_wanted = True

    def get_snapshot(self):
        with self._lock:
            s = self._snapshot
            if s is not None:
                self._snapshot = None
            return s

    def set_params(self, **kw):
        self.params.update(kw)

    def connected(self):
        return time.time() - self._t < 1.0

    def start(self):
        pass

    def stop(self):
        pass


# ----------------------------------------------------------------------------
# Webcam / DroidCam / Iriun
# ----------------------------------------------------------------------------
class WebcamSource(BaseSource):
    kind = "webcam"

    def __init__(self, src="0"):
        super().__init__()
        self.src = src
        self.running = False
        self.error = ""

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def _loop(self):
        import cv2
        src = int(self.src) if str(self.src).isdigit() else self.src
        backend = cv2.CAP_DSHOW if (sys.platform.startswith("win") and isinstance(src, int)) else cv2.CAP_ANY
        cap = cv2.VideoCapture(src, backend)
        if not cap.isOpened():
            self.error = f"Caméra « {self.src} » introuvable"
            return
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)      # plus de pixels : main mieux détectée
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        last_prev = 0
        hand = None
        while self.running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue
            p = self.params
            if p.get("mode") == "doigt":
                if hand is None:
                    hand = self._hand_detector()
                blobs = hand.detect(frame, p["roi"], p.get("crop", True)) if hand else []
            else:
                blobs = vision.detect_blobs(frame, p["threshold"], p["min_area"], p["max_area"], p["roi"])
            self._push(blobs)
            now = time.time()
            with self._lock:
                if self._snap_wanted:
                    self._snapshot, self._snap_wanted = frame.copy(), False
                if now - last_prev > 0.1:
                    self._preview, last_prev = ("bgr", frame), now
        cap.release()

    def _hand_detector(self):
        path = handmodel.model_path()
        if not path:
            handmodel.ensure_async()
            return None
        try:
            return vision.HandDetector(path)
        except ImportError:
            self.error = "Mode doigt : le module « mediapipe » n'est pas installé"
        except Exception as e:
            self.error = f"Mode doigt indisponible : {e}"
        self.params["mode"] = "led"
        return None

    def status(self):
        if self.error:
            return self.error
        if handmodel.status():
            return handmodel.status()
        return f"Webcam {self.src} : {self.fps:.0f} img/s" if self.connected() else "En attente de la caméra…"


# ----------------------------------------------------------------------------
# Caméra infrarouge (webcam IR, webcam modifiée avec filtre passe-IR, caméra USB IR)
# ----------------------------------------------------------------------------
class IRCameraSource(WebcamSource):
    """
    Même branchement qu'une webcam, mais l'image est traitée en niveaux de gris
    avec soustraction du fond infrarouge. Toutes les LED IR ont la même « couleur » :
    les stylets sont distingués par le suivi (position), pas par la couleur.
    """
    kind = "ir"

    def __init__(self, src="0", exposure=None):
        super().__init__(src)
        self.exposure = exposure
        self.background = vision.IRBackground()

    def relearn_background(self):
        self.background.reset()

    def _loop(self):
        import cv2
        src = int(self.src) if str(self.src).isdigit() else self.src
        backend = cv2.CAP_DSHOW if (sys.platform.startswith("win") and isinstance(src, int)) else cv2.CAP_ANY
        cap = cv2.VideoCapture(src, backend)
        if not cap.isOpened():
            self.error = f"Caméra IR « {self.src} » introuvable"
            return
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self.exposure is not None:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            cap.set(cv2.CAP_PROP_EXPOSURE, float(self.exposure))
        last_prev = 0
        while self.running:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue
            p = self.params
            blobs = vision.detect_blobs_ir(frame, self.background, p["threshold"], p["min_area"],
                                           p["max_area"], p["roi"])
            self._push(blobs)
            now = time.time()
            with self._lock:
                if self._snap_wanted:
                    self._snapshot, self._snap_wanted = frame.copy(), False
                if now - last_prev > 0.1:
                    self._preview, last_prev = ("bgr", frame), now
        cap.release()

    def status(self):
        if self.error:
            return self.error
        return f"Caméra IR {self.src} : {self.fps:.0f} img/s" if self.connected() else "En attente de la caméra IR…"


# ----------------------------------------------------------------------------
# Portable via page web (QR code)
# ----------------------------------------------------------------------------
def lan_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips or ["127.0.0.1"]


def ensure_certificate(ips):
    """Certificat auto-signé (HTTPS est obligatoire pour accéder à la caméra du portable)."""
    d = app_dir()
    crt, key = os.path.join(d, "tbi.crt"), os.path.join(d, "tbi.key")
    meta = os.path.join(d, "tbi_cert_ips.json")
    try:
        if os.path.exists(crt) and set(json.load(open(meta))) >= set(ips):
            return crt, key
    except Exception:
        pass
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TBI Pro")])
    san = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(k.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(k, hashes.SHA256()))
    with open(crt, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key, "wb") as f:
        f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                serialization.NoEncryption()))
    json.dump(ips, open(meta, "w"))
    return crt, key


class PhoneSource(BaseSource):
    kind = "phone"

    def __init__(self, port=8443):
        super().__init__()
        self.port = port
        self.ips = lan_ips()
        self.loop = None
        self.clients = set()
        self.error = ""
        self.cam_info = ""

    @property
    def url(self):
        return f"https://{self.ips[0]}:{self.port}"

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)

    def set_params(self, **kw):
        if kw.get("mode") == "doigt" and not handmodel.model_path():
            handmodel.ensure_async(lambda _p: self._broadcast({"t": "cfg", **self._cfg_msg()}))
        super().set_params(**kw)
        self._broadcast({"t": "cfg", **self._cfg_msg()})

    def request_snapshot(self):
        super().request_snapshot()
        self._broadcast({"t": "snap"})

    def _cfg_msg(self):
        p = self.params
        return {"thr": p["threshold"], "minA": p["min_area"], "maxA": p["max_area"], "roi": p["roi"],
                "mode": p.get("mode", "led"), "model": bool(handmodel.model_path()), "crop": p.get("crop", True)}

    def _broadcast(self, msg):
        if not self.loop:
            return
        data = json.dumps(msg)

        async def send():
            for ws in list(self.clients):
                try:
                    await ws.send_str(data)
                except Exception:
                    pass
        asyncio.run_coroutine_threadsafe(send(), self.loop)

    def _run(self):
        try:
            from aiohttp import web, WSMsgType
        except ImportError:
            self.error = "Module aiohttp manquant"
            return
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        page = resource_path("phone", "index.html")

        async def index(request):
            return web.FileResponse(page, headers={"Cache-Control": "no-store"})

        async def model(request):
            path = handmodel.model_path()
            if not path:
                handmodel.ensure_async(lambda _p: self._broadcast({"t": "cfg", **self._cfg_msg()}))
                return web.Response(status=503, text="Modèle en cours de téléchargement sur le PC")
            return web.FileResponse(path)

        async def ws_handler(request):
            ws = web.WebSocketResponse(heartbeat=5, max_msg_size=8 * 1024 * 1024)
            await ws.prepare(request)
            self.clients.add(ws)
            await ws.send_str(json.dumps({"t": "cfg", **self._cfg_msg()}))
            try:
                async for msg in ws:
                    if msg.type != WSMsgType.TEXT:
                        continue
                    try:
                        m = json.loads(msg.data)
                    except ValueError:
                        continue
                    t = m.get("t")
                    if t == "b":
                        self._push([(b[0], b[1], b[2], b[3]) for b in m.get("b", [])])
                    elif t == "p":
                        img = base64.b64decode(m["img"].split(",", 1)[1])
                        with self._lock:
                            self._preview = ("jpeg", img)
                    elif t == "s":
                        frame = decode_jpeg(base64.b64decode(m["img"].split(",", 1)[1]))
                        with self._lock:
                            self._snapshot, self._snap_wanted = frame, False
                    elif t == "info":
                        self.cam_info = m.get("txt", "")
            finally:
                self.clients.discard(ws)
            return ws

        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_get("/ws", ws_handler)
        app.router.add_get("/mp/hand_landmarker.task", model)
        app.router.add_static("/mp/", resource_path("phone", "mp"))
        try:
            crt, key = ensure_certificate(self.ips)
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.load_cert_chain(crt, key)
            runner = web.AppRunner(app, access_log=None)
            self.loop.run_until_complete(runner.setup())
            self.loop.run_until_complete(web.TCPSite(runner, "0.0.0.0", self.port, ssl_context=ctx).start())
        except Exception as e:
            self.error = f"Serveur impossible à démarrer : {e}"
            return
        self.loop.run_forever()

    def status(self):
        if self.error:
            return self.error
        if handmodel.status():
            return handmodel.status()
        if not self.clients:
            return "Scannez le QR code avec le portable"
        if not self.connected():
            return "Portable connecté — caméra en attente"
        return f"Portable connecté : {self.fps:.0f} img/s {self.cam_info}"


# ----------------------------------------------------------------------------
# Registre des sources : pour ajouter un nouveau capteur plus tard (Wiimote,
# caméra réseau, capteur ToF…), écrire une classe dérivée de BaseSource et
# l'ajouter ici. Le reste du logiciel n'a pas à changer.
# ----------------------------------------------------------------------------
SOURCES = {
    "phone": ("Portable (QR code, sans appli)", lambda cfg: PhoneSource(int(cfg.get("port", 8443)))),
    "webcam": ("Webcam / DroidCam / Iriun", lambda cfg: WebcamSource(cfg.get("webcam", "0"))),
    "ir": ("Caméra infrarouge + stylet IR", lambda cfg: IRCameraSource(cfg.get("ir_camera", "0"), cfg.get("ir_exposure"))),
}


def make_source(cfg):
    kind = cfg.get("source", "phone")
    if kind not in SOURCES:
        kind = "phone"
    return SOURCES[kind][1](cfg)
