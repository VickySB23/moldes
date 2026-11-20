"""Moldes de ropa paramétricos: se dibujan con código a partir de medidas.

Para agregar una prenda nueva: escribí una función que reciba las medidas
y devuelva (piezas, informe), y registrala en PRENDAS al final del archivo.
"""
from __future__ import annotations

import math

from .pieza import Pieza, bezier, largo, marca_en, punto_a_distancia

VERDE, ROSA, CELESTE, AMARILLO, LILA = "#cfe8b0", "#f6c9d6", "#c4def4", "#f8e7a6", "#ddd0f2"


# --------------------------------------------------------------------- remera

def remera(pecho=96, largo_total=68, hombros=44, cuello=38, largo_manga=20,
           brazo=30, holgura=10, **_):
    """Remera básica de tejido de punto: delantero, espalda, manga y vivo de cuello."""
    W = (pecho + holgura) / 4            # medio ancho de cada pieza (al doblez)
    nw = cuello / 6 + 1.0                # medio ancho de escote
    sx = hombros / 2                     # punta de hombro
    sd = 4.0                             # caída de hombro
    ad = (pecho + holgura) / 8 + 10.5    # profundidad de sisa (desde el cuello)
    vuelo = 1.0                          # ensanche en el ruedo
    escotes = {"Delantero": cuello / 6 + 2.5, "Espalda": 2.0}

    piezas, curvas = [], {}
    for nombre, prof in escotes.items():
        cuello_pts = bezier((0, prof), (nw * 0.6, prof), (nw, prof * 0.5), (nw, 0))
        meter = 0.8 if nombre == "Delantero" else 0.4
        sisa = bezier((sx, sd), (sx - meter, sd + 0.55 * (ad - sd)),
                      (sx + 0.1 * (W - sx), ad), (W, ad))
        contorno = cuello_pts + sisa + [(W + vuelo, largo_total), (0, largo_total)]
        p = Pieza(nombre, contorno, cortar="Cortar 1 al doblez",
                  doblez=((0, prof), (0, largo_total)),
                  hilo=((W * 0.78, ad + 4), (W * 0.78, largo_total - 8)),
                  color=VERDE if nombre == "Delantero" else CELESTE)
        # letras de unión
        p.marcas.append(marca_en(p, (nw + sx) / 2, sd / 2, "A"))                      # hombro
        p.marcas.append(marca_en(p, W + vuelo / 2, (ad + largo_total) / 2, "B"))      # costado
        sisa_inv = sisa[::-1]                                                        # desde la axila
        d = 7.0 if nombre == "Delantero" else 8.0
        x, y = punto_a_distancia(sisa_inv, d)
        p.marcas.append(marca_en(p, x, y, "C" if nombre == "Delantero" else "D"))
        piezas.append(p)
        curvas[nombre] = (largo(sisa), largo(cuello_pts))

    sisa_del, cue_del = curvas["Delantero"]
    sisa_esp, cue_esp = curvas["Espalda"]
    sisa_total = sisa_del + sisa_esp

    # manga: se busca la altura de copa para que su curva mida sisa + embebido
    SW = brazo + holgura * 0.6
    embebido = 1.0
    objetivo = sisa_total + embebido

    def copa(h):
        izq = bezier((0, h), (SW / 2 * 0.35, h * 0.95), (SW / 2 * 0.55, 0), (SW / 2, 0))
        der = [(SW - x, y) for x, y in izq[::-1]]
        return izq, der

    avisos = []
    if objetivo <= SW:
        avisos.append("La sisa es muy chica para el ancho de manga: revisá brazo/holgura.")
        ch = 3.0
    else:
        lo, hi = 0.5, largo_manga * 0.95
        for _ in range(60):
            mid = (lo + hi) / 2
            izq, der = copa(mid)
            if largo(izq) + largo(der[1:]) < objetivo:
                lo = mid
            else:
                hi = mid
        ch = (lo + hi) / 2
        if ch >= largo_manga * 0.9:
            avisos.append("La copa de manga quedó casi tan alta como la manga: alargá la manga.")
    izq, der = copa(ch)
    hw = SW * 0.88
    contorno = izq + der[1:] + [(SW - (SW - hw) / 2, largo_manga), ((SW - hw) / 2, largo_manga)]
    manga = Pieza("Manga", contorno, cortar="Cortar 2 (una en espejo)",
                  hilo=((SW / 2, ch + 2), (SW / 2, largo_manga - 2)), color=AMARILLO)
    x, y = punto_a_distancia(izq, 7.0)
    manga.marcas.append(marca_en(manga, x, y, "C"))
    x, y = punto_a_distancia(der[::-1], 8.0)
    manga.marcas.append(marca_en(manga, x, y, "D"))
    manga.marcas.append(marca_en(manga, SW / 2, 0, "A"))
    manga.marcas.append(marca_en(manga, (SW - (SW - hw) / 4) - 0.1, (ch + largo_manga) / 2, "E"))
    manga.marcas.append(marca_en(manga, (SW - hw) / 4 + 0.1, (ch + largo_manga) / 2, "E"))
    manga.notas.append("delantero = lado C")
    piezas.append(manga)

    # vivo de cuello (ribb): 85 % del contorno del escote
    escote_total = 2 * (cue_del + cue_esp)
    L = round(escote_total * 0.85, 1)
    vivo = Pieza("Vivo de cuello", [(0, 0), (L, 0), (L, 5), (0, 5)],
                 cortar="Cortar 1 (ribb)", hilo=((L * 0.2, 2.5), (L * 0.2 + 3, 2.5)), color=ROSA)
    vivo.texto_hilo = "ESTIRA"
    vivo.notas.append("doblar al medio a lo largo")
    piezas.append(vivo)

    informe = [
        f"Remera · pecho {pecho} cm + holgura {holgura} cm · largo {largo_total} cm",
        f"Sisa: delantero {sisa_del:.1f} cm + espalda {sisa_esp:.1f} cm = {sisa_total:.1f} cm",
        f"Copa de manga: alto {ch:.1f} cm, curva {objetivo:.1f} cm (embebido {embebido} cm)",
        f"Escote total {escote_total:.1f} cm → vivo de {L} cm",
    ] + avisos
    return piezas, informe


# --------------------------------------------------------------- falda circular

def falda_circular(cintura=70, largo_falda=55, vuelo=360, pretina=4, **_):
    """Falda circular (360°) o semicircular (180°) con pretina."""
    frac = 1.0 if vuelo >= 270 else 0.5
    r = cintura / (2 * math.pi * frac)
    R = r + largo_falda
    # cada pieza = un cuarto de círculo, cortada al doblez
    n = 64
    ext = [(R * math.cos(t), R * math.sin(t)) for t in
           (i * (math.pi / 2) / n for i in range(n + 1))]
    inte = [(r * math.cos(t), r * math.sin(t)) for t in
            (i * (math.pi / 2) / n for i in range(n, -1, -1))]
    contorno = ext + inte
    cortes = 2 if frac == 1.0 else 1
    p = Pieza("Falda", contorno,
              cortar=f"Cortar {cortes} al doblez" if cortes > 1 else "Cortar 1 al doblez",
              doblez=((0, r), (0, R)), hilo=((R * 0.6, R * 0.25), (R * 0.6, R * 0.55)),
              color=LILA)
    # con 1 pieza (semicircular) el otro borde recto es costura (centro espalda)
    p.marcas.append(marca_en(p, r + largo_falda / 2, 0, "A"))
    p.notas.append(f"radio cintura {r:.1f} cm")
    piezas = [p]
    L = cintura + 3
    pre = Pieza("Pretina", [(0, 0), (L, 0), (L, pretina * 2), (0, pretina * 2)],
                cortar="Cortar 1 (+ entretela)",
                hilo=((L * 0.15, pretina), (L * 0.15 + 4, pretina)), color=ROSA)
    pre.notas.append("doblar al medio · 3 cm de cruce")
    piezas.append(pre)
    informe = [
        f"Falda {'circular' if frac == 1 else 'semicircular'} · cintura {cintura} cm · "
        f"largo {largo_falda} cm",
        f"Radio de cintura {r:.1f} cm · radio total {R:.1f} cm",
        "El margen del ruedo es el mismo que el resto; dejá colgar la falda 24 h antes de emparejar.",
    ]
    if R > 90:
        informe.append("Aviso: la pieza mide más de 90 cm; puede no entrar en telas de 1,50 m al doblez.")
    return piezas, informe


# ---------------------------------------------------------------- registro

PRENDAS = {
    "remera": {
        "nombre": "Remera básica",
        "funcion": remera,
        "margen": 1.0,
        "params": [
            ("pecho", "Contorno de pecho", 96),
            ("largo_total", "Largo total (desde el cuello)", 68),
            ("hombros", "Ancho de hombros (punta a punta)", 44),
            ("cuello", "Contorno de cuello", 38),
            ("largo_manga", "Largo de manga", 20),
            ("brazo", "Contorno de brazo", 30),
            ("holgura", "Holgura total de pecho", 10),
        ],
    },
    "falda_circular": {
        "nombre": "Falda circular",
        "funcion": falda_circular,
        "margen": 1.0,
        "params": [
            ("cintura", "Contorno de cintura", 70),
            ("largo_falda", "Largo de falda", 55),
            ("vuelo", "Vuelo: 360 (circular) o 180 (semicircular)", 360),
            ("pretina", "Alto de pretina terminada", 4),
        ],
    },
}


def generar(prenda: str, medidas: dict):
    spec = PRENDAS[prenda]
    kw = {k: float(medidas.get(k, d)) for k, _, d in spec["params"]}
    return spec["funcion"](**kw)
