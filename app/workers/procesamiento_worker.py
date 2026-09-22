"""Worker asíncrono para procesamiento de imágenes ganaderas y telemetría."""

import gc
import logging
import os

import torch
from PyQt6.QtCore import QObject, pyqtSignal

from app.core.detector import DetectorGanadero
from app.core.telemetria import extraer_metadatos_foto

logger = logging.getLogger(__name__)


class ProcesamientoWorker(QObject):
    """Ejecuta inferencia y telemetría en un hilo secundario."""

    progreso = pyqtSignal(int)
    foto_procesada = pyqtSignal(str, int, str)
    mision_completa = pyqtSignal(list, int)
    mision_cancelada = pyqtSignal()
    error_ocurrido = pyqtSignal(str)

    def __init__(
        self,
        ruta_carpeta: str,
        potrero_id: int,
        confianza: float = 0.50,
        usar_sahi: bool = True,
    ):
        super().__init__()
        self.ruta_carpeta = ruta_carpeta
        self.potrero_id = potrero_id
        self.confianza = confianza
        self.usar_sahi = usar_sahi
        self._cancelado = False

    def detener(self):
        """Detiene de forma segura el ciclo de procesamiento."""
        self._cancelado = True

    def ejecutar(self):
        """Procesa todas las imágenes extrayendo conteo y telemetría GPS."""
        try:
            detector = DetectorGanadero(umbral_confianza=self.confianza)

            extensiones = (".jpg", ".jpeg", ".png", ".tif", ".tiff")
            archivos = [
                f
                for f in os.listdir(self.ruta_carpeta)
                if f.lower().endswith(extensiones)
                and not f.startswith("proc_")
                and not f.startswith("resultado_")
            ]

            total_archivos = len(archivos)
            if total_archivos == 0:
                self.error_ocurrido.emit(
                    "No se encontraron imágenes válidas en la carpeta seleccionada."
                )
                return

            carpeta_salida = os.path.join(self.ruta_carpeta, "procesadas")
            os.makedirs(carpeta_salida, exist_ok=True)

            datos_fotos = []
            total_acumulado = 0

            for indice, nombre_archivo in enumerate(archivos, start=1):
                if self._cancelado:
                    logger.info("Procesamiento cancelado por el usuario.")
                    break

                ruta_origen = os.path.join(self.ruta_carpeta, nombre_archivo)
                ruta_anotada = os.path.join(
                    carpeta_salida, f"proc_{nombre_archivo}"
                )

                # 1. Extracción de coordenadas EXIF del dron
                metadatos = extraer_metadatos_foto(ruta_origen)

                # 2. Inferencia de visión artificial
                conteo_foto, cajas = detector.detectar_en_imagen(
                    ruta_imagen=ruta_origen,
                    usar_sahi=self.usar_sahi,
                    guardar_resultado=True,
                    ruta_salida=ruta_anotada,
                )

                total_acumulado += conteo_foto

                # 3. Estructura compatible con DatabaseManager y Reportes
                datos_fotos.append({
                    "archivo": nombre_archivo,
                    "cantidad": conteo_foto,
                    "conteo_cabezas": conteo_foto,
                    "lat": metadatos.get("lat"),
                    "lon": metadatos.get("lon"),
                    "alt": metadatos.get("alt"),
                    "fecha_original": metadatos.get("fecha"),
                    "ruta_anotada": ruta_anotada,
                    "cajas": cajas,
                })

                self.foto_procesada.emit(
                    ruta_anotada, conteo_foto, nombre_archivo
                )
                porcentaje = int((indice / total_archivos) * 100)
                self.progreso.emit(porcentaje)

                # Limpieza periódica de memoria VRAM cada 10 capturas
                if indice % 10 == 0:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    gc.collect()

            if self._cancelado:
                self.mision_cancelada.emit()
            else:
                self.mision_completa.emit(datos_fotos, total_acumulado)

        except Exception as e:
            logger.exception("Fallo crítico en el worker de inferencia")
            self.error_ocurrido.emit(str(e))