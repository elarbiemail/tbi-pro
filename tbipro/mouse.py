# -*- coding: utf-8 -*-
"""Pilotage de la souris du système (mode « Souris »)."""
import sys

from PySide6.QtGui import QCursor


class SystemMouse:
    def __init__(self):
        self._down = False
        self._user32 = None
        self._pynput = None
        if sys.platform.startswith("win"):
            import ctypes
            self._user32 = ctypes.windll.user32
        else:
            try:
                from pynput.mouse import Button, Controller
                self._pynput = (Controller(), Button.left)
            except Exception:
                pass

    def move(self, screen, x, y):
        """x, y : position logique dans l'écran projeté (Qt gère la mise à l'échelle)."""
        g = screen.geometry()
        QCursor.setPos(screen, int(g.x() + x), int(g.y() + y))

    def press(self):
        if self._down:
            return
        self._down = True
        if self._user32:
            self._user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
        elif self._pynput:
            self._pynput[0].press(self._pynput[1])

    def release(self):
        if not self._down:
            return
        self._down = False
        if self._user32:
            self._user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
        elif self._pynput:
            self._pynput[0].release(self._pynput[1])

    def click(self):
        self.press()
        self.release()
