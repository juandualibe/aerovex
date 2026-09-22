"""Módulo de generación de mapas satelitales interactivos para AEROVEX."""

import logging
import os

import folium  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class GeneradorMapa:
    """Construye mapas interactivos HTML usando Folium y Leaflet."""

    @staticmethod
    def generar_mapa_mision(fotos_data: list, ruta_salida_html: str) -> str | None:
        """Genera un mapa interactivo con capa satelital y marcadores de cada foto."""
        fotos_con_gps = [
            f
            for f in fotos_data
            if f.get("lat") is not None and f.get("lon") is not None
        ]

        if not fotos_con_gps:
            logger.warning("No hay coordenadas GPS para generar el mapa.")
            return None

        lats = [f["lat"] for f in fotos_con_gps]
        lons = [f["lon"] for f in fotos_con_gps]
        centro_lat = sum(lats) / len(lats)
        centro_lon = sum(lons) / len(lons)

        # Mapa base neutro (sin teselas automáticas para controlar los nombres)
        mapa = folium.Map(
            location=[centro_lat, centro_lon],
            zoom_start=16,
            tiles=None,
        )

        # Capa Satelital por defecto
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            attr="Google Satellite",
            name="Vista Satelital",
            overlay=False,
            control=True,
        ).add_to(mapa)

        # Capa alternativa de Rutas / Calles
        folium.TileLayer(
            "OpenStreetMap",
            name="Mapa de Rutas",
            overlay=False,
            control=True,
        ).add_to(mapa)

        puntos_trayectoria = []
        for idx, f in enumerate(fotos_con_gps, start=1):
            lat = f["lat"]
            lon = f["lon"]
            puntos_trayectoria.append((lat, lon))

            cantidad = f.get("cantidad", 0)
            archivo = f.get("archivo", f"Captura #{idx}")
            altitud = f.get("alt", "N/D")

            color_marcador = "green" if cantidad > 0 else "blue"

            popup_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 12px; width: 180px;">
                <h4 style="margin: 0 0 6px 0; color: #0f172a;">Foto: {archivo}</h4>
                <b>Ganado censado:</b> <span style="color: #16a34a; font-size: 14px; font-weight: bold;">{cantidad}</span><br>
                <b>Altitud:</b> {altitud} m<br>
                <b>Coordenadas:</b> {lat:.5f}, {lon:.5f}
            </div>
            """

            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=220),
                tooltip=f"{archivo}: {cantidad} animales",
                icon=folium.Icon(color=color_marcador, icon="camera", prefix="fa"),
            ).add_to(mapa)

        if len(puntos_trayectoria) > 1:
            folium.PolyLine(
                locations=puntos_trayectoria,
                color="#38bdf8",
                weight=2.5,
                opacity=0.8,
                dash_array="5, 10",
                tooltip="Trayectoria de Vuelo",
            ).add_to(mapa)

        folium.LayerControl(position="topright").add_to(mapa)

        os.makedirs(os.path.dirname(os.path.abspath(ruta_salida_html)), exist_ok=True)
        mapa.save(ruta_salida_html)
        return ruta_salida_html