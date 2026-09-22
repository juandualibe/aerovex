"""Script de Prueba y Diagnóstico para AEROVEX.

Verifica GPU, Base de Datos, Modelo YOLO y pipeline general con múltiples imágenes.
"""

import logging
import os
import urllib.request
from datetime import datetime, timezone

import torch

from app.core.detector import DetectorGanadero
from app.database.db_manager import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")


def main() -> None:
    print("=" * 60)
    print("   AEROVEX CORE - COMPROBACIÓN DE SISTEMA")
    print("=" * 60)

    # 1. Comprobar aceleración por GPU
    tiene_cuda = torch.cuda.is_available()
    print(
        f"[*] Aceleración por GPU (CUDA): "
        f"{'ACTIVA' if tiene_cuda else 'NO DISPONIBLE'}"
    )
    if tiene_cuda:
        print(f"[*] Dispositivo detectado: {torch.cuda.get_device_name(0)}")

    # 2. Comprobar Base de Datos SQLite
    print("\n[*] Inicializando base de datos local...")
    db = DatabaseManager()
    potreros = db.obtener_potreros()
    print(f"[OK] Base de datos activa. Potreros registrados: {len(potreros)}")
    for p in potreros:
        print(f"    - ID {p['id']}: {p['nombre']} ({p['superficie_ha']} Ha)")

    # 3. Preparación de lote de prueba
    os.makedirs("test_images", exist_ok=True)
    fotos_test = [
        "01_una_vaca.jpg",
        "02_cuatro_animales.jpg",
    ]

    # Descarga de respaldo solo si la primera imagen no existiera
    ruta_primera = os.path.join("test_images", fotos_test[0])
    if not os.path.exists(ruta_primera):
        print("\n[*] Descargando imagen de prueba estándar...")
        url = "https://images.unsplash.com/photo-1546445317-29f4545e9d53?w=800&q=80"
        urllib.request.urlretrieve(url, ruta_primera)

    # 4. Iniciar Detector YOLO
    print("\n[*] Inicializando modelo YOLO...")
    detector = DetectorGanadero(modelo_path="yolo11n.pt", umbral_confianza=0.50)

    print("\n[*] Ejecutando detección de prueba sobre el lote...")
    total_mision = 0
    datos_fotos = []

    # Coordenadas simuladas para el test
    coords_simuladas = [
        (-31.782100, -64.391200, 450.5),
        (-31.782500, -64.391600, 452.0),
    ]

    for idx, nombre_archivo in enumerate(fotos_test):
        ruta_origen = os.path.join("test_images", nombre_archivo)
        if not os.path.exists(ruta_origen):
            print(f"[AVISO] Archivo no encontrado en disco: {ruta_origen}")
            continue

        ruta_salida = os.path.join("test_images", f"resultado_{nombre_archivo}")

        conteo, _cajas = detector.detectar_en_imagen(
            ruta_imagen=ruta_origen,
            usar_sahi=False,
            guardar_resultado=True,
            ruta_salida=ruta_salida,
        )
        total_mision += conteo

        lat, lon, alt = coords_simuladas[idx % len(coords_simuladas)]
        datos_fotos.append(
            {
                "archivo": nombre_archivo,
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "cantidad": conteo,
            }
        )

        print(
            f"[OK] {nombre_archivo} -> Animales detectados: {conteo} | Guardada en: {ruta_salida}"
        )

    print(f"\n[*] TOTAL LOTE PROCESADO: {total_mision} cabezas detectadas.")

    # 5. Prueba de persistencia en SQLite
    print("\n[*] Registrando vuelo de prueba en la base de datos...")
    fecha_actual = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    vuelo_id = db.registrar_mision(
        potrero_id=1,
        fecha_mision=fecha_actual,
        total_cabezas=total_mision,
        ruta_carpeta="test_images",
        fotos_data=datos_fotos,
    )
    print(f"[OK] Misión guardada con éxito bajo el ID: #{vuelo_id}")

    print("\n" + "=" * 60)
    print("   ESTADO: TODOS LOS MÓDULOS BASE RESPONDEN OK")
    print("=" * 60)


if __name__ == "__main__":
    main()