"""Ventana Principal de AEROVEX con interfaz de campo homogénea y de alto contraste."""

import ctypes
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QFont, QPixmap, QShowEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database.db_manager import DatabaseManager
from app.gui.historial_dialog import HistorialDialog
from app.gui.map_dialog import VisorMapaDialog
from app.reports.generador_mapa import GeneradorMapa
from app.reports.generador_reportes import GeneradorReportes
from app.workers.procesamiento_worker import ProcesamientoWorker

logger = logging.getLogger(__name__)


def aplicar_tema_barra_dialogo(dialogo: QWidget) -> None:
    """Aplica color claro (#f8fafc) y texto oscuro a la barra de título de Windows 11."""
    if sys.platform != "win32":
        return

    try:
        hwnd = int(dialogo.winId())
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
        logger.debug("No se pudo aplicar tema DWM a la ventana: %s", e)


class VentanaPrincipal(QMainWindow):
    """Panel de control de AEROVEX diseñado para trabajo de campo."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AEROVEX | Estación de Relevamiento Ganadero")
        self.setMinimumSize(960, 580)

        self.db = DatabaseManager()
        self.thread_worker = None
        self.worker = None

        self.carpeta_seleccionada = ""
        self.ultimos_datos_mision = None
        self.fotos_cache = {}

        self._inicializar_ui()
        self._cargar_potreros()
        self.showMaximized()

    def showEvent(self, a0: QShowEvent | None) -> None:
        """Se ejecuta al renderizarse la ventana en pantalla para aplicar el tema nativo."""
        super().showEvent(a0)
        aplicar_tema_barra_dialogo(self)

    def _inicializar_ui(self):
        widget_central = QWidget()
        layout_principal = QVBoxLayout(widget_central)
        layout_principal.setSpacing(10)
        layout_principal.setContentsMargins(14, 14, 14, 14)

        # 1. Barra de Control Superior
        layout_principal.addWidget(self._crear_panel_superior())

        # 2. Configuración de Parámetros
        layout_principal.addWidget(self._crear_panel_parametros())

        # 3. Área de Trabajo Central (Inspección + Tabla)
        panel_central = QHBoxLayout()
        panel_central.setSpacing(10)

        self.visor_imagen = QLabel(
            "Sin capturas en cola\nSeleccione un directorio de vuelo para iniciar el relevamiento."
        )
        self.visor_imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.visor_imagen.setMinimumSize(420, 260)
        self.visor_imagen.setStyleSheet(
            """
            QLabel {
                background-color: #f1f5f9;
                color: #64748b;
                border: 2px dashed #cbd5e1;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
            }
            """
        )
        panel_central.addWidget(self.visor_imagen, stretch=6)
        panel_central.addWidget(self._crear_panel_auditoria(), stretch=4)
        layout_principal.addLayout(panel_central)

        # 4. Indicador de Progreso
        self.barra_progreso = QProgressBar()
        self.barra_progreso.setValue(0)
        self.barra_progreso.setTextVisible(True)
        self.barra_progreso.setStyleSheet(
            """
            QProgressBar {
                background-color: #e2e8f0;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                text-align: center;
                height: 18px;
                font-weight: bold;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 3px;
            }
            """
        )
        layout_principal.addWidget(self.barra_progreso)

        # 5. Barra de Acciones Inferior Homogénea
        layout_principal.addWidget(self._crear_panel_acciones())

        self.setCentralWidget(widget_central)
        self._aplicar_estilo_general()

    def _crear_panel_superior(self):
        panel = QFrame()
        panel.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px;"
        )
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)

        self.btn_seleccionar_carpeta = QPushButton("Examinar Vuelo...")
        self.btn_seleccionar_carpeta.clicked.connect(self._seleccionar_carpeta)

        self.lbl_ruta_carpeta = QLabel("Directorio no asignado")
        self.lbl_ruta_carpeta.setStyleSheet(
            "color: #475569; font-weight: 600; padding-left: 6px;"
        )

        lbl_potrero = QLabel("Potrero / Lote:")
        lbl_potrero.setStyleSheet("color: #0f172a; font-weight: bold;")

        self.combo_potreros = QComboBox()
        self.combo_potreros.setMinimumWidth(240)

        self.btn_historial = QPushButton("Registro de Misiones")
        self.btn_historial.clicked.connect(self._abrir_historial)

        layout.addWidget(self.btn_seleccionar_carpeta)
        layout.addWidget(self.lbl_ruta_carpeta, stretch=1)
        layout.addWidget(lbl_potrero)
        layout.addWidget(self.combo_potreros)
        layout.addWidget(self.btn_historial)
        return panel

    def _crear_panel_parametros(self):
        panel = QFrame()
        panel.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px 10px;"
        )
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 4, 10, 4)

        self.chk_sahi = QCheckBox("Optimización Cenital de Alta Densidad (SAHI)")
        self.chk_sahi.setChecked(False)
        self.chk_sahi.setStyleSheet(
            "color: #0f172a; font-weight: 600; font-size: 12px;"
        )

        lbl_slider = QLabel("Umbral de Confianza:")
        lbl_slider.setStyleSheet("color: #475569; font-weight: 600;")

        self.slider_confianza = QSlider(Qt.Orientation.Horizontal)
        self.slider_confianza.setRange(20, 80)
        self.slider_confianza.setValue(50)
        self.slider_confianza.setFixedWidth(160)

        self.lbl_valor_confianza = QLabel("50%")
        self.lbl_valor_confianza.setStyleSheet(
            "color: #0f172a; font-weight: bold; min-width: 40px;"
        )
        self.slider_confianza.valueChanged.connect(
            lambda v: self.lbl_valor_confianza.setText(f"{v}%")
        )

        layout.addWidget(self.chk_sahi)
        layout.addSpacing(30)
        layout.addWidget(lbl_slider)
        layout.addWidget(self.slider_confianza)
        layout.addWidget(self.lbl_valor_confianza)
        layout.addStretch()
        return panel

    def _crear_panel_auditoria(self):
        grupo = QGroupBox("Auditoría de Capturas")
        grupo.setStyleSheet(
            """
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #0f172a;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            """
        )
        layout = QVBoxLayout(grupo)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 14, 10, 10)

        panel_totales = QFrame()
        panel_totales.setStyleSheet(
            "background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px;"
        )
        layout_totales = QVBoxLayout(panel_totales)
        layout_totales.setContentsMargins(8, 6, 8, 6)

        lbl_desc = QLabel("TOTAL ANIMALES DETECTADOS")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setStyleSheet(
            "color: #64748b; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )

        self.lbl_total_cabezas = QLabel("0")
        self.lbl_total_cabezas.setFont(QFont("Segoe UI", 32, QFont.Weight.Bold))
        self.lbl_total_cabezas.setStyleSheet("color: #0f172a;")
        self.lbl_total_cabezas.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_foto_actual = QLabel("Visualizando: -")
        self.lbl_foto_actual.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_foto_actual.setStyleSheet("color: #475569; font-size: 11px;")

        layout_totales.addWidget(lbl_desc)
        layout_totales.addWidget(self.lbl_total_cabezas)
        layout_totales.addWidget(self.lbl_foto_actual)
        layout.addWidget(panel_totales)

        self.tabla_auditoria = QTableWidget()
        self.tabla_auditoria.setColumnCount(2)
        self.tabla_auditoria.setHorizontalHeaderLabels(["Captura", "Conteo"])
        self.tabla_auditoria.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tabla_auditoria.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tabla_auditoria.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tabla_auditoria.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.tabla_auditoria.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.tabla_auditoria.setStyleSheet(
            """
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
                padding: 4px;
            }
            """
        )
        self.tabla_auditoria.cellClicked.connect(self._al_seleccionar_foto_tabla)
        layout.addWidget(self.tabla_auditoria)

        return grupo

    def _crear_panel_acciones(self):
        contenedor = QFrame()
        contenedor.setStyleSheet(
            "background-color: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px; padding: 4px;"
        )
        layout = QHBoxLayout(contenedor)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        # Botón principal de ejecución: Azul técnico refinado
        self.btn_iniciar = QPushButton("Iniciar Relevamiento")
        self.btn_iniciar.setFixedHeight(36)
        self.btn_iniciar.setStyleSheet(
            """
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: 600;
                border: 1px solid #1d4ed8;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background-color: #1d4ed8; }
            QPushButton:disabled { 
                background-color: #f1f5f9; 
                color: #94a3b8; 
                border-color: #e2e8f0; 
            }
            """
        )
        self.btn_iniciar.clicked.connect(self._iniciar_procesamiento)
        self.btn_iniciar.setEnabled(False)

        # Botón Detener: Mismo formato y alineación estándar
        self.btn_detener = QPushButton("Detener")
        self.btn_detener.setFixedHeight(36)
        self.btn_detener.setEnabled(False)
        self.btn_detener.setStyleSheet(
            """
            QPushButton {
                background-color: #ffffff;
                color: #dc2626;
                font-weight: 600;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { 
                background-color: #fef2f2; 
                border-color: #fca5a5; 
            }
            QPushButton:disabled { 
                background-color: #f8fafc; 
                color: #94a3b8; 
                border-color: #e2e8f0; 
            }
            """
        )
        self.btn_detener.clicked.connect(self._detener_procesamiento)

        self.btn_ver_mapa = QPushButton("Visualizar Mapa")
        self.btn_ver_mapa.setFixedHeight(36)
        self.btn_ver_mapa.setEnabled(False)
        self.btn_ver_mapa.clicked.connect(self._abrir_mapa)

        self.btn_exportar_excel = QPushButton("Exportar Excel (XLSX)")
        self.btn_exportar_excel.setFixedHeight(36)
        self.btn_exportar_excel.setEnabled(False)
        self.btn_exportar_excel.clicked.connect(self._exportar_excel)

        self.btn_exportar_pdf = QPushButton("Generar Informe (PDF)")
        self.btn_exportar_pdf.setFixedHeight(36)
        self.btn_exportar_pdf.setEnabled(False)
        self.btn_exportar_pdf.clicked.connect(self._exportar_pdf)

        # Cada botón ocupa una proporción perfectamente equilibrada
        layout.addWidget(self.btn_iniciar, stretch=1)
        layout.addWidget(self.btn_detener, stretch=1)
        layout.addWidget(self.btn_ver_mapa, stretch=1)
        layout.addWidget(self.btn_exportar_excel, stretch=1)
        layout.addWidget(self.btn_exportar_pdf, stretch=1)
        return contenedor

    def _aplicar_estilo_general(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #f8fafc; }
            QLabel { color: #0f172a; font-family: 'Segoe UI', sans-serif; }
            
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

            QComboBox {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:hover {
                border-color: #94a3b8;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #0f172a;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: 1px solid #cbd5e1;
                outline: none;
                padding: 4px;
            }

            QSlider::groove:horizontal {
                height: 4px;
                background: #cbd5e1;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #2563eb;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #0f172a;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }

            /* Diálogos modales y alertas homogéneas */
            QMessageBox {
                background-color: #ffffff;
            }
            QMessageBox QLabel {
                color: #0f172a;
                font-size: 12px;
            }
            QMessageBox QPushButton {
                background-color: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
                min-width: 60px;
            }
            QMessageBox QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
            """
        )

    def _cargar_potreros(self):
        self.combo_potreros.clear()
        self.potreros_cache = self.db.obtener_potreros()
        for p in self.potreros_cache:
            self.combo_potreros.addItem(
                f"{p['nombre']} ({p['superficie_ha']} Ha)", p["id"]
            )

    def _seleccionar_carpeta(self):
        ruta = QFileDialog.getExistingDirectory(
            self, "Seleccionar Directorio de Vuelo del Dron"
        )
        if ruta:
            self.carpeta_seleccionada = ruta
            self.lbl_ruta_carpeta.setText(os.path.basename(ruta) or ruta)
            self.btn_iniciar.setEnabled(True)

    def _abrir_historial(self):
        dialogo = HistorialDialog(self)
        dialogo.exec()

    def _iniciar_procesamiento(self):
        if not self.carpeta_seleccionada:
            return

        potrero_id = self.combo_potreros.currentData()
        confianza_val = self.slider_confianza.value() / 100.0
        usar_sahi_val = self.chk_sahi.isChecked()

        self.fotos_cache.clear()
        self.tabla_auditoria.setRowCount(0)
        self.barra_progreso.setValue(0)
        self.lbl_total_cabezas.setText("0")
        self.lbl_foto_actual.setText("Visualizando: Procesando lote...")

        self.btn_iniciar.setEnabled(False)
        self.btn_detener.setEnabled(True)
        self.btn_seleccionar_carpeta.setEnabled(False)
        self.btn_ver_mapa.setEnabled(False)
        self.btn_exportar_excel.setEnabled(False)
        self.btn_exportar_pdf.setEnabled(False)

        self.thread_worker = QThread()
        self.worker = ProcesamientoWorker(
            ruta_carpeta=self.carpeta_seleccionada,
            potrero_id=potrero_id,
            confianza=confianza_val,
            usar_sahi=usar_sahi_val,
        )
        self.worker.moveToThread(self.thread_worker)

        self.thread_worker.started.connect(self.worker.ejecutar)
        self.worker.progreso.connect(self.barra_progreso.setValue)
        self.worker.foto_procesada.connect(self._actualizar_vista_foto)
        self.worker.mision_completa.connect(self._finalizar_mision)
        self.worker.mision_cancelada.connect(self._manejar_cancelacion)
        self.worker.error_ocurrido.connect(self._mostrar_error)

        self.worker.mision_completa.connect(self.thread_worker.quit)
        self.worker.mision_cancelada.connect(self.thread_worker.quit)
        self.worker.error_ocurrido.connect(self.thread_worker.quit)
        self.thread_worker.finished.connect(self.thread_worker.deleteLater)

        self.thread_worker.start()

    def _detener_procesamiento(self):
        if self.worker:
            self.worker.detener()
            self.btn_detener.setEnabled(False)

    def _manejar_cancelacion(self):
        self._restablecer_botones()
        msg = QMessageBox(self)
        msg.setWindowTitle("Operación Cancelada")
        msg.setText("El relevamiento ha sido interrumpido por el operador.")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        aplicar_tema_barra_dialogo(msg)
        msg.exec()

    def _actualizar_vista_foto(self, ruta_anotada, vacas_en_foto, nombre_foto):
        self.fotos_cache[nombre_foto] = {
            "ruta": ruta_anotada,
            "conteo": vacas_en_foto,
        }

        self._mostrar_imagen_en_visor(ruta_anotada)

        total_actual = int(self.lbl_total_cabezas.text()) + vacas_en_foto
        self.lbl_total_cabezas.setText(str(total_actual))
        self.lbl_foto_actual.setText(f"Visualizando: {nombre_foto} (+{vacas_en_foto})")

        fila = self.tabla_auditoria.rowCount()
        self.tabla_auditoria.insertRow(fila)

        item_nombre = QTableWidgetItem(nombre_foto)
        item_conteo = QTableWidgetItem(str(vacas_en_foto))
        item_conteo.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.tabla_auditoria.setItem(fila, 0, item_nombre)
        self.tabla_auditoria.setItem(fila, 1, item_conteo)
        self.tabla_auditoria.scrollToBottom()

    def _al_seleccionar_foto_tabla(self, fila, _columna):
        item_nombre = self.tabla_auditoria.item(fila, 0)
        if not item_nombre:
            return

        nombre_archivo = item_nombre.text()
        info_foto = self.fotos_cache.get(nombre_archivo)
        if info_foto and os.path.exists(info_foto["ruta"]):
            self._mostrar_imagen_en_visor(info_foto["ruta"])
            self.lbl_foto_actual.setText(
                f"Visualizando: {nombre_archivo} ({info_foto['conteo']} animales)"
            )

    def _mostrar_imagen_en_visor(self, ruta_imagen):
        pixmap = QPixmap(ruta_imagen)
        if not pixmap.isNull():
            escalado = pixmap.scaled(
                self.visor_imagen.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.visor_imagen.setPixmap(escalado)

    def _finalizar_mision(self, datos_fotos, total_cabezas):
        potrero_id = self.combo_potreros.currentData()

        fecha_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if datos_fotos and datos_fotos[0].get("fecha_original"):
            fecha_str = datos_fotos[0]["fecha_original"]

        potrero_obj = next(
            (p for p in self.potreros_cache if p["id"] == potrero_id), None
        )
        nombre_potrero = potrero_obj["nombre"] if potrero_obj else "Desconocido"
        superficie_ha = potrero_obj["superficie_ha"] if potrero_obj else 0.0

        self.ultimos_datos_mision = {
            "potrero_nombre": nombre_potrero,
            "superficie_ha": superficie_ha,
            "total_cabezas": total_cabezas,
            "fecha": fecha_str,
            "fotos": datos_fotos,
        }

        self._restablecer_botones()

        try:
            vuelo_id = self.db.registrar_mision(
                potrero_id=potrero_id,
                fecha_mision=fecha_str,
                total_cabezas=total_cabezas,
                ruta_carpeta=self.carpeta_seleccionada,
                fotos_data=datos_fotos,
            )
            msg = QMessageBox(self)
            msg.setWindowTitle("Relevamiento Finalizado")
            msg.setText(
                f"Misión completada exitosamente.\n"
                f"Total verificado: {total_cabezas} animales en {len(datos_fotos)} tomas.\n"
                f"Asignado al Registro ID #{vuelo_id}."
            )
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            aplicar_tema_barra_dialogo(msg)
            msg.exec()
        except sqlite3.Error as e:
            msg_error = QMessageBox(self)
            msg_error.setWindowTitle("Aviso de Base de Datos")
            msg_error.setText(
                f"El conteo concluyó pero ocurrió una advertencia en la base de datos: {e}"
            )
            msg_error.setIcon(QMessageBox.Icon.Warning)
            msg_error.setStandardButtons(QMessageBox.StandardButton.Ok)
            aplicar_tema_barra_dialogo(msg_error)
            msg_error.exec()

    def _mostrar_error(self, mensaje):
        self._restablecer_botones()
        msg = QMessageBox(self)
        msg.setWindowTitle("Fallo en el Procesamiento")
        msg.setText(mensaje)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        aplicar_tema_barra_dialogo(msg)
        msg.exec()

    def _restablecer_botones(self):
        self.btn_iniciar.setEnabled(True)
        self.btn_detener.setEnabled(False)
        self.btn_seleccionar_carpeta.setEnabled(True)
        if self.ultimos_datos_mision:
            self.btn_exportar_excel.setEnabled(True)
            self.btn_exportar_pdf.setEnabled(True)
            tiene_gps = any(
                f.get("lat") is not None
                for f in self.ultimos_datos_mision.get("fotos", [])
            )
            self.btn_ver_mapa.setEnabled(tiene_gps)

    def _abrir_mapa(self):
        if not self.ultimos_datos_mision:
            return

        ruta_mapa = os.path.join(
            self.carpeta_seleccionada, "procesadas", "mapa_vuelo.html"
        )
        ruta_generada = GeneradorMapa.generar_mapa_mision(
            self.ultimos_datos_mision.get("fotos", []), ruta_mapa
        )

        if ruta_generada:
            dialogo = VisorMapaDialog(ruta_generada, self)
            dialogo.exec()
        else:
            msg = QMessageBox(self)
            msg.setWindowTitle("Sin Coordenadas GPS")
            msg.setText(
                "Las capturas analizadas no disponen de metadatos espaciales para graficar el recorrido."
            )
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            aplicar_tema_barra_dialogo(msg)
            msg.exec()

    def _exportar_excel(self):
        if not self.ultimos_datos_mision:
            return
        ruta, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Planilla de Relevamiento",
            "Reporte_Mision.xlsx",
            "Excel (*.xlsx)",
        )
        if ruta:
            try:
                GeneradorReportes.exportar_excel(self.ultimos_datos_mision, ruta)
                msg = QMessageBox(self)
                msg.setWindowTitle("Exportación Exitosa")
                msg.setText(f"Planilla generada correctamente en:\n{ruta}")
                msg.setIcon(QMessageBox.Icon.Information)
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                aplicar_tema_barra_dialogo(msg)
                msg.exec()
            except (OSError, ValueError) as e:
                logger.exception("Error al generar planilla Excel")
                msg = QMessageBox(self)
                msg.setWindowTitle("Error al Exportar")
                msg.setText(f"No se pudo guardar el archivo: {e}")
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                aplicar_tema_barra_dialogo(msg)
                msg.exec()

    def _exportar_pdf(self):
        if not self.ultimos_datos_mision:
            return
        ruta, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Informe Técnico",
            "Reporte_Mision.pdf",
            "PDF (*.pdf)",
        )
        if ruta:
            try:
                GeneradorReportes.exportar_pdf(self.ultimos_datos_mision, ruta)
                msg = QMessageBox(self)
                msg.setWindowTitle("Informe Generado")
                msg.setText(f"Documento PDF generado correctamente en:\n{ruta}")
                msg.setIcon(QMessageBox.Icon.Information)
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                aplicar_tema_barra_dialogo(msg)
                msg.exec()
            except (OSError, ValueError, RuntimeError) as e:
                logger.exception("Error al exportar informe PDF")
                msg = QMessageBox(self)
                msg.setWindowTitle("Error al Exportar")
                msg.setText(f"No se pudo generar el documento: {e}")
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                aplicar_tema_barra_dialogo(msg)
                msg.exec()