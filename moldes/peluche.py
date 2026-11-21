"""De modelo 3D (.obj) a molde de peluche.

Cómo se definen las piezas (modo 'auto' elige solo):
  * 'grupos'     -> cada grupo/objeto del OBJ (g / o) es una pieza.
  * 'materiales' -> cada material (usemtl) es una pieza.
  * 'uv'         -> cada isla UV es una pieza (en Blender: marcar costuras + Unwrap).
  * 'partes'     -> cada parte suelta (no conectada) es una pieza.
  * 'editor'     -> piezas marcadas en la vista 3D de la página: cada grupo es una
                    pieza y los cortes vienen como vértices UV distintos (no se sueldan).
Dentro de cada pieza, las partes no conectadas se separan solas.
"""
from __future__ import annotations

import math
import string
from collections import defaultdict

import numpy as np

from .aplanar import aplanar, distorsion
from .pieza import Marca, Pieza, marca_en

COLORES = ["#cfe8b0", "#f6c9d6", "#c4def4", "#f8e7a6", "#ddd0f2", "#f9d3b4",
           "#bfe7dc", "#e8d5b5", "#d9e3a5", "#f2c0c0", "#c9cdf2", "#e2e2e2"]


# ------------------------------------------------------------------ OBJ

class Malla:
    def __init__(self):
        self.V: list = []
        self.VT: list = []
        self.caras_v: list = []    # triángulos (índices de vértice)
        self.caras_vt: list = []   # triángulos (índices UV o -1)
        self.grupo: list = []      # nombre de grupo por triángulo
        self.material: list = []


def leer_obj(texto: str) -> Malla:
    m = Malla()
    grupo, material = "pieza", "sin_material"
    for linea in texto.splitlines():
        if not linea or linea[0] == "#":
            continue
        partes = linea.split()
        if not partes:
            continue
        t = partes[0]
        if t == "v":
            m.V.append([float(x) for x in partes[1:4]])
        elif t == "vt":
            m.VT.append([float(x) for x in partes[1:3]])
        elif t in ("g", "o"):
            grupo = " ".join(partes[1:]) or "pieza"
        elif t == "usemtl":
            material = " ".join(partes[1:]) or "sin_material"
        elif t == "f":
            vs, vts = [], []
            for p in partes[1:]:
                idx = p.split("/")
                vi = int(idx[0])
                vs.append(vi - 1 if vi > 0 else len(m.V) + vi)
                if len(idx) > 1 and idx[1]:
                    ti = int(idx[1])
                    vts.append(ti - 1 if ti > 0 else len(m.VT) + ti)
                else:
                    vts.append(-1)
            for k in range(1, len(vs) - 1):  # abanico
                m.caras_v.append([vs[0], vs[k], vs[k + 1]])
                m.caras_vt.append([vts[0], vts[k], vts[k + 1]])
                m.grupo.append(grupo)
                m.material.append(material)
    if not m.caras_v:
        raise ValueError("El archivo no tiene caras (f). ¿Es un OBJ válido?")
    return m


# ------------------------------------------------------------------ utilidades

class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def _soldar(V, tol=1e-6):
    """Índice 'soldado' por posición (vértices duplicados en costuras)."""
    V = np.asarray(V, float)
    escala = max(float(np.ptp(V, axis=0).max()), 1e-9)
    q = np.round(V / (escala * tol)).astype(np.int64)
    _, inv = np.unique(q, axis=0, return_inverse=True)
    return inv.reshape(-1)


def _componentes(caras, claves):
    """Agrupa triángulos conectados por aristas (según las claves de vértice)."""
    uf = _UF(len(caras))
    arista_a_cara = {}
    for fi, f in enumerate(caras):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            e = tuple(sorted((claves[fi][a], claves[fi][b])))
            if e in arista_a_cara:
                uf.union(arista_a_cara[e], fi)
            else:
                arista_a_cara[e] = fi
    comp = defaultdict(list)
    for fi in range(len(caras)):
        comp[uf.find(fi)].append(fi)
    return list(comp.values())


def _lazos_borde(F):
    """Lazos de borde ordenados (listas de índices locales)."""
    cuenta = defaultdict(int)
    dirigida = {}
    for f in F:
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            cuenta[tuple(sorted((a, b)))] += 1
            dirigida[(a, b)] = True
    sig = {}
    for (a, b) in dirigida:
        if cuenta[tuple(sorted((a, b)))] == 1:
            sig[a] = b
    lazos, vistos = [], set()
    for inicio in list(sig):
        if inicio in vistos:
            continue
        lazo, v = [], inicio
        while v not in vistos and v in sig:
            vistos.add(v)
            lazo.append(v)
            v = sig[v]
        if len(lazo) >= 3:
            lazos.append(lazo)
    lazos.sort(key=len, reverse=True)
    return lazos


def _letras():
    for n in range(1, 3):
        for t in __import__("itertools").product(string.ascii_uppercase, repeat=n):
            yield "".join(t)


# ------------------------------------------------------------------ principal

def molde_peluche(texto_obj: str, altura_cm: float = 30.0, eje: str = "y",
                  modo: str = "auto", iteraciones: int = 15, nombre_base: str = ""):
    """Devuelve (piezas, informe, vista3d)."""
    if not altura_cm or altura_cm <= 0:
        raise ValueError("La altura tiene que ser mayor que 0 cm.")
    m = leer_obj(texto_obj)
    V = np.asarray(m.V, float)
    Fv = np.asarray(m.caras_v, int)
    Fvt = np.asarray(m.caras_vt, int)
    ieje = {"x": 0, "y": 1, "z": 2}[eje.lower()]
    alto = float(np.ptp(V[np.unique(Fv)][:, ieje]))
    if alto <= 0:
        raise ValueError("El modelo no tiene altura en el eje elegido.")
    esc = altura_cm / alto
    V = V * esc
    soldado = _soldar(V)

    tiene_uv = (Fvt >= 0).all() and len(m.VT) > 0
    grupos = sorted(set(m.grupo))
    materiales = sorted(set(m.material))
    if modo == "auto" and "# moldes:editor" in texto_obj[:200] and tiene_uv:
        modo = "editor"
    if modo == "auto":
        if len(grupos) > 1:
            modo = "grupos"
        elif len(materiales) > 1:
            modo = "materiales"
        elif tiene_uv:
            modo = "uv"
        else:
            modo = "partes"
    if modo in ("uv", "editor") and not tiene_uv:
        raise ValueError("El modelo no tiene coordenadas UV; usá otro modo.")

    # 1) segmentación
    if modo in ("grupos", "editor"):
        etiquetas = m.grupo
    elif modo == "materiales":
        etiquetas = m.material
    else:
        etiquetas = ["pieza"] * len(Fv)
    if modo in ("uv", "editor"):
        claves_cara = [[(int(Fv[i, k]), int(Fvt[i, k])) for k in range(3)] for i in range(len(Fv))]
    else:
        claves_cara = [[int(soldado[Fv[i, k]]) for k in range(3)] for i in range(len(Fv))]

    por_etiqueta = defaultdict(list)
    for i, e in enumerate(etiquetas):
        por_etiqueta[e].append(i)

    segmentos = []
    for e in sorted(por_etiqueta, key=lambda s: (len(s), s)):
        idx = por_etiqueta[e]
        comps = _componentes([Fv[i] for i in idx], [claves_cara[i] for i in idx])
        comps.sort(key=len, reverse=True)
        for k, c in enumerate(comps):
            caras = [idx[j] for j in c]
            if len(caras) < 2:
                continue
            nombre = e if len(comps) == 1 else f"{e} {k+1}"
            if modo in ("uv", "partes"):
                nombre = f"{nombre_base or 'Pieza'} {len(segmentos)+1}"
            segmentos.append((nombre, caras))

    arriba = np.zeros(3)
    arriba[ieje] = 1.0
    abajo = -arriba

    piezas, datos, avisos = [], [], []
    vista_pos, vista_col = [], []
    for si, (nombre, caras) in enumerate(segmentos):
        claves = [claves_cara[i] for i in caras]
        mapa, Vl, sold_l = {}, [], []
        Fl = []
        for fi, f in zip(caras, claves):
            tri = []
            for k, key in enumerate(f):
                if key not in mapa:
                    mapa[key] = len(Vl)
                    vi = Fv[fi, k]
                    Vl.append(V[vi])
                    sold_l.append(int(soldado[vi]))
                tri.append(mapa[key])
            Fl.append(tri)
        Vl = np.asarray(Vl)
        Fl = np.asarray(Fl, int)
        lazos = _lazos_borde(Fl)
        color = COLORES[si % len(COLORES)]
        tri3d = Vl[Fl].reshape(-1, 3)
        vista_pos.append(tri3d)
        vista_col.append(np.repeat([color], len(Fl)))
        if not lazos:
            avisos.append(f"«{nombre}» es una superficie cerrada (sin costura): "
                          "agregale al menos una costura para poder aplanarla. Se omitió.")
            continue
        if len(lazos) > 1:
            avisos.append(f"«{nombre}» tiene forma de tubo o agujeros ({len(lazos)} bordes): "
                          "conviene agregar una costura a lo largo.")
        uv = aplanar(Vl, Fl, iteraciones)
        media, maxima, inv = distorsion(Vl, Fl, uv)
        if media > 6 or maxima > 20:
            avisos.append(f"«{nombre}» se deforma bastante al aplanar (medio {media:.0f} %, "
                          f"máx {maxima:.0f} %): sumá una pinza o costura.")
        if inv:
            avisos.append(f"«{nombre}»: {inv} triángulos se superponen al aplanar.")
        # el aplanado estira un poco los bordes de las piezas curvas: se escala
        # la pieza para que las costuras midan lo mismo que en el modelo 3D
        p3 = sum(np.linalg.norm(Vl[l] - Vl[np.roll(l, -1)], axis=1).sum() for l in map(np.array, lazos))
        p2 = sum(np.linalg.norm(uv[l] - uv[np.roll(l, -1)], axis=1).sum() for l in map(np.array, lazos))
        if p2 > 0:
            uv *= p3 / p2

        # dirección del pelo/hilo: "hacia abajo" del muñeco proyectado al plano
        g = _direccion_abajo(Vl, Fl, uv, abajo)
        P2 = np.column_stack([uv[:, 0], -uv[:, 1]])  # Y hacia abajo, vista del derecho
        g = np.array([g[0], -g[1]])
        if np.linalg.norm(g) < 0.3:
            # pieza casi horizontal (tapa): usamos el eje más largo
            c = P2 - P2.mean(0)
            _, _, vt = np.linalg.svd(c, full_matrices=False)
            g = vt[0]
        g = g / (np.linalg.norm(g) or 1)
        ang = math.degrees(math.atan2(g[0], g[1]))  # girar para que g apunte a +Y
        c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        R = np.array([[c, -s], [s, c]])
        P2 = P2 @ R.T

        exterior = [tuple(P2[i]) for i in lazos[0]]
        agujeros = [[tuple(P2[i]) for i in l] for l in lazos[1:]]
        if modo == "editor":
            exterior = _limpiar_contorno(exterior)
        pz = Pieza(nombre, exterior, agujeros=agujeros, cortar="Cortar 1", color=color,
                   texto_hilo="PELO / HILO")
        if media > 0:
            pz.notas.append(f"deformación {media:.1f} %")
        minx, miny = P2.min(0)
        maxx, maxy = P2.max(0)
        cx, cy = pz.punto_etiqueta()
        lh = min(6.0, (maxy - miny) * 0.35)
        pz.hilo = ((cx, cy + 1.2), (cx, cy + 1.2 + lh)) if lh > 1.5 else None
        piezas.append(pz)
        datos.append({"pieza": pz, "P2": P2, "lazos": lazos, "sold": np.asarray(sold_l), "V": Vl})

    _letras_union(datos, avisos)

    # informe
    informe = [f"Molde de {altura_cm:.1f} cm de alto (piezas incluidas) · {len(piezas)} piezas · modo de piezas: {modo}",
               "Piezas vistas desde el DERECHO de la tela; la flecha indica el sentido del pelo "
               "(hacia abajo del muñeco).",
               "Las letras iguales se cosen entre sí, haciendo coincidir los piquetes."]
    informe += avisos

    vista = {
        "posiciones": np.concatenate(vista_pos).round(3).reshape(-1).tolist() if vista_pos else [],
        "colores": np.concatenate(vista_col).tolist() if vista_col else [],
        "eje": eje.lower(),
    }
    return piezas, informe, vista


def _limpiar_contorno(pts, r=0.35):
    """Saca astillas y escalones finos del borde (piezas cortadas en la vista 3D)."""
    from shapely.geometry import Polygon
    try:
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        q = p.buffer(-r, join_style="round").buffer(r, join_style="round")
        q = q.buffer(r * 0.5, join_style="round").buffer(-r * 0.5, join_style="round")
        if q.geom_type != "Polygon" or q.is_empty or abs(q.area - p.area) > 0.04 * p.area:
            return pts
        return list(q.simplify(0.03).exterior.coords)[:-1]
    except Exception:   # noqa: BLE001
        return pts


def _direccion_abajo(V, F, uv, abajo):
    """Promedio (ponderado por área) de la imagen 2D del vector 'abajo'."""
    v0, v1, v2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1, e2 = v1 - v0, v2 - v0
    n = np.cross(e1, e2)
    area = np.linalg.norm(n, axis=1)
    ok = area > 1e-12
    e1, e2, n, area = e1[ok], e2[ok], n[ok], area[ok]
    Fo = F[ok]
    nu = n / area[:, None]
    d = abajo[None, :] - np.einsum("ij,j->i", nu, abajo)[:, None] * nu  # proyección tangente
    # resolver d = a*e1 + b*e2 (mínimos cuadrados por triángulo)
    E = np.stack([e1, e2], axis=2)  # m,3,2
    EtE = np.einsum("nki,nkj->nij", E, E)
    Etd = np.einsum("nki,nk->ni", E, d)
    det = EtE[:, 0, 0] * EtE[:, 1, 1] - EtE[:, 0, 1] ** 2
    det[np.abs(det) < 1e-18] = 1e-18
    a = (EtE[:, 1, 1] * Etd[:, 0] - EtE[:, 0, 1] * Etd[:, 1]) / det
    b = (EtE[:, 0, 0] * Etd[:, 1] - EtE[:, 0, 1] * Etd[:, 0]) / det
    u0, u1, u2 = uv[Fo[:, 0]], uv[Fo[:, 1]], uv[Fo[:, 2]]
    g = (a[:, None] * (u1 - u0) + b[:, None] * (u2 - u0)) * area[:, None]
    tot = g.sum(0)
    peso = (np.linalg.norm(d, axis=1) * area).sum()
    return tot / max(area.sum(), 1e-12) if peso > 0 else np.zeros(2)


def _letras_union(datos, avisos):
    """Busca bordes compartidos entre piezas y les pone la misma letra + piquetes."""
    # aristas de borde (en claves soldadas) de cada pieza
    bordes = []
    for d in datos:
        aristas = {}
        for lazo in d["lazos"]:
            for k in range(len(lazo)):
                a, b = lazo[k], lazo[(k + 1) % len(lazo)]
                aristas[tuple(sorted((d["sold"][a], d["sold"][b])))] = (a, b)
        bordes.append(aristas)

    gen = _letras()
    for i in range(len(datos)):
        for j in range(i + 1, len(datos)):
            comunes = set(bordes[i]) & set(bordes[j])
            if not comunes:
                continue
            # tramos continuos sobre el lazo de la pieza i
            for tramo in _tramos(datos[i], comunes):
                letra = next(gen)
                _marcar_tramo(datos[i], datos[j], tramo, letra)


def _tramos(d, comunes):
    tramos = []
    for lazo in d["lazos"]:
        n = len(lazo)
        flags = [tuple(sorted((d["sold"][lazo[k]], d["sold"][lazo[(k + 1) % n]]))) in comunes
                 for k in range(n)]
        if all(flags):
            tramos.append(lazo + [lazo[0]])
            continue
        if not any(flags):
            continue
        k0 = flags.index(False)
        actual = []
        for t in range(1, n + 1):
            k = (k0 + t) % n
            if flags[k]:
                if not actual:
                    actual = [lazo[k]]
                actual.append(lazo[(k + 1) % n])
            elif actual:
                tramos.append(actual)
                actual = []
        if actual:
            tramos.append(actual)
    return tramos


def _marcar_tramo(di, dj, tramo, letra):
    """Pone la letra en el medio del tramo y piquetes cada ~10 cm, en ambas piezas."""
    Vi = di["V"]
    largos = [0.0]
    for a, b in zip(tramo[:-1], tramo[1:]):
        largos.append(largos[-1] + float(np.linalg.norm(Vi[b] - Vi[a])))
    total = largos[-1]
    if total < 0.5:
        return
    n_marcas = max(1, int(round(total / 10.0)))
    sold_j = {int(s): k for k, s in enumerate(dj["sold"])}
    for q in range(1, n_marcas + 1):
        objetivo = total * q / (n_marcas + 1)
        k = int(np.argmin([abs(l - objetivo) for l in largos]))
        vi = tramo[k]
        vj = sold_j.get(int(di["sold"][vi]))
        texto = letra if q == (n_marcas + 1) // 2 or n_marcas == 1 else ""
        for d, v in ((di, vi), (dj, vj)):
            if v is None:
                continue
            x, y = d["P2"][v]
            d["pieza"].marcas.append(marca_en(d["pieza"], float(x), float(y), texto))


def analizar(texto_obj: str, iteraciones: int = 4) -> list:
    """Revisión rápida de las piezas (para la vista 3D): bordes y deformación al aplanar."""
    m = leer_obj(texto_obj)
    V = np.asarray(m.V, float)
    Fv = np.asarray(m.caras_v, int)
    Fvt = np.asarray(m.caras_vt, int)
    con_uv = (Fvt >= 0).all() and len(m.VT) > 0
    soldado = _soldar(V)
    if con_uv:
        claves_cara = [[(int(Fv[i, k]), int(Fvt[i, k])) for k in range(3)] for i in range(len(Fv))]
    else:
        claves_cara = [[int(soldado[Fv[i, k]]) for k in range(3)] for i in range(len(Fv))]
    por_grupo = defaultdict(list)
    for i, g in enumerate(m.grupo):
        por_grupo[g].append(i)
    salida = []
    for g, idx in por_grupo.items():
        comps = _componentes([Fv[i] for i in idx], [claves_cara[i] for i in idx])
        res = {"nombre": g, "caras": len(idx), "partes": len(comps), "bordes": 0,
               "media": None, "maxima": None, "invertidos": 0, "estado": "ok"}
        peor = None
        for c in comps:
            caras = [idx[j] for j in c]
            mapa, Vl, Fl = {}, [], []
            for fi in caras:
                tri = []
                for k, key in enumerate(claves_cara[fi]):
                    if key not in mapa:
                        mapa[key] = len(Vl)
                        Vl.append(V[Fv[fi, k]])
                    tri.append(mapa[key])
                Fl.append(tri)
            Vl, Fl = np.asarray(Vl), np.asarray(Fl, int)
            lazos = _lazos_borde(Fl)
            res["bordes"] = max(res["bordes"], len(lazos))
            if not lazos:
                res["estado"] = "cerrada"
                continue
            try:
                uv = aplanar(Vl, Fl, iteraciones)
                media, maxima, inv = distorsion(Vl, Fl, uv)
            except Exception:   # noqa: BLE001
                res["estado"] = "error"
                continue
            if peor is None or media > peor[0]:
                peor = (media, maxima, inv)
        if peor:
            res["media"], res["maxima"], res["invertidos"] = round(peor[0], 1), round(peor[1], 1), peor[2]
        if res["estado"] == "ok":
            if res["bordes"] > 1:
                res["estado"] = "tubo"
            elif peor and (peor[0] > 6 or peor[1] > 20 or peor[2]):
                res["estado"] = "deforma"
        salida.append(res)
    return salida
