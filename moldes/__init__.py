"""moldes: moldes de costura para ropa (paramétricos) y peluches (desde 3D)."""
from .pieza import Marca, Pieza
from .salida import acomodar, generar_pdf, generar_svg

__all__ = ["Pieza", "Marca", "acomodar", "generar_pdf", "generar_svg"]
__version__ = "0.1.0"
