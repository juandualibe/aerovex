"""Ventana modal para consultar el historial de vuelos y re-exportar informes."""

import ctypes
import logging
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.database.db_manager import DatabaseManager
from app.gui.map_dialog import VisorMapaDialog
from app.reports.generador_mapa import GeneradorMapa
from app.reports.generador_reportes import GeneradorReportes

logger = logging.getLogger(__name__)


class HistorialDialog(QDialog):
    """Interfaz para auditar vuelos anteriores, regenerar mapas y exportar reportes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AEROVEX | Historial de Misiones y Vuelos Registrados")
        self.resize(1080, 640)

        # Habilita botones de minimizar, maximizar y cerrar estándar
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self.db = DatabaseManager()
        self.vuelos_cache = []
        self.vuelo_seleccionado = None
        self.fotos_vuelo_seleccionado = []

        self._inicializar_ui()
        self._cargar_vuelos()

    def showEvent(self, a0: QShowEvent | None) -> None:
        """Se ejecuta al mostrarse en pantalla para sincronizar el tema de la ventana."""
        super().showEvent(a0)
        self._aplicar_tema_barra_windows()

    def _aplicar_tema_barra_windows(self) -> None:
        """Aplica color claro (#f8fafc) y texto oscuro a la barra de título en Windows 11."""
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

            # DWMWA_CAPTION_COLOR = 35 (#f8fafc -> 0x00FCFAF8)
            color_fondo = ctypes.c_uint32(0x00FCFAF8)
            dwmapi.dwmapi.DwmSetWindowAttribute(
                hwnd, 35, ctypes.byref(color_fondo), ctypes.sizeof(color_fondo)
            )

            # DWMWA_TEXT_COLOR = 36 (#0f172a -> 0x002A170F)
            color_texto = ctypes.c_uint32(0x002A170F)
            dwmapi.dwmapi.DwmSetWindowAttribute(
                hwnd, 36, ctypes.byref(color_texto), ctypes.sizeof(color_texto)
            )
        except (AttributeError, OSError) as e:
            logger.debug("No se pudo aplicar tema DWM al diálogo de historial: %s", e)

    def _inicializar_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setSpacing(8)
        layout_principal.setContentsMargins(14, 14, 14, 14)

        # 1. Cabecera fija de títulos (alineada, fuera del splitter)
        layout_titulos = QHBoxLayout()
        self.lbl_vuelos = QLabel("Vuelos Registrados:")
        self.lbl_vuelos.setStyleSheet("color: #0f172a; font-weight: bold; font-size: 12px;")

        self.lbl_detalle_titulo = QLabel("Desglose de Capturas (Seleccione un vuelo):")
        self.lbl_detalle_titulo.setStyleSheet("color: #475569; font-weight: bold; font-size: 12px;")

        layout_titulos.addWidget(self.lbl_vuelos, stretch=5)
        layout_titulos.addWidget(self.lbl_detalle_titulo, stretch=5)
        layout_principal.addLayout(layout_titulos)

        # 2. Divisor que contiene únicamente las dos tablas
        self.divisor = QSplitter(Qt.Orientation.Horizontal)

        # Tabla de vuelos
        self.tabla_vuelos = QTableWidget()
        self.tabla_vuelos.setColumnCount(4)
        self.tabla_vuelos.setHorizontalHeaderLabels(["ID", "Fecha / Hora", "Potrero", "Cabezas"])
        self.tabla_vuelos.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_vuelos.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_vuelos.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabla_vuelos.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_vuelos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_vuelos.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_vuelos.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_vuelos.cellClicked.connect(self._al_seleccionar_vuelo)
        self.divisor.addWidget(self.tabla_vuelos)

        # Tabla de fotos del vuelo
        self.tabla_fotos = QTableWidget()
        self.tabla_fotos.setColumnCount(4)
        self.tabla_fotos.setHorizontalHeaderLabels(["Archivo", "Cabezas", "GPS Lat/Lon", "Altitud"])
        self.tabla_fotos.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabla_fotos.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_fotos.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_fotos.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla_fotos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_fotos.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.divisor.addWidget(self.tabla_fotos)

        self.divisor.setSizes([520, 520])
        layout_principal.addWidget(self.divisor, stretch=1)

        # 3. Barra inferior de acciones
        layout_acciones = QHBoxLayout()

        self.btn_ver_mapa = QPushButton("Visualizar Mapa Satelital")
        self.btn_ver_mapa.setFixedHeight(36)
        self.btn_ver_mapa.setEnabled(False)
        self.btn_ver_mapa.clicked.connect(self._abrir_mapa_historico)

        self.btn_exportar_excel = QPushButton("Exportar XLSX")
        self.btn_exportar_excel.setFixedHeight(36)
        self.btn_exportar_excel.setEnabled(False)
        self.btn_exportar_excel.clicked.connect(self._exportar_excel)

        self.btn_exportar_pdf = QPushButton("Generar Informe PDF")
        self.btn_exportar_pdf.setFixedHeight(36)
        self.btn_exportar_pdf.setEnabled(False)
        self.btn_exportar_pdf.clicked.connect(self._exportar_pdf)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setFixedHeight(36)
        btn_cerrar.clicked.connect(self.accept)

        layout_acciones.addWidget(self.btn_ver_mapa)
        layout_acciones.addWidget(self.btn_exportar_excel)
        layout_acciones.addWidget(self.btn_exportar_pdf)
        layout_acciones.addStretch()
        layout_acciones.addWidget(btn_cerrar)

        layout_principal.addLayout(layout_acciones)
        self._aplicar_estilo()

    def _aplicar_estilo(self):
        self.setStyleSheet(
            """
            QDialog { 
                background-color: #f8fafc; 
            }
            QLabel { 
                color: #0f172a; 
                font-family: 'Segoe UI', sans-serif; 
            }
            
            /* Divisor sutil y limpio */
            QSplitter::handle {
                background-color: #cbd5e1;
            }
            QSplitter::handle:horizontal {
                width: 1px;
            }

            /* Tablas */
            QTableWidget {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                gridline-color: #f1f5f9;
                font-size: 11px;
            }
            QTableWidget::item:selected {
                background-color: #2563eb;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #f1f5f9;
                color: #334155;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #cbd5e1;
                border-right: 1px solid #e2e8f0;
                padding: 5px;
            }
            QTableCornerButton::section {
                background-color: #f1f5f9;
                border: none;
                border-bottom: 1px solid #cbd5e1;
                border-right: 1px solid #cbd5e1;
            }

            /* Botones */
            QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
            QPushButton:disabled {
                background-color: #f8fafc;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
            """
        )

    def _cargar_vuelos(self):
        self.tabla_vuelos.setRowCount(0)
        self.vuelos_cache = self.db.obtener_vuelos_historial()

        for fila_idx, v in enumerate(self.vuelos_cache):
            self.tabla_vuelos.insertRow(fila_idx)

            item_id = QTableWidgetItem(str(v["id"]))
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_fecha = QTableWidgetItem(v["fecha_mision"])
            item_potrero = QTableWidgetItem(f"{v['potrero_nombre']} ({v['superficie_ha']} Ha)")
            item_total = QTableWidgetItem(str(v["total_cabezas"]))
            item_total.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tabla_vuelos.setItem(fila_idx, 0, item_id)
            self.tabla_vuelos.setItem(fila_idx, 1, item_fecha)
            self.tabla_vuelos.setItem(fila_idx, 2, item_potrero)
            self.tabla_vuelos.setItem(fila_idx, 3, item_total)

    def _al_seleccionar_vuelo(self, fila, _columna):
        if fila < 0 or fila >= len(self.vuelos_cache):
            return

        self.vuelo_seleccionado = self.vuelos_cache[fila]
        vuelo_id = self.vuelo_seleccionado["id"]
        self.fotos_vuelo_seleccionado = self.db.obtener_detalle_vuelo(vuelo_id)

        self.lbl_detalle_titulo.setText(
            f"Capturas Vuelo #{vuelo_id} - Potrero: {self.vuelo_seleccionado['potrero_nombre']}"
        )

        self.tabla_fotos.setRowCount(0)
        tiene_gps = False
        for f_idx, foto in enumerate(self.fotos_vuelo_seleccionado):
            self.tabla_fotos.insertRow(f_idx)

            coords = "Sin GPS"
            if foto.get("lat") is not None and foto.get("lon") is not None:
                coords = f"{foto['lat']:.4f}, {foto['lon']:.4f}"
                tiene_gps = True

            alt = f"{foto['alt']} m" if foto.get("alt") is not None else "N/D"

            item_archivo = QTableWidgetItem(foto["archivo"])
            item_cant = QTableWidgetItem(str(foto["cantidad"]))
            item_cant.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_gps = QTableWidgetItem(coords)
            item_alt = QTableWidgetItem(alt)
            item_alt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.tabla_fotos.setItem(f_idx, 0, item_archivo)
            self.tabla_fotos.setItem(f_idx, 1, item_cant)
            self.tabla_fotos.setItem(f_idx, 2, item_gps)
            self.tabla_fotos.setItem(f_idx, 3, item_alt)

        self.btn_exportar_excel.setEnabled(True)
        self.btn_exportar_pdf.setEnabled(True)
        self.btn_ver_mapa.setEnabled(tiene_gps)

    def _obtener_datos_mision_formateados(self) -> dict:
        return {
            "potrero_nombre": self.vuelo_seleccionado["potrero_nombre"],
            "superficie_ha": self.vuelo_seleccionado["superficie_ha"],
            "total_cabezas": self.vuelo_seleccionado["total_cabezas"],
            "fecha": self.vuelo_seleccionado["fecha_mision"],
            "fotos": self.fotos_vuelo_seleccionado,
        }

    def _abrir_mapa_historico(self):
        if not self.vuelo_seleccionado:
            return

        carpeta_base = self.vuelo_seleccionado.get("ruta_carpeta") or os.getcwd()
        ruta_mapa = os.path.join(carpeta_base, "procesadas", "mapa_vuelo_historico.html")

        ruta_generada = GeneradorMapa.generar_mapa_mision(
            self.fotos_vuelo_seleccionado, ruta_mapa
        )
        if ruta_generada:
            dialogo = VisorMapaDialog(ruta_generada, self)
            dialogo.exec()
        else:
            QMessageBox.information(
                self,
                "Sin Coordenadas",
                "Este vuelo no posee coordenadas GPS registradas.",
            )

    def _exportar_excel(self):
        if not self.vuelo_seleccionado:
            return
        datos_mision = self._obtener_datos_mision_formateados()
        nombre_sugerido = f"Reporte_Vuelo_{self.vuelo_seleccionado['id']}.xlsx"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar Reporte Excel", nombre_sugerido, "Excel (*.xlsx)"
        )
        if ruta:
            try:
                GeneradorReportes.exportar_excel(datos_mision, ruta)
                QMessageBox.information(
                    self, "Reporte Generado", f"Archivo Excel guardado en:\n{ruta}"
                )
            except (OSError, ValueError) as e:
                logger.exception("Error al guardar Excel histórico")
                QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar: {e}")

    def _exportar_pdf(self):
        if not self.vuelo_seleccionado:
            return
        datos_mision = self._obtener_datos_mision_formateados()
        nombre_sugerido = f"Reporte_Vuelo_{self.vuelo_seleccionado['id']}.pdf"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar Reporte PDF", nombre_sugerido, "PDF (*.pdf)"
        )
        if ruta:
            try:
                GeneradorReportes.exportar_pdf(datos_mision, ruta)
                QMessageBox.information(
                    self, "Reporte Generado", f"Archivo PDF guardado en:\n{ruta}"
                )
            except (OSError, ValueError, RuntimeError) as e:
                logger.exception("Error al generar PDF histórico")
                QMessageBox.critical(self, "Error al Exportar", f"No se pudo guardar: {e}")