# DECISIONES.md — AEROVEX
 
Registro de decisiones técnicas no obvias del proyecto. Objetivo: que cualquiera que toque este código después (humano o IA) entienda el *por qué*, no solo el *qué*, y no reintroduzca bugs ya resueltos.
 
Convención: cada entrada tiene fecha aproximada, el problema, la decisión tomada, y por qué se descartaron las alternativas.
 
---
 
## 1. Filtro de clases del detector: dinámico por nombre, no por ID fijo
 
**Archivo:** `app/core/detector.py` → `_obtener_indices_clases_ganado()`
 
**Problema:** La primera versión filtraba con `classes=[19]` hardcodeado (ID de "cow" en el dataset COCO de 80 clases, que es el que trae `yolo11n.pt` de fábrica). Esto funciona *solo* mientras se use el modelo genérico. El día que se entrene un modelo custom con fotos aéreas del Mavic 3M (que lógicamente va a tener 1 sola clase, "vaca", con ID `0`), el filtro `classes=[19]` no matchea nada y el conteo da **0 en silencio, sin error**.
 
**Decisión:** En el constructor, `_obtener_indices_clases_ganado()` inspecciona `self.yolo_nativo.names` (el diccionario de clases que trae cargado el propio modelo):
- Si el modelo tiene **≤ 2 clases** → se asume modelo custom entrenado para esto → **no se filtra nada**, todo lo detectado es ganado.
- Si el modelo tiene **muchas clases** (ej. COCO, 80) → se busca por **nombre** contra un set de alias (`cow`, `vaca`, `cattle`, `bovine`, `bull`, `ox`, `livestock`, `ternero`, `calf`) y se arma la lista de índices dinámicamente.
**Por qué no un ID fijo:** un ID de clase es un detalle de implementación del dataset con el que se entrenó *ese* modelo puntual. Cambia entre COCO, un modelo custom, o cualquier otro dataset. Filtrar por nombre (con fallback a "sin filtro" si hay pocas clases) hace que el mismo código sirva para el modelo de prueba actual y para el modelo custom sin tocar una línea cuando se haga el reemplazo.
 
**Si vas a tocar esto:** si entrenás el modelo custom con un nombre de clase que no sea `"vaca"` o `"cow"` (por ejemplo `"bovino"` en mayúscula rara, o en otro idioma), agregalo al set `alias_ganado`. Si el modelo custom termina teniendo más de 2 clases (por ejemplo, separar "vaca adulta" de "ternero"), esta heurística de `<= 2` deja de aplicar y hay que revisarla.
 
---
 
## 2. `model_type="ultralytics"` en SAHI (no `"yolov8"`)
 
**Archivo:** `app/core/detector.py` → `AutoDetectionModel.from_pretrained(...)`
 
**Decisión:** se usa `model_type="ultralytics"`, el wrapper genérico de SAHI que soporta YOLOv8/v9/v10/v11.
 
**Por qué no `"yolov8"`:** es un alias más viejo dentro de SAHI. Con `yolo11n.pt` (y cualquier modelo custom entrenado sobre YOLO11) puede fallar o comportarse distinto según la versión de SAHI instalada. No había ningún bug en el original — no tocar este valor sin una razón concreta y probada.
 
---
 
## 3. Fallback dinámico de dispositivo (CUDA → CPU)
 
**Archivo:** `app/core/detector.py` → `self.device`
 
```python
self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
```
 
**Problema:** la versión original forzaba `device="cuda:0"` sin chequeo. El cliente final es una persona de campo sin conocimientos de informática (San Agustín, Córdoba) — si algún día usa la app en una máquina sin GPU NVIDIA bien configurada (drivers, notebook distinta, etc.), la app **crasheaba** en vez de seguir funcionando más lento.
 
**Decisión:** detectar disponibilidad de CUDA en tiempo de inicialización y usar CPU como fallback transparente. El usuario nunca ve un error técnico — en el peor caso, la app tarda más en procesar.
 
---
 
## 4. Parámetros de SAHI: se mantienen fijos (`GREEDYNMM`, tiles configurables)
 
**Archivo:** `app/core/detector.py` → `get_sliced_prediction(...)`
 
**Decisión:** se conservan explícitos:
```python
postprocess_type="GREEDYNMM",
postprocess_match_metric="IOU",
postprocess_match_threshold=0.25,
```
más `slice_height`/`slice_width`/`overlap_*` parametrizados por `tamano_corte` y `solapamiento` del constructor (no hardcodeados dentro del método).
 
**Por qué importa:** `GREEDYNMM` es el algoritmo que fusiona detecciones duplicadas que aparecen en los bordes entre "tiles" cuando SAHI corta una imagen grande en pedazos para procesarla. Sin especificarlo, SAHI usa su valor por defecto (que puede variar entre versiones), y eso puede introducir doble conteo *dentro de una misma foto* — un problema distinto pero relacionado al de doble conteo entre fotos del punto 6.
 
**No simplificar esto** aunque parezca "solo config por defecto que se puede omitir".
 
---
 
## 5. Contrato de parámetros de `DetectorGanadero` — no renombrar sin actualizar todos los llamadores
 
**Archivos afectados:** `app/core/detector.py`, `app/workers/procesamiento_worker.py`, `test_sistema.py`
 
**Problema real que pasó:** en una iteración, se reescribió el detector renombrando `modelo_path` → `ruta_modelo`, `ruta_salida` → `ruta_salida_anotada`, y se eliminó el parámetro `guardar_resultado`. El archivo *en sí* estaba bien escrito, pero rompía en producción con `TypeError` apenas se ejecutaba un relevamiento real, porque `procesamiento_worker.py` y `test_sistema.py` seguían llamando con los nombres viejos.
 
**Decisión:** los nombres de parámetros de `DetectorGanadero.__init__` y `.detectar_en_imagen()` son parte del contrato público del módulo. Si se necesita cambiar una firma, hay que actualizar **en el mismo commit**:
- `app/workers/procesamiento_worker.py`
- `test_sistema.py`
- cualquier otro caller nuevo que se agregue
**Firma actual (de referencia):**
```python
DetectorGanadero(modelo_path, umbral_confianza, tamano_corte, solapamiento)
detectar_en_imagen(ruta_imagen, usar_sahi, guardar_resultado, ruta_salida)
```
 
**Nota sobre defaults:** los valores por defecto de `usar_sahi` y `guardar_resultado` cambiaron en algún punto (`True`/`False` originales → `False`/`True` actuales). Hoy no rompe nada porque todos los llamadores pasan los dos parámetros explícitos, pero si se agrega un caller nuevo (notebook de debug, script suelto) que no los pase, el comportamiento va a ser distinto al esperado originalmente. Revisar si conviene volver a los defaults originales para evitar sorpresas.
 
---
 
## 6. Pendiente conocido: doble conteo por solape entre fotos consecutivas del vuelo
 
**Estado:** NO resuelto todavía. Documentado acá para que no se pierda.
 
**Problema:** un vuelo en grilla con DJI Mavic 3M usa overlap típico de 60-70% entre fotos consecutivas (frontal/lateral) para permitir fotogrametría. Esto significa que la misma vaca físicamente puede aparecer en 2-4 fotos distintas. Si el conteo total simplemente suma las detecciones por foto (como hace hoy `ProcesamientoWorker` sumando `total_acumulado += conteo_foto`), **el total va a estar inflado** respecto a la cantidad real de animales en el lote.
 
**Enfoque propuesto (no implementado):** proyectar la posición geográfica aproximada de cada detección (usando lat/lon/alt de la foto + posición del bounding box dentro de la imagen) y aplicar una deduplicación tipo NMS espacial / geocercas de proximidad entre fotos del mismo vuelo, antes de sumar el total.
 
**Por qué no se resolvió todavía:** se priorizó primero dejar sólido el detector base (bug de clase hardcodeada) y validarlo con datos reales, antes de construir lógica de deduplicación sobre una base de detección que no estaba confirmada. Orden correcto, pero **este punto bloquea que el número final de "Total Cabezas Detectadas" sea confiable para entrega real al cliente**.
 
---
 
## 7. Pendiente conocido: altitud MSL vs AGL en telemetría EXIF
 
**Archivo:** `app/core/telemetria.py` → `extraer_metadatos_foto()`
 
**Problema:** el tag EXIF estándar `GPS GPSAltitude` que lee `exifread` da la altitud **absoluta sobre el nivel del mar (MSL)**, no la altura real de vuelo sobre el suelo (AGL). Si el lote está a, por ejemplo, 400 msnm y el dron vuela a 450m de altitud EXIF, la altura real sobre las vacas es 50m, no 450m.
 
**Dato relevante:** DJI suele guardar la altura relativa real (`drone-dji:RelativeAltitude`) en el bloque **XMP** de la imagen, que `exifread` **no lee** (solo procesa EXIF estándar).
 
**Estado:** no resuelto. Relevante para el día que se quiera usar la altura de vuelo para calcular GSD (ground sample distance / escala de píxel real) y ajustar automáticamente `tamano_corte` de SAHI según la altura real de cada vuelo. No bloquea el conteo actual, pero si en algún momento el conteo por foto empieza a fallar sistemáticamente en vuelos a distinta altura, revisar esto primero.
 
---
 
## 8. Modelo actual es genérico (COCO), no entrenado para vistas cenitales
 
**Estado:** el detector hoy usa `yolo11n.pt` de fábrica, entrenado sobre fotos de nivel de piso (perfil/frontal de vacas), no vistas aéreas nadir de dron.
 
**Por qué funciona igual en las pruebas actuales:** las imágenes de test (`01_una_vaca.jpg`, `02_cuatro_animales.jpg`) son fotos de referencia a nivel de piso, no fotos reales del dron — por eso el modelo genérico detecta bien.
 
**Riesgo:** una vaca vista desde arriba (nadir, 60-100m de altura) se ve muy distinta — más como un óvalo oscuro que como el perfil característico de una vaca. El modelo genérico puede no generalizar bien a ese ángulo. **No hay que asumir que el detector funciona en fotos aéreas reales solo porque funciona en estas fotos de prueba.**
 
**Siguiente paso necesario:** entrenar o hacer fine-tuning con fotos aéreas reales del Mavic 3M antes de considerar el sistema listo para uso en campo.
 
---
 
## Historial de este documento
 
- Creado tras cerrar la validación del módulo `detector.py` (fix del filtro de clases hardcodeado, fallback de GPU/CPU, y confirmación con `test_sistema.py` sobre imágenes reales).
- Mantener actualizado cada vez que se tome una decisión de diseño no obvia, especialmente al resolver los puntos 6, 7 y 8.
 