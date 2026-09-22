"""Punto de entrada principal para AEROVEX."""

import sys

from PyQt6.QtWidgets import QApplication

from app.gui.main_window import VentanaPrincipal


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AEROVEX Core")

    ventana = VentanaPrincipal()
    ventana.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()