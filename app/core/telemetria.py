"""Módulo de Telemetría para AEROVEX.

Extrae coordenadas geográficas (Latitud, Longitud, Altitud) y fecha
directamente desde los metadatos EXIF de las fotos del DJI Mavic 3M.
"""

import logging
import os

import exifread

logger = logging.getLogger(__name__)


def _convertir_a_grados_decimales(coordenada, referencia):
    """Convierte una tupla sexagesimal [grados, minutos, segundos] a grados decimales.

    Ejemplo: 31° 46' 55.56" S -> -31.782100
    """
    try:
        grados = float(coordenada.values[0].num) / float(
            coordenada.values[0].den
        )
        minutos = float(coordenada.values[1].num) / float(
            coordenada.values[1].den
        )
        segundos = float(coordenada.values[2].num) / float(
            coordenada.values[2].den
        )

        decimal = grados + (minutos / 60.0) + (segundos / 3600.0)

        if referencia in ["S", "W"]:
            decimal = -decimal

        return round(decimal, 6)
    except Exception:
        logger.warning(
            "No se pudo convertir la coordenada a decimal", exc_info=True
        )
        return None


def extraer_metadatos_foto(ruta_archivo):
    """Abre una imagen del dron y extrae latitud, longitud, altitud y fecha de disparo.

    Retorna un diccionario con los datos limpios.
    """
    datos = {
        "archivo": os.path.basename(ruta_archivo),
        "lat": None,
        "lon": None,
        "alt": None,
        "fecha": None,
        "valida": False,
    }

    try:
        with open(ruta_archivo, "rb") as f:
            tags = exifread.process_file(f, details=False)

            if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
                lat_raw = tags["GPS GPSLatitude"]
                lat_ref = tags["GPS GPSLatitudeRef"].printable
                datos["lat"] = _convertir_a_grados_decimales(lat_raw, lat_ref)

            if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
                lon_raw = tags["GPS GPSLongitude"]
                lon_ref = tags["GPS GPSLongitudeRef"].printable
                datos["lon"] = _convertir_a_grados_decimales(lon_raw, lon_ref)

            if "GPS GPSAltitude" in tags:
                alt_tag = tags["GPS GPSAltitude"]
                datos["alt"] = round(
                    float(alt_tag.values[0].num) / float(alt_tag.values[0].den),
                    2,
                )

            if "Image DateTime" in tags:
                datos["fecha"] = tags["Image DateTime"].printable

            datos["valida"] = True

    except Exception:
        logger.exception(
            "Error al procesar metadatos del archivo %s", ruta_archivo
        )
        datos["valida"] = False

    return datos