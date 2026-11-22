# -*- coding: utf-8 -*-
"""
Son des vidéos : micro (voix de l'enseignant) et sons de l'ordinateur (« loopback » WASAPI
sous Windows : vidéos, diaporamas sonores…), mélangés puis assemblés avec l'image par ffmpeg.
"""
import os
import subprocess
import sys
import threading
import time
import wave

import numpy as np

RATE = 48000
BLOCK = 1024


def _sc():
    try:
        import soundcard
        return soundcard
    except Exception:
        return None


def audio_available():
    """(micro disponible, sons de l'ordinateur disponibles, message)."""
    sc = _sc()
    if sc is None:
        return False, False, "Module « soundcard » indisponible"
    mic = spk = False
    try:
        mic = sc.default_microphone() is not None
    except Exception:
        pass
    try:
        spk = sc.default_speaker() is not None
    except Exception:
        pass
    return mic, spk, ""


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def run_ffmpeg(args, timeout=600):
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg introuvable")
    flags = 0x08000000 if sys.platform.startswith("win") else 0      # CREATE_NO_WINDOW : pas de console
    r = subprocess.run([exe, "-y", "-loglevel", "error"] + args, capture_output=True, timeout=timeout,
                       creationflags=flags)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "ignore")[-400:])


class _Track(threading.Thread):
    """Capture d'une source sonore dans un fil : liste de blocs (horodatés, pauses exclues)."""

    def __init__(self, get_device, owner):
        super().__init__(daemon=True)
        self.get_device, self.owner = get_device, owner
        self.blocks = []
        self.error = ""
        self.running = True

    def run(self):
        try:
            try:                                   # Windows : initialiser COM dans ce fil
                import ctypes
                ctypes.windll.ole32.CoInitializeEx(None, 0)
            except Exception:
                pass
            dev = self.get_device()
            with dev.recorder(samplerate=RATE, channels=2, blocksize=BLOCK) as rec:
                while self.running:
                    data = rec.record(numframes=BLOCK)
                    if not self.owner.paused:
                        if data.ndim == 1:
                            data = np.stack([data, data], axis=1)
                        self.blocks.append(data[:, :2].astype(np.float32))
        except Exception as e:
            self.error = str(e)

    def samples(self):
        return np.concatenate(self.blocks) if self.blocks else np.zeros((0, 2), np.float32)


class AudioRecorder:
    """Enregistre micro et/ou sons de l'ordinateur ; stop() écrit un WAV mélangé."""

    def __init__(self, mic=True, system=True, mic_gain=1.0, sys_gain=0.8):
        self.paused = False
        self.mic_gain, self.sys_gain = mic_gain, sys_gain
        self.tracks = []
        sc = _sc()
        if sc is None:
            return
        if mic:
            self.tracks.append(("mic", _Track(lambda: sc.default_microphone(), self)))
        if system:
            self.tracks.append(("sys", _Track(
                lambda: sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True), self)))

    def start(self):
        for _, t in self.tracks:
            t.start()

    def stop(self, wav_path):
        for _, t in self.tracks:
            t.running = False
        for _, t in self.tracks:
            t.join(timeout=3)
        parts = []
        errors = []
        for name, t in self.tracks:
            s = t.samples()
            if t.error:
                errors.append(f"{name}: {t.error}")
            if len(s):
                parts.append(s * (self.mic_gain if name == "mic" else self.sys_gain))
        if not parts:
            return None, "; ".join(errors) or "aucun son capté"
        n = max(len(p) for p in parts)
        mix = np.zeros((n, 2), np.float32)
        for p in parts:
            mix[:len(p)] += p
        peak = float(np.max(np.abs(mix))) or 1.0
        if peak > 0.98:                            # éviter la saturation du mélange
            mix *= 0.98 / peak
        pcm = (mix * 32767).astype("<i2")
        with wave.open(wav_path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        return wav_path, "; ".join(errors)


def mux(video_path, wav_path, out_path):
    """Assemble image + son en MP4 lisible partout (H.264 + AAC)."""
    args = ["-i", video_path]
    if wav_path:
        args += ["-i", wav_path]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if wav_path:
        args += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    args += ["-movflags", "+faststart", out_path]
    run_ffmpeg(args)


def trim(src, start_s, end_s, out_path):
    """Découpe en gardant le son."""
    run_ffmpeg(["-ss", f"{start_s:.3f}", "-i", src, "-t", f"{max(0.1, end_s - start_s):.3f}", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path])
