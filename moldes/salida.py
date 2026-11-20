"""Acomoda las piezas y genera el PDF en hojas (A4 / Carta) y el SVG a tamaño real."""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import box

from .dibujo import _anillos, _hex_a_rgb, dibujar_pieza
from .pdf import PDF, LienzoCm, Pagina
from .pieza import Pieza

HOJAS = {
    "A4": (210.0, 297.0),
    "Carta": (215.9, 279.4),
    "A3": (297.0, 420.0),
}
MARGEN_HOJA_MM = 10.0


@dataclass
class Acomodo:
    piezas: list          # piezas ya movidas a su lugar (cm)
    ancho: float          # cm
    alto: float           # cm
    margen: float         # margen de costura (cm)


# ------------------------------------------------------------------ acomodo

def _estantes(cajas, ancho_max, sep):
    """Acomodo simple por estantes. cajas: [(i, w, h)] -> {i: (x, y)}, alto total."""
    pos, x, y, alto_fila = {}, sep, sep, 0.0
    for i, w, h in sorted(cajas, key=lambda c: -c[2]):
        if x + w + sep > ancho_max and x > sep:
            x = sep
            y += alto_fila + sep
            alto_fila = 0.0
        pos[i] = (x, y)
        x += w + sep
        alto_fila = max(alto_fila, h)
    return pos, y + alto_fila + sep


def acomodar(piezas: list[Pieza], margen: float, hoja: str = "A4", sep: float = 1.0) -> Acomodo:
    """Prueba distintos anchos (en columnas de hojas) y elige el que usa menos hojas."""
    if not piezas:
        raise ValueError("No hay piezas para acomodar.")
    w_mm, h_mm = HOJAS[hoja]
    cw = (w_mm - 2 * MARGEN_HOJA_MM) / 10
    ch = (h_mm - 2 * MARGEN_HOJA_MM) / 10

    cajas, bordes = [], []
    for i, p in enumerate(piezas):
        minx, miny, maxx, maxy = p.corte(margen).bounds
        bordes.append((minx, miny))
        cajas.append((i, maxx - minx, maxy - miny))
    ancho_min = max(w for _, w, _ in cajas) + 2 * sep

    mejor = None
    for cols in range(1, 9):
        ancho = cols * cw
        if ancho < ancho_min:
            continue
        pos, alto = _estantes(cajas, ancho, sep)
        filas = math.ceil(alto / ch)
        # cuenta sólo hojas con algo dibujado
        hojas_usadas = set()
        for i, w, h in cajas:
            x, y = pos[i]
            for r in range(int(y // ch), int((y + h) // ch) + 1):
                for c in range(int(x // cw), int((x + w) // cw) + 1):
                    hojas_usadas.add((r, c))
        clave = (len(hojas_usadas), cols * filas)
        if mejor is None or clave < mejor[0]:
            mejor = (clave, pos, ancho, alto)
    _, pos, ancho, alto = mejor
    movidas = []
    for i, p in enumerate(piezas):
        x, y = pos[i]
        bx, by = bordes[i]
        movidas.append(p.transformada(0, x - bx, y - by))
    # ancho real usado
    ancho_real = max(m.corte(margen).bounds[2] for m in movidas) + sep
    return Acomodo(movidas, ancho_real, alto, margen)


# ------------------------------------------------------------------ PDF

def _cuadricula(ac: Acomodo, hoja: str):
    w_mm, h_mm = HOJAS[hoja]
    cw = w_mm - 2 * MARGEN_HOJA_MM
    ch = h_mm - 2 * MARGEN_HOJA_MM
    cols = max(1, math.ceil(ac.ancho * 10 / cw - 1e-6))
    filas = max(1, math.ceil(ac.alto * 10 / ch - 1e-6))
    return cw, ch, cols, filas


def _celdas_usadas(ac: Acomodo, cw, ch):
    usadas = set()
    for p in ac.piezas:
        corte = p.corte(ac.margen)
        minx, miny, maxx, maxy = (v * 10 for v in corte.bounds)
        for r in range(int(miny // ch), int(maxy // ch) + 1):
            for c in range(int(minx // cw), int(maxx // cw) + 1):
                # comprobación fina: ¿la pieza toca de verdad esta celda?
                if corte.intersects(box(c * cw / 10, r * ch / 10, (c + 1) * cw / 10, (r + 1) * ch / 10)):
                    usadas.add((r, c))
    return usadas


def generar_pdf(ac: Acomodo, titulo: str, info: list[str], hoja: str = "A4") -> bytes:
    w_mm, h_mm = HOJAS[hoja]
    M = MARGEN_HOJA_MM
    cw, ch, cols, filas = _cuadricula(ac, hoja)
    usadas = _celdas_usadas(ac, cw, ch)
    pdf = PDF(titulo)

    # ---- portada
    pg = pdf.nueva_pagina(w_mm, h_mm)
    pg.texto(M, M + 8, titulo, tam=7, ancla="izq", negrita=True)
    y = M + 18
    for linea in info:
        pg.texto(M, y, linea, tam=3.4, ancla="izq")
        y += 5
    y += 3
    pg.texto(M, y, "IMPRIMIR AL 100 % (tamaño real, sin 'ajustar a la página').", tam=3.6,
             ancla="izq", negrita=True)
    y += 5
    pg.texto(M, y, "Medí los cuadrados de prueba antes de cortar.", tam=3.4, ancla="izq")
    y += 6
    # cuadrados de prueba
    pg.rect(M, y, 25, 25, ancho=0.35)
    pg.texto(M + 12.5, y + 12.5, "2,5 cm", tam=3.5)
    pg.rect(M + 32, y, 25.4, 25.4, ancho=0.35)
    pg.texto(M + 32 + 12.7, y + 12.7, "1 pulgada", tam=3.2)
    y += 33
    pg.texto(M, y, f"Mapa de hojas ({len(usadas)} para imprimir de {cols*filas}; "
                   f"las vacías no se incluyen):", tam=3.6, ancla="izq", negrita=True)
    y += 4
    # mapa
    disp_w, disp_h = w_mm - 2 * M, h_mm - y - M - 12
    esc = min(disp_w / (cols * cw), disp_h / (filas * ch))
    ox, oy = M, y
    pg.guardar()
    pg.transformar(esc, 0, 0, esc, ox, oy)
    for p in ac.piezas:
        for anillo in _anillos(p.corte(ac.margen)):
            pg.linea([(a * 10, b * 10) for a, b in anillo], cerrada=True, ancho=0.4 / esc,
                     color=(0.3, 0.3, 0.3), relleno=_hex_a_rgb(p.color))
    for r in range(filas):
        for c in range(cols):
            n = r * cols + c + 1
            usada = (r, c) in usadas
            pg.rect(c * cw, r * ch, cw, ch, ancho=0.5 / esc,
                    color=(0, 0, 0) if usada else (0.75, 0.75, 0.75),
                    trazo=None if usada else (2 / esc, 2 / esc))
            pg.texto(c * cw + cw / 2, r * ch + ch / 2, str(n), tam=min(cw, ch) * 0.25,
                     color=(0.1, 0.1, 0.1) if usada else (0.75, 0.75, 0.75), negrita=True)
    pg.restaurar()
    pg.texto(M, h_mm - M, "Pegá las hojas tocando los bordes del recuadro; hacé coincidir los "
                          "triángulos y números de las hojas vecinas.", tam=3, ancla="izq")

    # ---- hojas del molde
    for r in range(filas):
        for c in range(cols):
            if (r, c) not in usadas:
                continue
            n = r * cols + c + 1
            pg = pdf.nueva_pagina(w_mm, h_mm)
            pg.guardar()
            pg.recortar_rect(M, M, cw, ch)
            pg.transformar(1, 0, 0, 1, M - c * cw, M - r * ch)
            lz = LienzoCm(pg)
            for p in ac.piezas:
                minx, miny, maxx, maxy = (v * 10 for v in p.corte(ac.margen).bounds)
                if maxx < c * cw or minx > (c + 1) * cw or maxy < r * ch or miny > (r + 1) * ch:
                    continue
                dibujar_pieza(lz, p, ac.margen)
            pg.restaurar()
            _marco(pg, M, cw, ch, n, r, c, cols, filas, usadas)
    return pdf.bytes()


def _marco(pg: Pagina, M, cw, ch, n, r, c, cols, filas, usadas):
    gris = (0.55, 0.55, 0.55)
    pg.rect(M, M, cw, ch, ancho=0.25, color=gris)
    pg.texto(M + 4, M + 7, str(n), tam=9, ancla="izq", color=(0.6, 0.6, 0.6), negrita=True)
    pg.texto(M + cw - 2, M + ch + 5, f"Fila {r+1} · Columna {c+1}", tam=2.8, ancla="der", color=gris)
    s = 4.0
    # vecinos: triángulos en el centro de cada borde con el número de la hoja vecina
    vecinos = {
        "arriba": (r - 1, c), "abajo": (r + 1, c), "izq": (r, c - 1), "der": (r, c + 1),
    }
    for lado, (rr, cc) in vecinos.items():
        if not (0 <= rr < filas and 0 <= cc < cols):
            continue
        nv = rr * cols + cc + 1
        if lado == "arriba":
            pts = [(M + cw / 2 - s, M), (M + cw / 2 + s, M), (M + cw / 2, M + s)]
            tx, ty = M + cw / 2, M + s + 3
        elif lado == "abajo":
            pts = [(M + cw / 2 - s, M + ch), (M + cw / 2 + s, M + ch), (M + cw / 2, M + ch - s)]
            tx, ty = M + cw / 2, M + ch - s - 3
        elif lado == "izq":
            pts = [(M, M + ch / 2 - s), (M, M + ch / 2 + s), (M + s, M + ch / 2)]
            tx, ty = M + s + 4, M + ch / 2
        else:
            pts = [(M + cw, M + ch / 2 - s), (M + cw, M + ch / 2 + s), (M + cw - s, M + ch / 2)]
            tx, ty = M + cw - s - 4, M + ch / 2
        pg.linea(pts, cerrada=True, ancho=0.2, color=gris, relleno=(0.85, 0.85, 0.85))
        etiqueta = str(nv) if (rr, cc) in usadas else f"({nv})"
        pg.texto(tx, ty, etiqueta, tam=3, color=gris)
    # círculos en las esquinas para alinear
    for x, y in ((M, M), (M + cw, M), (M, M + ch), (M + cw, M + ch)):
        k = 16
        pg.linea([(x + 2 * math.cos(2 * math.pi * i / k), y + 2 * math.sin(2 * math.pi * i / k))
                  for i in range(k)], cerrada=True, ancho=0.2, color=gris)


# ------------------------------------------------------------------ SVG

class LienzoSVG:
    def __init__(self):
        self.partes: list[str] = []

    @staticmethod
    def _c(rgb):
        return "#%02x%02x%02x" % tuple(int(max(0, min(1, v)) * 255) for v in rgb)

    def linea(self, pts, cerrada=False, ancho=0.03, trazo=None, color=(0, 0, 0), relleno=None):
        d = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        tag = "polygon" if cerrada else "polyline"
        dash = f' stroke-dasharray="{" ".join(f"{t:.2f}" for t in trazo)}"' if trazo else ""
        fill = self._c(relleno) if relleno else "none"
        self.partes.append(f'<{tag} points="{d}" fill="{fill}" stroke="{self._c(color)}" '
                           f'stroke-width="{ancho:.3f}"{dash} stroke-linejoin="round"/>')

    def texto(self, x, y, s, tam=0.5, ang=0.0, ancla="centro", color=(0, 0, 0)):
        a = {"centro": "middle", "izq": "start", "der": "end"}[ancla]
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.partes.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{tam:.2f}" text-anchor="{a}" '
            f'dominant-baseline="central" font-family="Helvetica,Arial,sans-serif" '
            f'fill="{self._c(color)}" transform="rotate({ang:.1f} {x:.2f} {y:.2f})">{s}</text>')


def generar_svg(ac: Acomodo, color: bool = True) -> str:
    lz = LienzoSVG()
    for p in ac.piezas:
        dibujar_pieza(lz, p, ac.margen, color_relleno=color)
    w, h = ac.ancho, ac.alto
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}cm" height="{h:.2f}cm" '
            f'viewBox="0 0 {w:.2f} {h:.2f}">\n<rect width="100%" height="100%" fill="white"/>\n'
            + "\n".join(lz.partes) + "\n</svg>\n")
