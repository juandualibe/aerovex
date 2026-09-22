# AEROVEX | Estación de Relevamiento Ganadero con Drones

Software de escritorio para procesamiento de imágenes aéreas y conteo automatizado de hacienda mediante visión computacional. Desarrollado a medida para productores agropecuarios en Córdoba (Argentina), optimizado para vuelos de relevamiento con drones **DJI Mavic 3M** sobre potreros de pastoreo y verdeos.

> ⚠️ **Estado del proyecto:** En desarrollo activo. Pipeline base validado (detección YOLO11/SAHI, persistencia SQLite WAL, reportes Excel/PDF y mapa satelital interactivo). Pendiente la deduplicación espacial por solape de fotos y el dataset cenital definitivo.

---

## Índice
1. [¿Qué hace la aplicación?](#qué-hace-la-aplicación)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Estructura del Proyecto](#estructura-del-proyecto)
4. [Instalación y Configuración](#instalación-y-configuración)
5. [Flujo de Trabajo (Uso)](#flujo-de-trabajo-uso)
6. [Base de Datos Local](#base-de-datos-local)
7. [Módulo de Detección e Inferencia](#módulo-de-detección-e-inferencia)
8. [Pendientes Críticos para Producción](#pendientes-críticos-para-producción)
9. [Roadmap y Mejoras Ganaderas](#roadmap-y-mejoras-ganaderas)
10. [Hardware y Rendimiento](#hardware-y-rendimiento)

---

## ¿Qué hace la aplicación?

1. **Ingesta de vuelo:** El productor descarga la tarjeta SD del dron a una carpeta local y la selecciona en AEROVEX ("Examinar Vuelo...").
2. **Asignación de Potrero:** Vincula la misión al potrero correspondiente cargado en el sistema catastral.
3. **Inferencia Adaptativa:**
   - **YOLO directo:** Inferencia nativa ultra-rápida.
   - **SAHI (Slicing Aided Hyper Inference):** Segmentación por mosaicos (tiles) con algoritmo `GREEDYNMM` para tomas cenitales en altura o rodeos de alta concentración.
4. **Extracción de Telemetría:** Lee metadatos EXIF (coordenadas GPS, altitud MSL, timestamp).
5. **Auditoría y Validación:** Permite revisar cada captura individualmente con sus recuadros verdes (*bounding boxes*), porcentajes de certeza y coordenadas.
6. **Mapeo y Reportes:**
   - Mapa satelital interactivo embebido con la traza del vuelo y densidad de animales.
   - Exportación de planillas de liquidación en **Excel (.xlsx)** e informes técnicos de auditoría en **PDF**.
   - Cálculo automático de **Carga Animal (Cabezas / Hectárea)**.

---

## Arquitectura del Sistema

```
┌──────────────────────────────────────────────────────────┐
│           VentanaPrincipal (PyQt6 - Dark/Light)           │
└───────────────────────────┬────────────────────────────────┘
                             │ dispara ejecución
                             ▼
┌──────────────────────────────────────────────────────────┐
│         ProcesamientoWorker (QThread asíncrono)            │
│  ├── Ingesta y lectura EXIF (telemetria.py)                │
│  ├── Inferencia YOLO / SAHI (detector.py)                  │
│  └── Renderizado y guardado de anotaciones (OpenCV)        │
└─────────────┬──────────────────────────────┬───────────────┘
              │ al finalizar misión           │ visualización
              ▼                               ▼
┌───────────────────────────┐    ┌──────────────────────────┐
│ DatabaseManager (SQLite)   │    │  GeneradorMapa (Folium)   │
│ - Modo WAL de concurrencia │    │  - Visor Leaflet HTML     │
│ - Transacciones atómicas   │    │  - Traza y pines GPS      │
└───────────────────────────┘    └──────────────────────────┘
              │ exportación
              ▼
┌──────────────────────────────────────────────────────────┐
│  GeneradorReportes (Excel con openpyxl | PDF reportlab)    │
└──────────────────────────────────────────────────────────┘
```

---

## Estructura del Proyecto

```text
aerovex_app/
├── main.py                          # Inicializador de la interfaz gráfica PyQt6
├── test_sistema.py                  # Script integral de diagnóstico (GPU, DB, Pipeline)
├── test_backend.py                  # Test unitario sin dependencias gráficas
├── requirements.txt                 # Dependencias congeladas del entorno
├── DECISIONES.md                    # ADR: Registro de decisiones técnicas de diseño
├── README.md                        # Documentación técnica general
│
├── models/
│   └── yolo11n.pt                   # Pesos base YOLO11 (Ultralytics)
│
├── data/
│   └── aerovex.db                   # Base de datos SQLite (se genera automáticamente)
│
├── app/
│   ├── core/
│   │   ├── detector.py              # DetectorGanadero: YOLO11 + SAHI + Fallback Hardware
│   │   └── telemetria.py            # Parser EXIF/GPS para metadatos de vuelo
│   │
│   ├── database/
│   │   └── db_manager.py            # Capa de datos SQLite en modo WAL transaccional
│   │
│   ├── workers/
│   │   └── procesamiento_worker.py  # Hilo QThread para no congelar la GUI en inferencia
│   │
│   ├── gui/                         # Interfaces de usuario PyQt6
│   │   ├── main_window.py           # Ventana principal y panel de auditoría
│   │   ├── historial_dialog.py      # Visor modal de misiones históricas
│   │   └── map_dialog.py            # Visor web embebido (QWebEngineView)
│   │
│   └── reports/
│       ├── generador_reportes.py    # Generación de informes en Excel (.xlsx) y PDF
│       └── generador_mapa.py        # Generador de capas satelitales interactivas (Folium)
│
└── test_images/                     # Capturas de prueba para calibración de laboratorio
```

---

## Instalación y Configuración

### Requisitos Previos
- **Sistema Operativo:** Windows 10 / Windows 11 (integrado con API DWM de Windows).
- **Python:** 3.10 o 3.11 recomendado.
- **Aceleración Gráfica (Opcional):** GPU NVIDIA con drivers actualizados y soporte CUDA 11.8 / 12.x. (Incluye fallback transparente a CPU si no se detecta placa NVIDIA).

### Pasos de Instalación

1. Clonar o descargar el repositorio:
   ```bash
   cd aerovex_app
   ```

2. Crear y activar el entorno virtual:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Instalar dependencias:
   ```powershell
   pip install -r requirements.txt
   ```

4. Verificación de sistema (Diagnóstico de hardware y DB):
   ```powershell
   python test_sistema.py
   ```
   Verifica CUDA, detecta potreros, ejecuta una inferencia en lote y valida la escritura en base de datos.

5. Lanzar la aplicación:
   ```powershell
   python main.py
   ```

---

## Flujo de Trabajo (Uso)

1. **Seleccionar Carpeta de Vuelo:** Click en "Examinar Vuelo..." y elegir la carpeta con las tomas JPG del dron.
2. **Seleccionar Potrero:** Elegir de la lista desplegable el potrero auditado (trae las hectáreas asignadas para el cálculo de carga).
3. **Ajustar Parámetros de Inferencia:**
   - **Modo SAHI (Optimización Cenital):** Tildar para fotos tomadas a más de 40m de altura o con rodeos densos.
   - **Umbral de Confianza:** Ajustar con el slider (recomendado 45% - 50% para equilibrio entre falsos positivos y falsos negativos).
4. **Iniciar Relevamiento:** El hilo en segundo plano procesa la cola de imágenes. Muestra barra de progreso y fotos procesadas en tiempo real.
5. **Auditoría:** En la tabla inferior, hacer doble click en cualquier fila para inspeccionar la foto con los animales etiquetados.
6. **Exportar Resultados:**
   - **Botón Visualizar Mapa:** Inspecciona los pines georreferenciados.
   - **Botón Exportar Excel:** Descarga la matriz de datos y cómputo de cabezas.
   - **Botón Generar Informe:** Genera un PDF formal para la administración del campo.

---

## Base de Datos Local

La persistencia se gestiona con SQLite (`data/aerovex.db`) configurado en modo **WAL** (Write-Ahead Logging) para evitar bloqueos por concurrencia.

**Tablas Principales:**
- **`potreros`**: Identificador, nombre del lote, superficie en hectáreas y observaciones de manejo.
- **`vuelos`**: Registro de misiones, fecha y hora UTC, total acumulado de cabezas y ruta en disco.
- **`detecciones_foto`**: Detalle por imagen (nombre de archivo, latitud, longitud, altitud y cabezas contabilizadas).

---

## Módulo de Detección e Inferencia

Ubicado en `app/core/detector.py`, el componente `DetectorGanadero` implementa:

- **Filtrado Dinámico de Clases:**
  - Si el modelo cargado tiene ≤ 2 clases (modelo específico entrenado para vacas), no filtra, asumiendo detección total de ganado.
  - Si es un modelo genérico (COCO con 80 clases), busca dinámicamente alias ganaderos (`cow`, `vaca`, `cattle`, `bovine`, etc.) para asignar el índice correspondiente sin hardcodear el ID 19.
- **Soporte SAHI Oficial:** Utiliza `model_type="ultralytics"` y supresión de solapamiento interno mediante `postprocess_type="GREEDYNMM"` con `IOU=0.25`.
- **Hardware Fallback:** Conmuta automáticamente entre `cuda:0` y `cpu` según la disponibilidad de PyTorch en tiempo de arranque.

---

## Pendientes Críticos para Producción

1. **Deduplicación Espacial por Solape (NMS Geográfico):**
   En vuelos con solapamiento del 60%-70%, una misma vaca aparece en múltiples imágenes consecutivas.
   *Solución planificada:* Proyectar el centro de cada bounding box a coordenadas geográficas (Lat/Lon) según altitud y GSD, deduplicando detecciones que caigan dentro de un radio de proximidad física (< 2.5 metros).

2. **Dataset Cenital / Fine-Tuning de YOLO:**
   El modelo base (`yolo11n.pt`) fue entrenado a nivel de suelo. En tomas cenitales (nadir) a 60 metros, los animales se aprecian como elipses dorsales. Es mandatorio reentrenar sobre fotos aéreas tomadas con el Mavic 3M.

3. **Altitud AGL vs. MSL en EXIF:**
   La altitud leída actualmente corresponde al elipsoide/mar (MSL). Se incorporará la lectura del bloque XMP (`drone-dji:RelativeAltitude`) para calcular la distancia real del sensor al suelo (AGL).

---

## Roadmap y Mejoras Ganaderas

- [ ] **ABM de Potreros desde la GUI:** Diseñador o importador de polígonos KML / KMZ de Google Earth para geocercas automáticas.
- [ ] **Diferenciación de Categorías:** Clasificación por área métrica dorsal entre Vientre Adulto y Ternero al pie.
- [ ] **Alerta de Comportamiento:** Detección de animales apartados del rodeo (> 250m) para prevención de distocias, rengueras o empastes.
- [ ] **Valuación Financiera en Pie:** Integración de cotización de hacienda (kilo vivo MAG Cañuelas / Dólar) para cálculo de capital líquido en lote.

---

## Hardware y Rendimiento

- **Entorno de Desarrollo:** Intel Core i7 / AMD Ryzen + NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM).
- **Equipo de Campo Sugerido:** Notebook con GPU dedicada NVIDIA (RTX 3050 / 4050 / 5060 o superior). Compatible con CPU para uso de contingencia.
- **Espacio en Disco:** Se recomienda monitorizar el directorio de vuelos procesados ante campañas extensas de tomas aéreas de alta resolución.