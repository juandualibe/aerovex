"""Módulo de Persistencia y Base de Datos para AEROVEX.

Maneja la conexión a SQLite, creación de tablas y transacciones.
Implementa modo WAL (Write-Ahead Logging) para evitar corrupción de datos.
"""

import logging
import os
import sqlite3

# Logger dedicado para este módulo específico
logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path="data/aerovex.db"):
        """Inicializa la ruta de la base de datos y asegura que la carpeta exista."""
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._inicializar_tablas()

    def get_conexion(self):
        """Retorna una conexión activa con soporte de tipos de fila relacionales

        y activa el modo WAL para alta concurrencia y tolerancia a fallos.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # MODO WAL: Permite lecturas y escrituras simultáneas sin trabar la base
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _inicializar_tablas(self):
        """Crea las tablas maestras si no existen al arrancar la aplicación."""
        query_potreros = """
        CREATE TABLE IF NOT EXISTS potreros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            superficie_ha REAL NOT NULL DEFAULT 0.0,
            observaciones TEXT
        );
        """

        query_vuelos = """
        CREATE TABLE IF NOT EXISTS vuelos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            potrero_id INTEGER NOT NULL,
            fecha_mision TEXT NOT NULL,
            total_cabezas INTEGER NOT NULL DEFAULT 0,
            ruta_carpeta TEXT NOT NULL,
            FOREIGN KEY (potrero_id) REFERENCES potreros (id) ON DELETE CASCADE
        );
        """

        query_detecciones = """
        CREATE TABLE IF NOT EXISTS detecciones_foto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vuelo_id INTEGER NOT NULL,
            archivo_nombre TEXT NOT NULL,
            latitud REAL,
            longitud REAL,
            altitud REAL,
            cantidad_vacas INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (vuelo_id) REFERENCES vuelos (id) ON DELETE CASCADE
        );
        """

        try:
            with self.get_conexion() as conn:
                cursor = conn.cursor()
                cursor.execute(query_potreros)
                cursor.execute(query_vuelos)
                cursor.execute(query_detecciones)

                cursor.execute(
                    """
                INSERT OR IGNORE INTO potreros (id, nombre, superficie_ha) 
                VALUES 
                    (1, 'Potrero Bajo Norte', 85.0),
                    (2, 'Lote El Molino', 120.0),
                    (3, 'Potrero Las Sierras', 64.5);
                """
                )
                conn.commit()
                logger.info(
                    "Base de datos inicializada correctamente en: %s",
                    self.db_path,
                )
        except Exception:
            logger.exception("Error al inicializar la base de datos")
            raise

    def registrar_mision(
        self, potrero_id, fecha_mision, total_cabezas, ruta_carpeta, fotos_data
    ):
        """Guarda un vuelo completo de manera transaccional (todo o nada).

        Si falla una foto, revierte todo para evitar datos inconsistentes.
        """
        conn = self.get_conexion()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO vuelos (potrero_id, fecha_mision, total_cabezas, ruta_carpeta)
                    VALUES (?, ?, ?, ?);
                """,
                    (potrero_id, fecha_mision, total_cabezas, ruta_carpeta),
                )
                vuelo_id = cursor.lastrowid

                for foto in fotos_data:
                    cursor.execute(
                        """
                        INSERT INTO detecciones_foto 
                        (vuelo_id, archivo_nombre, latitud, longitud, altitud, cantidad_vacas)
                        VALUES (?, ?, ?, ?, ?, ?);
                    """,
                        (
                            vuelo_id,
                            foto["archivo"],
                            foto.get("lat"),
                            foto.get("lon"),
                            foto.get("alt"),
                            foto["cantidad"],
                        ),
                    )

                logger.info(
                    "Vuelo ID %s registrado exitosamente con %s animales.",
                    vuelo_id,
                    total_cabezas,
                )
                return vuelo_id
        except Exception:
            logger.exception("Fallo al registrar la misión en la BD")
            conn.rollback()
            raise
        finally:
            conn.close()

    def obtener_potreros(self):
        """Devuelve la lista de potreros para cargar en el selector de la interfaz."""
        with self.get_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, nombre, superficie_ha FROM potreros ORDER BY"
                " nombre ASC;"
            )
            return cursor.fetchall()

    def obtener_vuelos_historial(self) -> list[dict]:
        """Obtiene la lista de todos los vuelos registrados con el nombre de su potrero."""
        query = """
            SELECT 
                v.id,
                v.fecha_mision,
                v.total_cabezas,
                v.ruta_carpeta,
                p.nombre AS potrero_nombre,
                p.superficie_ha,
                p.id AS potrero_id
            FROM vuelos v
            JOIN potreros p ON v.potrero_id = p.id
            ORDER BY v.id DESC;
        """
        with self.get_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            filas = cursor.fetchall()
            return [dict(f) for f in filas]

    def obtener_detalle_vuelo(self, vuelo_id: int) -> list[dict]:
        """Obtiene el desglose de todas las fotos y detecciones de un vuelo específico."""
        query = """
            SELECT 
                archivo_nombre AS archivo,
                cantidad_vacas AS cantidad,
                latitud AS lat,
                longitud AS lon,
                altitud AS alt
            FROM detecciones_foto
            WHERE vuelo_id = ?
            ORDER BY id ASC;
        """
        with self.get_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (vuelo_id,))
            filas = cursor.fetchall()
            return [dict(f) for f in filas]