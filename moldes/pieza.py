"""Pieza de molde: contorno (línea de costura), margen, hilo, doblez y marcas.

Todas las medidas están en centímetros. El eje Y apunta hacia abajo
(como en una hoja), así el molde se ve igual en pantalla y en el PDF.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polylabel


@dataclass
class Marca:
    """Piquete y/o letra de unión sobre la línea de costura."""
    x: float
    y: float
    nx: float  # normal hacia adentro de la pieza (unitaria)
    ny: float
    texto: str = ""
    piquete: bool = True


@dataclass
class Pieza:
    nombre: str
    contorno: list            # [(x, y), ...] línea de costura, cerrada implícitamente
    cortar: str = "Cortar 1"
    hilo: tuple | None = None     # ((x1, y1), (x2, y2)) dirección del hilo / pelo
    texto_hilo: str = "HILO"
    doblez: tuple | None = None   # ((x1, y1), (x2, y2)) borde que va al doblez de la tela
    marcas: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    agujeros: list = field(default_factory=list)  # contornos interiores (raro)
    color: str = "#cfe8b0"

    # ---------- geometría ----------
    def poligono(self) -> Polygon:
        p = Polygon(self.contorno, self.agujeros)
        if not p.is_valid:
            p = p.buffer(0)
        return p

    def corte(self, margen: float) -> Polygon:
        """Línea de corte = línea de costura + margen (sin margen en el doblez)."""
        p = self.poligono()
        if margen > 0:
            c = p.buffer(margen, join_style="mitre", mitre_limit=2.5)
        else:
            c = p
        if self.doblez:
            (x1, y1), (x2, y2) = self.doblez
            dx, dy = x2 - x1, y2 - y1
            L = math.hypot(dx, dy) or 1.0
            ux, uy = dx / L, dy / L
            nx, ny = -uy, ux
            cx, cy = p.representative_point().coords[0]
            if (cx - x1) * nx + (cy - y1) * ny < 0:
                nx, ny = -nx, -ny
            R = 1e4
            semiplano = Polygon([
                (x1 - ux * R, y1 - uy * R),
                (x1 + ux * R, y1 + uy * R),
                (x1 + ux * R + nx * R, y1 + uy * R + ny * R),
                (x1 - ux * R + nx * R, y1 - uy * R + ny * R),
            ])
            c = c.intersection(semiplano)
        return c

    def punto_etiqueta(self):
        p = self.poligono()
        c = p.centroid
        try:
            q = polylabel(p, tolerance=0.2)
            # preferimos el centroide si está bien adentro de la pieza
            if p.contains(c) and p.exterior.distance(c) > 0.6 * p.exterior.distance(q):
                q = c
        except Exception:
            q = p.representative_point()
        return q.x, q.y

    # ---------- transformaciones ----------
    def transformada(self, ang_grados: float = 0.0, dx: float = 0.0, dy: float = 0.0,
                     espejo: bool = False) -> "Pieza":
        a = math.radians(ang_grados)
        c, s = math.cos(a), math.sin(a)
        sx = -1.0 if espejo else 1.0

        def T(pt):
            x, y = pt[0] * sx, pt[1]
            return (c * x - s * y + dx, s * x + c * y + dy)

        def Rv(vx, vy):
            vx *= sx
            return (c * vx - s * vy, s * vx + c * vy)

        marcas = []
        for m in self.marcas:
            x, y = T((m.x, m.y))
            nx, ny = Rv(m.nx, m.ny)
            marcas.append(Marca(x, y, nx, ny, m.texto, m.piquete))
        cont = [T(p) for p in self.contorno]
        aguj = [[T(p) for p in h] for h in self.agujeros]
        if espejo:
            cont = cont[::-1]
            aguj = [h[::-1] for h in aguj]
        return replace(
            self,
            contorno=cont,
            agujeros=aguj,
            hilo=tuple(T(p) for p in self.hilo) if self.hilo else None,
            doblez=tuple(T(p) for p in self.doblez) if self.doblez else None,
            marcas=marcas,
        )


# ---------- utilidades ----------

def marca_en(pieza: Pieza, x: float, y: float, texto: str = "", piquete: bool = True) -> Marca:
    """Crea una marca en el punto del contorno más cercano a (x, y),
    con la normal apuntando hacia adentro de la pieza."""
    poly = pieza.poligono()
    borde = poly.exterior
    d = borde.project(Point(x, y))
    L = borde.length
    p = borde.interpolate(d)
    p1 = borde.interpolate((d - 0.3) % L)
    p2 = borde.interpolate((d + 0.3) % L)
    tx, ty = p2.x - p1.x, p2.y - p1.y
    n = math.hypot(tx, ty) or 1.0
    nx, ny = -ty / n, tx / n
    if not poly.contains(Point(p.x + nx * 0.2, p.y + ny * 0.2)):
        nx, ny = -nx, -ny
    return Marca(p.x, p.y, nx, ny, texto, piquete)


def bezier(p0, p1, p2, p3, n: int = 24, incluir_inicio: bool = True):
    """Puntos de una curva Bézier cúbica."""
    pts = []
    for i in range(0 if incluir_inicio else 1, n + 1):
        t = i / n
        u = 1 - t
        x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def largo(pts) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def punto_a_distancia(pts, d: float):
    """Punto sobre una polilínea a distancia d desde su inicio."""
    return LineString(pts).interpolate(d).coords[0]
