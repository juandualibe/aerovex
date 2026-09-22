"""Ventana modal con visor WebEngine para desplegar el mapa satelital."""

import ctypes
import logging
import os
import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout

logger = logging.getLogger(__name__)


class VisorMapaDialog(QDialog):
    """Muestra el mapa HTML interactivo renderizado con WebEngine."""

    def __init__(self, ruta_mapa_html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AEROVEX | Mapa Satelital de Misión y Geolocalización")
        self.resize(1020, 700)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not os.path.exists(ruta_mapa_html):
            QMessageBox.critical(self, "Error", "No se encontró el archivo del mapa.")
            return

        self.web_view = QWebEngineView()

        config = self.web_view.settings()
        if config is not None:
            config.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            config.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            config.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )

        ruta_absoluta = os.path.abspath(ruta_mapa_html)
        self.web_view.load(QUrl.fromLocalFile(ruta_absoluta))
        layout.addWidget(self.web_view)

    def showEvent(self, a0: QShowEvent | None) -> None:
        """Se ejecuta al momento de mostrarse en pantalla para aplicar el tema nativo."""
        super().showEvent(a0)
        self._aplicar_tema_barra_windows()

    def _aplicar_tema_barra_windows(self) -> None:
        """Aplica color claro (#f8fafc) y texto oscuro a la barra de título de Windows 11."""
        if sys.platform != "win32":
            return

        try:
            hwnd = int(self.winId())
            dwmapi = getattr(ctypes, "windll", None)
            if dwmapi is None or not hasattr(dwmapi, "dwmapi"):
                return

            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (0 = claro)
            modo_claro = ctypes.c_int(0)
            dwmapi.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(modo_claro), ctypes.sizeof(modo_claro)
            )

            # DWMWA_CAPTION_COLOR = 35 (Formato 0x00BBGGRR: #f8fafc -> 0x00FCFAF8)
            color_fondo = ctypes.c_uint32(0x00FCFAF8)
            dwmapi.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(color_fondo), ctypes.sizeof(color_fondo)
            )

            # DWMWA_TEXT_COLOR = 36 (Formato 0x00BBGGRR: #0f172a -> 0x002A170F)
            color_texto = ctypes.c_uint32(0x002A170F)
            dwmapi.dwmapi.DwmSetWindowAttribute(
                hwnd, 36, ctypes.byref(color_texto), ctypes.sizeof(color_texto)
            )
        except (AttributeError, OSError) as e:
            logger.debug("No se pudo aplicar tema DWM a la barra de título: %s", e)