"""Módulo de detección de ganado adaptativo con YOLO y SAHI para tomas aéreas."""

import logging
import os
from typing import Any, cast

import cv2
import torch
from sahi import AutoDetectionModel
from sahi.predict import get_sliced_prediction
from ultralytics import YOLO

logger = logging.getLogger(__name__)


class DetectorGanadero:
    """Motor de detección que unifica inferencia directa y segmentada (SAHI)."""

    def __init__(
        self,
        modelo_path: str = "models/yolo11n.pt",
        umbral_confianza: float = 0.45,
        tamano_corte: int = 640,
        solapamiento: float = 0.20,
    ) -> None:
        self.modelo_path = modelo_path
        self.confianza = umbral_confianza
        self.tamano_corte = tamano_corte
        self.solapamiento = solapamiento

        # 1. Fallback dinámico de hardware para no fallar en computadoras sin placa NVIDIA
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(
            "Inicializando DetectorGanadero [Modelo: %s | Dispositivo: %s | Conf: %.2f]",
            self.modelo_path,
            self.device,
            self.confianza,
        )

        # 2. Carga nativa de Ultralytics
        self.yolo_nativo = YOLO(self.modelo_path)

        # 3. Resolución dinámica de clases a detectar según el tipo de modelo
        self.alias_ganado = {
            "cow",
            "vaca",
            "cattle",
            "bovine",
            "bull",
            "ox",
            "livestock",
            "ternero",
            "calf",
        }
        self.indices_clases_validas = self._obtener_indices_clases_ganado()

        # 4. Carga de SAHI con backend ultralytics oficial
        self.sahi_model = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=self.modelo_path,
            confidence_threshold=self.confianza,
            device=self.device,
        )

    def _obtener_indices_clases_ganado(self) -> list[int] | None:
        """Determina automáticamente qué clases filtrar según el modelo cargado.

        Si el modelo tiene <= 2 clases (modelo custom para vacas), no filtra nada.
        Si es un modelo genérico con muchas clases (COCO 80 clases), busca sinónimos de ganado.
        """
        nombres = getattr(self.yolo_nativo, "names", {})
        if not nombres or len(nombres) <= 2:
            logger.info(
                "Modelo custom detectado (%d clases registradas). Inferencia sin filtro de exclusión.",
                len(nombres),
            )
            return None

        indices = [
            idx for idx, name in nombres.items() if str(name).lower() in self.alias_ganado
        ]
        logger.info(
            "Modelo general detectado (%d clases). Filtrando índices de ganado: %s",
            len(nombres),
            indices,
        )
        return indices if indices else None

    def detectar_en_imagen(
        self,
        ruta_imagen: str,
        usar_sahi: bool = False,
        guardar_resultado: bool = True,
        ruta_salida: str | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        """Ejecuta la inferencia sobre una captura y opcionalmente guarda la imagen anotada."""
        if not os.path.exists(ruta_imagen):
            logger.error("No existe el archivo de imagen: %s", ruta_imagen)
            return 0, []

        imagen_cv = cv2.imread(ruta_imagen) if guardar_resultado else None
        detecciones_mision: list[dict[str, Any]] = []

        try:
            if usar_sahi:
                # ------------------- CAMINO SAHI (CENITAL / SLICED) -------------------
                resultado_sahi = get_sliced_prediction(
                    ruta_imagen,
                    self.sahi_model,
                    slice_height=self.tamano_corte,
                    slice_width=self.tamano_corte,
                    overlap_height_ratio=self.solapamiento,
                    overlap_width_ratio=self.solapamiento,
                    postprocess_type="GREEDYNMM",
                    postprocess_match_metric="IOU",
                    postprocess_match_threshold=0.25,
                    verbose=0,
                )

                for pred in resultado_sahi.object_prediction_list:
                    nombre_cat = pred.category.name.lower()
                    cat_id = pred.category.id

                    # Validación de clase: coincide nombre, coincide índice, o el modelo es custom
                    es_valida = (
                        (self.indices_clases_validas is None)
                        or (nombre_cat in self.alias_ganado)
                        or (cat_id in self.indices_clases_validas)
                    )

                    if es_valida:
                        x1 = int(pred.bbox.minx)
                        y1 = int(pred.bbox.miny)
                        x2 = int(pred.bbox.maxx)
                        y2 = int(pred.bbox.maxy)
                        score = float(pred.score.value)

                        detecciones_mision.append(
                            {
                                "bbox": [x1, y1, x2, y2],
                                "confianza": score,
                                "clase": pred.category.name,
                            }
                        )

                        if guardar_resultado and imagen_cv is not None:
                            cv2.rectangle(imagen_cv, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(
                                imagen_cv,
                                f"Vaca {score:.0%}",
                                (x1, max(y1 - 6, 12)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (0, 255, 0),
                                1,
                                cv2.LINE_AA,
                            )

            else:
                # ------------------- CAMINO YOLO NATIVO DIRECTO -------------------
                argumentos_predict: dict[str, Any] = {
                    "source": ruta_imagen,
                    "conf": self.confianza,
                    "device": self.device,
                    "verbose": False,
                }
                if self.indices_clases_validas is not None:
                    argumentos_predict["classes"] = self.indices_clases_validas

                resultados_raw = self.yolo_nativo.predict(**argumentos_predict)
                resultados = cast(list[Any], resultados_raw)

                for res in resultados:
                    cajas = getattr(res, "boxes", None)
                    if cajas is None or len(cajas) == 0:
                        continue

                    # Extracción directa vectorizada de tensores (compatible con Mypy)
                    xyxy_lista = cajas.xyxy.cpu().numpy()
                    conf_lista = cajas.conf.cpu().numpy()
                    cls_lista = cajas.cls.cpu().numpy()

                    for i in range(len(xyxy_lista)):
                        x1, y1, x2, y2 = map(int, xyxy_lista[i])
                        conf = float(conf_lista[i])
                        cls_id = int(cls_lista[i])
                        nombre_clase = (
                            self.yolo_nativo.names.get(cls_id, "vaca")
                            if hasattr(self.yolo_nativo, "names")
                            else "vaca"
                        )

                        detecciones_mision.append(
                            {
                                "bbox": [x1, y1, x2, y2],
                                "confianza": conf,
                                "clase": nombre_clase,
                            }
                        )

                        if guardar_resultado and imagen_cv is not None:
                            cv2.rectangle(imagen_cv, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(
                                imagen_cv,
                                f"Vaca {conf:.0%}",
                                (x1, max(y1 - 6, 12)),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.5,
                                (0, 255, 0),
                                1,
                                cv2.LINE_AA,
                            )

            # Persistencia de la imagen si fue solicitada
            if guardar_resultado and ruta_salida and imagen_cv is not None:
                os.makedirs(os.path.dirname(ruta_salida), exist_ok=True)
                cv2.imwrite(ruta_salida, imagen_cv)

            return len(detecciones_mision), detecciones_mision

        except Exception:
            logger.exception("Fallo durante la inferencia de la imagen %s", ruta_imagen)
            return 0, []