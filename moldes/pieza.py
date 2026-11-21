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
    # margen distinto por tramo: una entrada por arista (contorno[k] → contorno[k+1],
    # la última cierra contra el primer punto). None = usar el margen general.
    margenes: list | None = None
    # líneas interiores (pinzas, líneas de doblez, ubicación de bolsillos): [(pts, estilo)]
    # estilo: "linea", "punteada" o "pinza"
    lineas: list = field(default_factory=list)

    # ---------- geometría ----------
    def poligono(self) -> Polygon:
        p = Polygon(self.contorno, self.agujeros)
        if not p.is_valid:
            p = p.buffer(0)
        return p

    def corte(self, margen: float) -> Polygon:
        """Línea de corte = línea de costura + margen (sin margen en el doblez)."""
        p = self.poligono()
        if self.margenes:
            c = _corte_por_tramos(self.contorno, self.margenes, margen).union(p)
            if c.geom_type != "Polygon":
                c = max(getattr(c, "geoms", [c]), key=lambda g: g.area)
        elif margen > 0:
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
        margenes = self.margenes
        if espejo:
            cont = cont[::-1]
            aguj = [h[::-1] for h in aguj]
            if margenes:
                n = len(cont)
                # al invertir el contorno, la arista k pasa a ser la n-2-k
                margenes = [margenes[(n - 2 - e) % n] for e in range(n)]
        return replace(
            self,
            contorno=cont,
            agujeros=aguj,
            hilo=tuple(T(p) for p in self.hilo) if self.hilo else None,
            doblez=tuple(T(p) for p in self.doblez) if self.doblez else None,
            marcas=marcas,
            margenes=margenes,
            lineas=[([T(p) for p in pts], est) for pts, est in self.lineas],
        )


# ---------- margen por tramos ----------

def _area_signada(pts) -> float:
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                     for i in range(len(pts)))


def _cruce_rectas(p1, p2, q1, q2):
    """Intersección de las rectas p1-p2 y q1-q2 (None si son casi paralelas)."""
    d1x, d1y = p2[0] - p1[0], p2[1] - p1[1]
    d2x, d2y = q2[0] - q1[0], q2[1] - q1[1]
    den = d1x * d2y - d1y * d2x
    n1, n2 = math.hypot(d1x, d1y), math.hypot(d2x, d2y)
    if n1 < 1e-9 or n2 < 1e-9 or abs(den) < 1e-6 * n1 * n2:
        return None
    t = ((q1[0] - p1[0]) * d2y - (q1[1] - p1[1]) * d2x) / den
    return (p1[0] + t * d1x, p1[1] + t * d1y)


def _corte_por_tramos(contorno, margenes, margen_general):
    """Línea de corte con un margen distinto en cada arista, con esquinas en inglete."""
    n = len(contorno)
    ms = [margen_general if (k >= len(margenes) or margenes[k] is None) else float(margenes[k])
          for k in range(n)]
    sentido = -1.0 if _area_signada(contorno) > 0 else 1.0   # hacia afuera
    if len(set(ms)) == 1:
        m = ms[0]
        p = Polygon(contorno).buffer(0)
        return p.buffer(m, join_style="mitre", mitre_limit=2.5) if m > 0 else p
    # agrupar aristas consecutivas con el mismo margen, empezando en un cambio
    inicio = next(k for k in range(n) if ms[k] != ms[k - 1])
    tramos, k0 = [], inicio
    for paso in range(1, n + 1):
        k = (inicio + paso) % n
        if paso == n or ms[k] != ms[k0]:
            idx = [(k0 + t) % n for t in range((k - k0) % n or n)] + [k]
            tramos.append(([contorno[i] for i in idx], ms[k0]))
            k0 = k
    salida = []
    for pts, m in tramos:
        if m <= 1e-9:
            off = pts
        else:
            g = LineString(pts).offset_curve(sentido * m, join_style="mitre", mitre_limit=2.5)
            partes = [list(x.coords) for x in getattr(g, "geoms", [g]) if not x.is_empty]
            off = [c for parte in partes for c in parte] or pts
        salida.append((off, m, pts))
    anillo = []
    for k, (off, m, pts) in enumerate(salida):
        sig, m2, _ = salida[(k + 1) % len(salida)]
        nodo = pts[-1]
        anillo.extend(off[:-1] if len(off) > 1 else off)
        x = None
        if len(off) >= 2 and len(sig) >= 2:
            x = _cruce_rectas(off[-2], off[-1], sig[0], sig[1])
        lim = 2.5 * max(m, m2, 0.1) + 0.05
        if x is not None and math.dist(x, nodo) <= lim:
            anillo.append(x)
        else:
            anillo.append(off[-1])
            anillo.append(sig[0])
    pol = Polygon(anillo)
    if not pol.is_valid:
        pol = pol.buffer(0)
    return pol


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
