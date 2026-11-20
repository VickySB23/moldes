"""Dibuja una pieza sobre cualquier 'lienzo' (PDF o SVG).

Un lienzo debe tener:
    linea(pts, cerrada=False, ancho=0.03, trazo=None, color=(0,0,0), relleno=None)
    texto(x, y, s, tam=0.5, ang=0, ancla='centro', color=(0,0,0))
Coordenadas en cm, eje Y hacia abajo.
"""
from __future__ import annotations

import math

from .pieza import Pieza

NEGRO = (0, 0, 0)
GRIS = (0.45, 0.45, 0.45)
GRIS_CLARO = (0.75, 0.75, 0.75)


def _hex_a_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _anillos(geom):
    """Devuelve los contornos (exterior + agujeros) de un Polygon o MultiPolygon."""
    polys = getattr(geom, "geoms", [geom])
    for p in polys:
        if p.is_empty:
            continue
        yield list(p.exterior.coords)
        for h in p.interiors:
            yield list(h.coords)


def flecha(lz, p1, p2, ancho=0.03, doble=True, color=NEGRO):
    lz.linea([p1, p2], ancho=ancho, color=color)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L = math.hypot(dx, dy) or 1
    ux, uy = dx / L, dy / L
    s = 0.6
    for (px, py), sg in ((p2, 1), (p1, -1)) if doble else ((p2, 1),):
        a = (px - sg * ux * s - uy * s * 0.45, py - sg * uy * s + ux * s * 0.45)
        b = (px - sg * ux * s + uy * s * 0.45, py - sg * uy * s - ux * s * 0.45)
        lz.linea([a, (px, py), b], ancho=ancho, color=color)


def dibujar_pieza(lz, pz: Pieza, margen: float, color_relleno: bool = False,
                  escala_texto: float = 1.0):
    corte = pz.corte(margen)
    relleno = _hex_a_rgb(pz.color) if color_relleno else None

    # línea de corte (continua) y de costura (punteada)
    for anillo in _anillos(corte):
        lz.linea(anillo, cerrada=True, ancho=0.04, color=NEGRO, relleno=relleno)
    if margen > 0:
        poly = pz.poligono()
        for anillo in _anillos(poly):
            lz.linea(anillo, cerrada=True, ancho=0.02, trazo=(0.25, 0.15), color=GRIS)

    # doblez
    if pz.doblez:
        (x1, y1), (x2, y2) = pz.doblez
        lz.linea([(x1, y1), (x2, y2)], ancho=0.05, trazo=(0.6, 0.2, 0.1, 0.2), color=NEGRO)
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        cx, cy = pz.punto_etiqueta()
        if (cx - mx) * nx + (cy - my) * ny < 0:
            nx, ny = -nx, -ny
        lz.texto(mx + nx * 0.7, my + ny * 0.7, "DOBLEZ DE LA TELA", tam=0.45 * escala_texto,
                 ang=_ang_legible(ang))

    # hilo
    if pz.hilo:
        p1, p2 = pz.hilo
        flecha(lz, p1, p2, ancho=0.03, doble=pz.texto_hilo == "HILO")
        ang = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        a = math.radians(ang)
        lz.texto(mx - math.sin(a) * 0.45, my + math.cos(a) * 0.45, pz.texto_hilo,
                 tam=0.35 * escala_texto, ang=_ang_legible(ang))

    # marcas: piquete + letra
    for m in pz.marcas:
        if m.piquete:
            lz.linea([(m.x + m.nx * 0.25, m.y + m.ny * 0.25),
                      (m.x - m.nx * max(margen, 0.4), m.y - m.ny * max(margen, 0.4))],
                     ancho=0.04, color=NEGRO)
        if m.texto:
            lz.texto(m.x + m.nx * 0.75, m.y + m.ny * 0.75, m.texto,
                     tam=0.5 * escala_texto, ancla="centro")

    # etiqueta central
    cx, cy = pz.punto_etiqueta()
    poly = pz.poligono()
    minx, miny, maxx, maxy = poly.bounds
    t = max(0.35, min(0.8, (maxx - minx) / max(len(pz.nombre), 1) * 1.2)) * escala_texto
    lineas = [(pz.nombre, t), (pz.cortar, t * 0.7)] + [(n, t * 0.55) for n in pz.notas]
    y = cy - sum(s for _, s in lineas) * 0.6
    for txt, s in lineas:
        y += s * 1.2
        lz.texto(cx, y, txt, tam=s, ancla="centro")


def _ang_legible(ang):
    """Evita textos cabeza abajo."""
    while ang > 90:
        ang -= 180
    while ang < -90:
        ang += 180
    return ang
