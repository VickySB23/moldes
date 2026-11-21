"""Modelado con formas simples para peluches, como si fuera plastilina.

Cada forma (esfera, cápsula, cilindro, cono, caja, toroide) es una superficie
implícita (SDF). Las formas "unidas" se funden con una unión suave, las "aparte"
quedan como piezas sueltas (orejas, cola) y las de "restar" ahuecan. La malla se
arma con *surface nets* sobre una grilla, todo con numpy.

Unidades: cm. Eje Y hacia ARRIBA (como en la vista 3D); el muñeco mira hacia +Z.
Rotaciones en grados, orden XYZ (igual que three.js).
"""
from __future__ import annotations

import json
import math

import numpy as np

FORMATO = "moldes-formas"
TIPOS = {
    "esfera": "Esfera / huevo",
    "capsula": "Cápsula (salchicha)",
    "cilindro": "Cilindro",
    "cono": "Cono redondeado",
    "caja": "Caja redondeada",
    "toro": "Toroide (dona)",
}
MODOS = {"unir": "Unida al cuerpo", "aparte": "Pieza aparte", "restar": "Restar (ahuecar)"}
RESOLUCION = {"baja": 34, "media": 50, "alta": 70}


# ------------------------------------------------------------------ SDF de cada forma

def _rot(rx, ry, rz):
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def _num(v, defecto=0.0):
    try:
        x = float(v)
        return x if math.isfinite(x) else defecto
    except (TypeError, ValueError):
        return defecto


def _vec(v, defecto):
    v = list(v or [])
    return np.array([_num(v[i], defecto[i]) if i < len(v) else defecto[i] for i in range(3)], float)


class Forma:
    def __init__(self, d: dict, espejada: bool = False):
        self.nombre = str(d.get("nombre") or TIPOS.get(d.get("tipo"), "Forma"))
        self.tipo = d.get("tipo", "esfera") if d.get("tipo") in TIPOS else "esfera"
        self.modo = d.get("modo", "unir") if d.get("modo") in MODOS else "unir"
        self.pos = _vec(d.get("pos"), [0, 0, 0])
        self.tam = np.maximum(_vec(d.get("tam"), [10, 10, 10]), 0.2)
        rot = _vec(d.get("rot"), [0, 0, 0])
        self.afinado = min(max(_num(d.get("afinado"), 0.35), 0.0), 1.0)
        sv = d.get("suavidad")
        self.suavidad = None if sv in (None, "") else max(_num(sv, 0), 0.0)
        if espejada:
            self.pos[0] = -self.pos[0]
            rot = np.array([rot[0], -rot[1], -rot[2]])
        self.R = _rot(*rot)
        self.espejada = espejada

    def radio_envolvente(self):
        return float(np.linalg.norm(self.tam) / 2)

    def sdf(self, P):
        """Distancia (aprox.) con signo: negativa adentro. P: (n, 3)."""
        q = (P - self.pos) @ self.R          # a coordenadas locales
        sx, sy, sz = self.tam / 2
        t = self.tipo
        if t == "esfera":
            r = np.array([sx, sy, sz])
            k0 = np.linalg.norm(q / r, axis=1)
            k1 = np.linalg.norm(q / (r * r), axis=1)
            d = k0 * (k0 - 1) / np.maximum(k1, 1e-9)
            return np.where(k1 < 1e-9, -float(r.min()), d)
        if t == "capsula":
            r = (sx + sz) / 2
            q = q * np.array([r / sx, 1, r / sz])
            h = max(sy - r, 0.0)
            y = q[:, 1] - np.clip(q[:, 1], -h, h)
            return np.sqrt(q[:, 0] ** 2 + y ** 2 + q[:, 2] ** 2) - r
        if t == "cilindro":
            r = (sx + sz) / 2
            q = q * np.array([r / sx, 1, r / sz])
            e = min(r, sy) * 0.3
            dx = np.hypot(q[:, 0], q[:, 2]) - r + e
            dy = np.abs(q[:, 1]) - sy + e
            fuera = np.hypot(np.maximum(dx, 0), np.maximum(dy, 0))
            return np.minimum(np.maximum(dx, dy), 0) + fuera - e
        if t == "cono":
            r1 = (sx + sz) / 2
            q = q * np.array([r1 / sx, 1, r1 / sz])
            r2 = max(r1 * self.afinado, 0.15)
            h = max(2 * sy - r1 - r2, 0.01)
            # cono redondeado (Inigo Quilez): base abajo en y = -sy + r1
            y = q[:, 1] + sy - r1
            xz = np.hypot(q[:, 0], q[:, 2])
            b = (r1 - r2) / h
            a = math.sqrt(max(1 - b * b, 1e-9))
            k = -xz * b + y * a  # dot(q, (-b, a))
            d1 = np.hypot(xz, y) - r1
            d2 = np.hypot(xz, y - h) - r2
            d3 = xz * a + y * b - r1
            return np.where(k < 0, d1, np.where(k > a * h, d2, d3))
        if t == "caja":
            b = np.array([sx, sy, sz])
            e = float(min(b) * 0.35)
            d = np.abs(q) - b + e
            return np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(axis=1), 0) - e
        if t == "toro":
            tubo = max(sy, 0.1)
            R = max(sx - tubo, 0.1)
            return np.hypot(np.hypot(q[:, 0], q[:, 2]) - R, q[:, 1]) - tubo
        raise ValueError(t)


def _smin(a, b, k):
    if k <= 1e-9:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0, 1)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _smax(a, b, k):
    return -_smin(-a, -b, k)


class Grupo:
    """Un cuerpo que se malla por separado (el cuerpo unido, o una forma aparte)."""

    def __init__(self, nombre, unir, restar, k):
        self.nombre = nombre
        self.unir = unir
        self.restar = restar
        self.k = k

    def sdf(self, P):
        d = None
        for f in self.unir:
            ds = f.sdf(P)
            d = ds if d is None else _smin(d, ds, self.k if f.suavidad is None else f.suavidad)
        for f in self.restar:
            d = _smax(d, -f.sdf(P), self.k if f.suavidad is None else f.suavidad)
        return d

    def forma_cercana(self, P):
        """Índice (en self.unir) de la forma más cercana a cada punto."""
        D = np.stack([f.sdf(P) for f in self.unir], axis=1)
        return D.argmin(axis=1)

    def caja(self):
        lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
        for f in self.unir:
            r = f.radio_envolvente()
            lo = np.minimum(lo, f.pos - r)
            hi = np.maximum(hi, f.pos + r)
        return lo, hi


# ------------------------------------------------------------------ surface nets

_ESQ = np.array([(i, j, k) for k in (0, 1) for j in (0, 1) for i in (0, 1)])
_ARISTAS = [(a, b) for a in range(8) for b in range(a + 1, 8) if np.abs(_ESQ[a] - _ESQ[b]).sum() == 1]


def surface_nets(D, origen, h):
    """Malla (V, F) de la superficie D = 0 sobre una grilla regular."""
    nx, ny, nz = D.shape
    c = [D[i:nx - 1 + i, j:ny - 1 + j, k:nz - 1 + k] for i, j, k in _ESQ]
    suma = np.zeros((nx - 1, ny - 1, nz - 1, 3))
    cuenta = np.zeros((nx - 1, ny - 1, nz - 1))
    for a, b in _ARISTAS:
        da, db = c[a], c[b]
        m = (da < 0) != (db < 0)
        if not m.any():
            continue
        t = np.where(m, da / np.where(m, da - db, 1), 0)
        for ax in range(3):
            suma[..., ax] += m * (_ESQ[a][ax] + t * (_ESQ[b][ax] - _ESQ[a][ax]))
        cuenta += m
    activas = cuenta > 0
    vid = np.full(activas.shape, -1, np.int64)
    idx = np.argwhere(activas)
    vid[activas] = np.arange(len(idx))
    V = origen + (idx + suma[activas] / cuenta[activas][:, None]) * h

    quads = []
    adentro = D < 0
    # aristas en X: celdas alrededor en el plano (y, z)
    m = adentro[:-1, 1:-1, 1:-1] != adentro[1:, 1:-1, 1:-1]
    i, j, k = np.nonzero(m)
    j, k = j + 1, k + 1
    q = np.stack([vid[i, j - 1, k - 1], vid[i, j, k - 1], vid[i, j, k], vid[i, j - 1, k]], 1)
    quads.append(np.where(adentro[i, j, k][:, None], q, q[:, ::-1]))
    # aristas en Y: plano (z, x)
    m = adentro[1:-1, :-1, 1:-1] != adentro[1:-1, 1:, 1:-1]
    i, j, k = np.nonzero(m)
    i, k = i + 1, k + 1
    q = np.stack([vid[i - 1, j, k - 1], vid[i - 1, j, k], vid[i, j, k], vid[i, j, k - 1]], 1)
    quads.append(np.where(adentro[i, j, k][:, None], q, q[:, ::-1]))
    # aristas en Z: plano (x, y)
    m = adentro[1:-1, 1:-1, :-1] != adentro[1:-1, 1:-1, 1:]
    i, j, k = np.nonzero(m)
    i, j = i + 1, j + 1
    q = np.stack([vid[i - 1, j - 1, k], vid[i, j - 1, k], vid[i, j, k], vid[i - 1, j, k]], 1)
    quads.append(np.where(adentro[i, j, k][:, None], q, q[:, ::-1]))
    Q = np.concatenate(quads)
    Q = Q[(Q >= 0).all(1)]
    return V, Q


def _triangular(V, Q):
    """Parte cada cuadrilátero por su diagonal más corta."""
    d02 = np.linalg.norm(V[Q[:, 0]] - V[Q[:, 2]], axis=1)
    d13 = np.linalg.norm(V[Q[:, 1]] - V[Q[:, 3]], axis=1)
    a = d02 <= d13
    F = np.concatenate([
        np.stack([Q[a, 0], Q[a, 1], Q[a, 2]], 1), np.stack([Q[a, 0], Q[a, 2], Q[a, 3]], 1),
        np.stack([Q[~a, 0], Q[~a, 1], Q[~a, 3]], 1), np.stack([Q[~a, 1], Q[~a, 2], Q[~a, 3]], 1),
    ])
    return F


def _proyectar(V, sdf, h, pasos=2):
    """Acerca los vértices a la superficie exacta (mejora las curvas)."""
    e = h * 0.1
    for _ in range(pasos):
        d = sdf(V)
        g = np.stack([(sdf(V + np.eye(3)[a] * e) - sdf(V - np.eye(3)[a] * e)) / (2 * e) for a in range(3)], 1)
        g2 = np.maximum((g * g).sum(1), 1e-9)
        paso = (d / g2)[:, None] * g
        n = np.linalg.norm(paso, axis=1)
        lim = np.minimum(1, (0.5 * h) / np.maximum(n, 1e-12))
        V = V - paso * lim[:, None]
    return V


def _sin_burbujas(V, F):
    """Quita cáscaras internas o diminutas (restos numéricos de la grilla)."""
    n = len(V)
    padre = np.arange(n)

    def raiz(a):
        while padre[a] != a:
            padre[a] = padre[padre[a]]
            a = padre[a]
        return a

    for a, b in np.concatenate([F[:, [0, 1]], F[:, [1, 2]]]):
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[ra] = rb
    r = np.array([raiz(v) for v in F[:, 0]])
    vols = np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]]))
    etiquetas, inv = np.unique(r, return_inverse=True)
    vol = np.bincount(inv, weights=vols)
    cnt = np.bincount(inv)
    mayor = vol.max()
    signo = 1 if abs(vol.max()) >= abs(vol.min()) else -1
    ok = (vol * signo > 0.01 * abs(mayor)) & (cnt >= 20)
    return F[ok[inv]]


def _mallar(grupo: Grupo, n_celdas: int, simetrico: bool):
    lo, hi = grupo.caja()
    k = grupo.k + 1.0
    lo, hi = lo - k, hi + k
    if simetrico:
        m = max(abs(lo[0]), abs(hi[0]))
        lo[0], hi[0] = -m, m
    h = float((hi - lo).max() / n_celdas)
    n = np.ceil((hi - lo) / h).astype(int) + 3
    if simetrico and n[0] % 2 == 0:
        n[0] += 1
    centro = (lo + hi) / 2
    if simetrico:
        centro[0] = 0.0
    origen = centro - (n - 1) * h / 2
    xs = [origen[a] + np.arange(n[a]) * h for a in range(3)]
    X, Y, Z = np.meshgrid(*xs, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    D = grupo.sdf(P).reshape(n)
    if not (D < 0).any():
        return None
    V, Q = surface_nets(D, origen, h)
    if not len(Q):
        return None
    F = _triangular(V, Q)
    V = _proyectar(V, grupo.sdf, h)
    # orientación hacia afuera (volumen positivo)
    vol = np.einsum("ij,ij->i", V[F[:, 0]], np.cross(V[F[:, 1]], V[F[:, 2]])).sum()
    if vol < 0:
        F = F[:, ::-1]
    F = _sin_burbujas(V, F)
    # sacar vértices sin usar
    usados = np.unique(F)
    nuevo = np.full(len(V), -1)
    nuevo[usados] = np.arange(len(usados))
    return V[usados], nuevo[F], h


# ------------------------------------------------------------------ API

def cargar(texto_o_dict) -> dict:
    d = json.loads(texto_o_dict) if isinstance(texto_o_dict, str) else texto_o_dict
    if not isinstance(d, dict):
        raise ValueError("No es un modelo de formas.")
    return d


def _es_simetrico(formas):
    """¿Las formas unidas forman un cuerpo simétrico respecto de X = 0?"""
    for f in formas:
        if f.espejada:
            continue
        if abs(f.pos[0]) > 1e-6 and not getattr(f, "tiene_espejo", False):
            return False
    return True


def mallar(texto_o_dict):
    """Devuelve V (n,3), F (m,3), nombres de grupo y grupo de cada cara."""
    d = cargar(texto_o_dict)
    k = max(_num(d.get("suavidad"), 2.0), 0.0)
    n_celdas = RESOLUCION.get(d.get("resolucion", "media"), RESOLUCION["media"])
    unir, restar, aparte = [], [], []
    for fd in d.get("formas", []):
        if fd.get("oculta"):
            continue
        copias = [Forma(fd)]
        if fd.get("espejo") and abs(_num((fd.get("pos") or [0])[0])) > 1e-6:
            copias[0].tiene_espejo = True
            copias.append(Forma(fd, espejada=True))
        for f in copias:
            {"unir": unir, "restar": restar, "aparte": aparte}[f.modo].append(f)
    if not unir and not aparte:
        raise ValueError("Agregá al menos una forma.")

    Vs, Fs, gcara, nombres = [], [], [], []
    base = 0

    def agregar(V, F, etiquetas):
        nonlocal base
        Vs.append(V)
        Fs.append(F + base)
        base += len(V)
        for e in etiquetas:
            if e not in nombres:
                nombres.append(e)
        gcara.append(np.array([nombres.index(e) for e in etiquetas], int))

    if unir:
        g = Grupo("Cuerpo", unir, restar, k)
        r = _mallar(g, n_celdas, _es_simetrico(unir))
        if r:
            V, F, h = r
            cent = V[F].mean(axis=1)
            cerca = g.forma_cercana(cent)
            agregar(V, F, [unir[i].nombre for i in cerca])
    # formas aparte: se mallan solas (las espejadas se copian exactas)
    hechas = {}
    for f in aparte:
        clave = id(f) if not f.espejada else None
        if f.espejada:
            # buscar la original ya mallada
            orig = next((o for o in aparte if not o.espejada and o.nombre == f.nombre
                         and np.allclose(o.tam, f.tam) and np.allclose(o.pos[1:], f.pos[1:])
                         and abs(o.pos[0] + f.pos[0]) < 1e-6), None)
            if orig is not None and id(orig) in hechas:
                V, F = hechas[id(orig)]
                Vm = V * np.array([-1, 1, 1])
                agregar(Vm, F[:, ::-1], [f.nombre] * len(F))
                continue
        g = Grupo(f.nombre, [f], [x for x in restar], k)
        r = _mallar(g, max(16, int(n_celdas * 0.7)), False)
        if r:
            V, F, _ = r
            if clave:
                hechas[clave] = (V, F)
            agregar(V, F, [f.nombre] * len(F))
    if not Vs:
        raise ValueError("Las formas no generan ninguna superficie (¿restaste todo?).")
    V = np.concatenate(Vs)
    F = np.concatenate(Fs)
    return V, F, nombres, np.concatenate(gcara)


def mallar_json(texto_o_dict) -> dict:
    V, F, nombres, gcara = mallar(texto_o_dict)
    lo, hi = V.min(0), V.max(0)
    return {
        "posiciones": np.round(V, 4).ravel().tolist(),
        "caras": F.ravel().tolist(),
        "grupos": nombres,
        "grupo_cara": gcara.tolist(),
        "alto": round(float(hi[1] - lo[1]), 2),
        "ancho": round(float(hi[0] - lo[0]), 2),
        "fondo": round(float(hi[2] - lo[2]), 2),
    }


def a_obj(texto_o_dict) -> str:
    """OBJ con un grupo por forma (para usar el modelo en otro programa)."""
    V, F, nombres, gcara = mallar(texto_o_dict)
    lineas = ["# Modelo hecho con formas en Moldes"]
    lineas += [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in V]
    for gi, nombre in enumerate(nombres):
        lineas.append(f"g {nombre}")
        for a, b, c in F[gcara == gi] + 1:
            lineas.append(f"f {a} {b} {c}")
    return "\n".join(lineas) + "\n"


def esquema() -> dict:
    return {"tipos": TIPOS, "modos": MODOS, "resoluciones": list(RESOLUCION)}
