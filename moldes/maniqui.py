"""Maniquí a partir de medidas del cuerpo.

El torso es un "loft": secciones elípticas a la altura de los hombros, el busto,
la cintura y la cadera, interpoladas suavemente. El cuello, la cabeza, los brazos
y las piernas son formas (cápsulas, conos, esferas) unidas con suavidad. Después
se mide la malla como con un centímetro (envolvente convexa del corte) y se
corrige hasta que los contornos coinciden con los pedidos.

Unidades: cm, Y hacia arriba, piso en y = 0, el maniquí mira hacia +Z.
"""
from __future__ import annotations

import json
import math

import numpy as np

from .formas import Forma, Grupo, _mallar, RESOLUCION

MEDIDAS = [
    # id, nombre, valor por defecto (mujer talle M)
    ("altura", "Estatura", 165),
    ("busto", "Contorno de busto / pecho", 92),
    ("bajo_busto", "Contorno bajo busto", 76),
    ("cintura", "Contorno de cintura", 72),
    ("cadera", "Contorno de cadera", 98),
    ("cuello", "Contorno de cuello", 35),
    ("hombros", "Ancho de hombros (punta a punta)", 39),
    ("talle", "Talle espalda (nuca a cintura)", 40),
    ("alto_cadera", "Alto de cadera (cintura a cadera)", 20),
    ("entrepierna", "Largo de entrepierna (al piso)", 76),
    ("largo_brazo", "Largo de brazo (hombro a muñeca)", 58),
    ("brazo", "Contorno de brazo", 27),
    ("muslo", "Contorno de muslo", 55),
]

TALLES = {
    "mujer_s": {"nombre": "Mujer talle S", "altura": 162, "busto": 86, "bajo_busto": 72, "cintura": 66,
                "cadera": 92, "cuello": 34, "hombros": 37.5, "talle": 39.5, "alto_cadera": 19.5,
                "entrepierna": 75, "largo_brazo": 57, "brazo": 25.5, "muslo": 52},
    "mujer_m": {"nombre": "Mujer talle M", **{k: v for k, _, v in MEDIDAS}},
    "mujer_l": {"nombre": "Mujer talle L", "altura": 168, "busto": 100, "bajo_busto": 83, "cintura": 80,
                "cadera": 106, "cuello": 36.5, "hombros": 40.5, "talle": 41, "alto_cadera": 20.5,
                "entrepierna": 77, "largo_brazo": 59, "brazo": 29.5, "muslo": 59},
    "hombre_m": {"nombre": "Hombre talle M", "altura": 176, "busto": 98, "bajo_busto": 90, "cintura": 84,
                 "cadera": 98, "cuello": 39, "hombros": 45, "talle": 45, "alto_cadera": 19,
                 "entrepierna": 81, "largo_brazo": 62, "brazo": 31, "muslo": 55},
    "nino_8": {"nombre": "Niña/o 8 años", "altura": 128, "busto": 66, "bajo_busto": 62, "cintura": 58,
               "cadera": 68, "cuello": 29, "hombros": 29, "talle": 30, "alto_cadera": 13,
               "entrepierna": 56, "largo_brazo": 43, "brazo": 19, "muslo": 38},
}

TIPOS = {"completo": "Cuerpo completo (brazos en A)", "torso": "Maniquí de costura (torso)"}
FORMAS_CUERPO = {"femenina": "Femenina (con busto)", "masculina": "Masculina", "neutra": "Neutra"}


def _perim_elipse(a, b):
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def _semiejes(contorno, prop):
    """Semiejes (ancho, profundidad) de una elipse con ese contorno y proporción prof/ancho."""
    a = contorno / _perim_elipse(1.0, prop)
    return a, a * prop


def _pchip(x, y, xq):
    """Interpolación cúbica monótona (sin ondas entre los niveles)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros_like(y)
    for i in range(1, len(y) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0], m[-1] = d[0], d[-1]
    xq = np.clip(xq, x[0], x[-1])
    i = np.clip(np.searchsorted(x, xq) - 1, 0, len(x) - 2)
    t = (xq - x[i]) / h[i]
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * y[i] + h10 * h[i] * m[i] + h01 * y[i + 1] + h11 * h[i] * m[i + 1]


class Loft:
    """Torso: pila de elipses (y, semiancho, semiprofundidad, centro z) con tapas redondeadas."""

    def __init__(self, nombre, niveles, tapa_arriba=5.0, tapa_abajo=4.0):
        niveles = sorted(niveles)
        self.nombre = nombre
        self.y, self.a, self.b, self.c = (np.array(col, float) for col in zip(*niveles))
        self.t_arr, self.t_ab = tapa_arriba, tapa_abajo
        self.suavidad = None
        self.pos = np.array([0.0, (self.y[0] + self.y[-1]) / 2, float(self.c.mean())])
        self._r = float(max(self.a.max(), self.b.max()) + (self.y[-1] - self.y[0]) / 2 + 6)

    def radio_envolvente(self):
        return self._r

    def sdf(self, P):
        x, y, z = P[:, 0], P[:, 1], P[:, 2]
        yc = np.clip(y, self.y[0], self.y[-1])
        a = _pchip(self.y, self.a, yc)
        b = _pchip(self.y, self.b, yc)
        c = _pchip(self.y, self.c, yc)
        # tapas: la sección se achica como un cuarto de elipse
        s = np.ones_like(y)
        arriba = y > self.y[-1]
        abajo = y < self.y[0]
        s[arriba] = np.sqrt(np.clip(1 - ((y[arriba] - self.y[-1]) / self.t_arr) ** 2, 1e-4, 1))
        s[abajo] = np.sqrt(np.clip(1 - ((self.y[0] - y[abajo]) / self.t_ab) ** 2, 1e-4, 1))
        a, b = a * s, b * s
        qx, qz = x / a, (z - c) / b
        k0 = np.hypot(qx, qz)
        k1 = np.hypot(qx / a, qz / b)
        d = np.where(k1 < 1e-9, -np.minimum(a, b), k0 * (k0 - 1) / np.maximum(k1, 1e-9))
        # más allá de las tapas: distancia a la punta
        fuera_arr = y > self.y[-1] + self.t_arr
        fuera_ab = y < self.y[0] - self.t_ab
        if fuera_arr.any():
            d[fuera_arr] = np.maximum(d[fuera_arr], y[fuera_arr] - (self.y[-1] + self.t_arr))
        if fuera_ab.any():
            d[fuera_ab] = np.maximum(d[fuera_ab], (self.y[0] - self.t_ab) - y[fuera_ab])
        return d


def _f(nombre, tipo, pos, tam, rot=(0, 0, 0), afinado=None, suavidad=None, espejada=False):
    d = {"nombre": nombre, "tipo": tipo, "pos": list(pos), "tam": list(tam), "rot": list(rot)}
    if afinado is not None:
        d["afinado"] = afinado
    if suavidad is not None:
        d["suavidad"] = suavidad
    return Forma(d, espejada=espejada)


def _par(nombre, tipo, pos, tam, rot=(0, 0, 0), **kw):
    return [_f(nombre, tipo, pos, tam, rot, **kw), _f(nombre, tipo, pos, tam, rot, espejada=True, **kw)]


def medidas_completas(m: dict) -> dict:
    out = {}
    for k, _, v in MEDIDAS:
        try:
            out[k] = float(m.get(k, v))
        except (TypeError, ValueError):
            raise ValueError(f"La medida «{k}» no es un número.")
        if out[k] <= 0:
            raise ValueError(f"La medida «{k}» tiene que ser mayor que 0.")
    if out["cintura"] > out["cadera"] * 1.3 or out["cintura"] > out["busto"] * 1.3:
        pass  # cuerpos con cintura grande son válidos
    if out["entrepierna"] > out["altura"] * 0.6:
        raise ValueError("La entrepierna es demasiado larga para esa estatura.")
    if out["talle"] > out["altura"] * 0.35:
        raise ValueError("El talle es demasiado largo para esa estatura.")
    return out


def construir(m: dict, tipo="completo", forma="femenina", ajustes=None):
    """Arma el grupo de formas del maniquí. `ajustes` corrige busto/cintura/cadera."""
    aj = {"busto": 1.0, "cintura": 1.0, "cadera": 1.0, **(ajustes or {})}
    H = m["altura"]
    y_nuca = 0.845 * H
    y_hombro = y_nuca - 0.025 * H
    y_cint = y_nuca - m["talle"]
    y_busto = y_nuca - 0.58 * m["talle"]
    y_axila = y_busto + 0.22 * m["talle"]
    y_cad = y_cint - m["alto_cadera"]
    y_entre = m["entrepierna"]
    y_entre = min(y_entre, y_cad - 4)
    fem = forma == "femenina"
    masc = forma == "masculina"

    # secciones del torso (contorno, proporción prof/ancho, adelanto z)
    busto_loft = (m["bajo_busto"] * 1.03 if fem else m["busto"]) * aj["busto"]
    pb = 0.72 if fem else (0.68 if masc else 0.7)
    a_b, b_b = _semiejes(busto_loft, pb)
    a_c, b_c = _semiejes(m["cintura"] * aj["cintura"], 0.74)
    a_k, b_k = _semiejes(m["cadera"] * aj["cadera"], 0.70)
    a_hc, b_hc = _semiejes((m["cintura"] * aj["cintura"] + m["cadera"] * aj["cadera"]) / 2, 0.72)
    a_e, b_e = _semiejes(m["cadera"] * aj["cadera"] * 0.93, 0.72)
    a_sh = max(m["hombros"] / 2 - 4.5, a_b * 0.95)
    niveles = [
        (y_entre + 1.0, a_e, b_e, -0.8),
        (y_cad, a_k, b_k, -1.2),
        ((y_cad + y_cint) / 2, a_hc, b_hc, -0.6),
        (y_cint, a_c, b_c, 0.0),
        ((y_cint + y_busto) / 2, (a_c + a_b) / 2, (b_c + b_b) / 2, 0.2),
        (y_busto, a_b, b_b, 0.3),
        (y_axila, a_sh * 0.97, b_b * 0.98, 0.0),
        (y_hombro - 3.0, a_sh, b_b * 0.78, -0.6),
    ]
    torso = Loft("Torso", niveles, tapa_arriba=5.5, tapa_abajo=0.12 * (y_cad - y_entre) + 3)
    formas = [torso]

    # cuello y hombros
    r_cu = m["cuello"] / (2 * math.pi)
    largo_cuello = 0.035 * H + 4
    formas.append(_f("Cuello", "cilindro", (0, y_nuca + largo_cuello / 2 - 1.5, -0.8),
                     (2 * r_cu, largo_cuello + 3, 2 * r_cu * 0.95), rot=(-8, 0, 0), suavidad=2.5))
    x_hom = m["hombros"] / 2 - 2.0
    for f in _par("Hombro", "capsula", (x_hom * 0.55, y_hombro + 0.8, -1.0),
                  (6.0, x_hom * 0.95, 5.5), rot=(0, 0, 77), suavidad=3.0):
        formas.append(f)

    if fem:
        r_bu = max((m["busto"] - m["bajo_busto"]) * 0.42 + 4.0, 5.0)
        for f in _par("Busto", "esfera", (a_b * 0.42, y_busto + 0.5, b_b * 0.55),
                      (r_bu * 1.25, r_bu * 1.05, r_bu * 1.1), rot=(0, 18, 0), suavidad=3.5):
            formas.append(f)

    if tipo == "completo":
        # cabeza
        formas.append(_f("Cabeza", "esfera", (0, H - 0.066 * H, 0.6), (0.092 * H, 0.135 * H, 0.118 * H),
                         suavidad=2.0))
        # brazos en A (40° desde la vertical)
        r_br = m["brazo"] / (2 * math.pi)
        ang = 40.0
        L1, L2 = m["largo_brazo"] * 0.54, m["largo_brazo"] * 0.46
        hombro = np.array([x_hom, y_hombro - r_br * 0.9, -0.8])
        dirb = np.array([math.sin(math.radians(ang)), -math.cos(math.radians(ang)), 0.0])
        codo = hombro + dirb * L1
        munieca = codo + dirb * L2
        for f in _par("Brazo", "cono", tuple(hombro + dirb * L1 / 2), (2 * r_br, L1 + 2 * r_br, 2 * r_br * 0.95),
                      rot=(0, 0, ang), afinado=0.78, suavidad=2.2):
            formas.append(f)
        for f in _par("Antebrazo", "cono", tuple(codo + dirb * L2 / 2), (2 * r_br * 0.8, L2 + r_br, 2 * r_br * 0.7),
                      rot=(0, 0, ang), afinado=0.62, suavidad=1.5):
            formas.append(f)
        for f in _par("Mano", "esfera", tuple(munieca + dirb * 0.055 * H), (0.032 * H, 0.105 * H, 0.016 * H + 1),
                      rot=(0, 0, ang), suavidad=1.2):
            formas.append(f)
        # piernas
        r_mu = m["muslo"] / (2 * math.pi)
        x_pi = max(a_e - r_mu * 0.95, r_mu * 0.85)
        y_rod = 0.285 * H
        y_tob = 0.045 * H
        largo_muslo = y_entre + 4 - y_rod
        for f in _par("Muslo", "cono", (x_pi, (y_entre + 4 + y_rod) / 2, -0.5),
                      (2 * r_mu, largo_muslo + 2 * r_mu * 0.6, 2 * r_mu), rot=(0, 0, 3), afinado=0.62, suavidad=2.5):
            formas.append(f)
        r_pa = r_mu * 0.66
        for f in _par("Pierna", "cono", (x_pi * 0.92, (y_rod + y_tob) / 2, -1.0),
                      (2 * r_pa, y_rod - y_tob + 2 * r_pa * 0.7, 2 * r_pa), rot=(0, 0, 2), afinado=0.55, suavidad=1.8):
            formas.append(f)
        for f in _par("Pie", "esfera", (x_pi * 0.9, y_tob * 0.55, 3.5), (0.055 * H, 0.05 * H, 0.155 * H),
                      suavidad=1.5):
            formas.append(f)
        k = 2.2
    else:
        # maniquí de costura: arranque de brazos y de piernas, cortado parejo
        k = 2.0
        for f in _par("Brazo", "esfera", (x_hom - 1.5, y_hombro - 6.5, -0.8), (9.0, 12.0, 10.0), suavidad=3.0):
            formas.append(f)
    return Grupo("Maniquí", formas, [], k), {"y_busto": y_busto, "y_cintura": y_cint, "y_cadera": y_cad,
                                             "y_entrepierna": y_entre, "y_nuca": y_nuca,
                                             "y_axila": y_axila, "y_hombro": y_hombro,
                                             "x_hombro": x_hom, "x_axila": a_sh * 0.97,
                                             "centro_z": {"busto": 0.3, "cintura": 0.0, "cadera": -1.2}}


# ------------------------------------------------------------------ medir como con un centímetro

def _envolvente(P):
    """Envolvente convexa 2D (cadena monótona)."""
    P = sorted(set(map(tuple, np.round(P, 5))))
    if len(P) < 3:
        return P

    def cruz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, hi = [], []
    for p in P:
        while len(lo) >= 2 and cruz(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(hi) >= 2 and cruz(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def contorno(V, F, y, centro=(0.0, 0.0), radio_max=None):
    """Contorno 'con centímetro' de la malla a la altura y, del lazo más cercano al centro."""
    d = V[:, 1] - y
    sF = d[F]
    cruza = ((sF > 0).any(1)) & ((sF <= 0).any(1))
    segs = []
    for f, s in zip(F[cruza], sF[cruza]):
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            if (s[a] > 0) != (s[b] > 0):
                t = s[a] / (s[a] - s[b])
                p = V[f[a]] + t * (V[f[b]] - V[f[a]])
                pts.append((p[0], p[2]))
        if len(pts) == 2:
            segs.append(pts)
    if not segs:
        return 0.0
    S = np.array(segs)                      # (n, 2, 2)
    # separar lazos (brazos, piernas) por cercanía al centro
    mid = S.mean(axis=1)
    dist = np.hypot(mid[:, 0] - centro[0], mid[:, 1] - centro[1])
    # lazo central: puntos conectados empezando por el segmento más cercano al centro
    puntos = S.reshape(-1, 2)
    if radio_max is not None:
        puntos = puntos[np.hypot(puntos[:, 0] - centro[0], puntos[:, 1] - centro[1]) <= radio_max]
    else:
        # agrupar por conectividad aproximada
        from collections import defaultdict
        clave = lambda p: (round(p[0], 3), round(p[1], 3))
        vec = defaultdict(list)
        for i, (p, q) in enumerate(S):
            vec[clave(p)].append(i)
            vec[clave(q)].append(i)
        inicio = int(dist.argmin())
        visto, pila = {inicio}, [inicio]
        while pila:
            i = pila.pop()
            for p in S[i]:
                for j in vec[clave(p)]:
                    if j not in visto:
                        visto.add(j)
                        pila.append(j)
        puntos = S[sorted(visto)].reshape(-1, 2)
    hull = _envolvente(puntos)
    if len(hull) < 3:
        return 0.0
    H = np.array(hull)
    return float(np.linalg.norm(H - np.roll(H, -1, axis=0), axis=1).sum())


# ------------------------------------------------------------------ API

def mallar(datos, calibrar: bool = True):
    """datos: {"medidas": {...}, "tipo", "forma", "holgura", "resolucion"}.
    Devuelve V, F, nombres, grupo_cara, informe."""
    if isinstance(datos, str):
        datos = json.loads(datos)
    m = medidas_completas(datos.get("medidas", {}))
    tipo = datos.get("tipo", "completo") if datos.get("tipo") in TIPOS else "completo"
    forma = datos.get("forma", "femenina") if datos.get("forma") in FORMAS_CUERPO else "femenina"
    holgura = max(float(datos.get("holgura", 0) or 0), 0.0)
    n = RESOLUCION.get(datos.get("resolucion", "media"), RESOLUCION["media"])
    n = int(n * 1.45)   # el cuerpo es alto: más celdas para el mismo detalle
    ajustes = {"busto": 1.0, "cintura": 1.0, "cadera": 1.0}
    pedido = {"busto": m["busto"], "cintura": m["cintura"], "cadera": m["cadera"]}
    medido = {}

    def medir(V, F, ref):
        return {k: contorno(V, F, ref["y_" + k], (0.0, ref["centro_z"][k])) for k in pedido}

    def corregir(medido):
        for k in pedido:
            if medido[k] > 0:
                ajustes[k] *= pedido[k] / medido[k]

    def error(medido):
        return max(abs(medido[k] / pedido[k] - 1) for k in pedido)

    # 1) calibración rápida con una malla gruesa
    for _ in range(3 if calibrar else 0):
        grupo, ref = construir(m, tipo, forma, ajustes)
        r = _mallar(grupo, max(44, n // 2), True)
        if r is None:
            raise ValueError("No pude armar el maniquí con esas medidas.")
        medido = medir(r[0], r[1], ref)
        if error(medido) < 0.005:
            break
        corregir(medido)
    # 2) malla final; si todavía difiere, una corrección más a resolución final
    for vuelta in range(2 if calibrar else 1):
        grupo, ref = construir(m, tipo, forma, ajustes)
        r = _mallar(grupo, n, True)
        if r is None:
            raise ValueError("No pude armar el maniquí con esas medidas.")
        V, F, h = r
        medido = medir(V, F, ref)
        if not calibrar or error(medido) < 0.006:
            break
        corregir(medido)
    if holgura > 0:
        # la holgura se reparte en todo el contorno: se infla la superficie
        inflar = holgura / (2 * math.pi)
        base = grupo.sdf
        grupo.sdf = lambda P, base=base: base(P) - inflar
        V, F, h = _mallar(grupo, n, True)
    cent = V[F].mean(axis=1)
    cerca = grupo.forma_cercana(cent)
    nombres_formas = [f.nombre for f in grupo.unir]
    nombres = []
    gcara = []
    for i in cerca:
        nom = nombres_formas[i]
        if nom not in nombres:
            nombres.append(nom)
        gcara.append(nombres.index(nom))
    informe = {k: {"pedido": pedido[k], "medido": round(medido[k], 1)} for k in pedido}
    informe["alto"] = round(float(V[:, 1].max() - V[:, 1].min()), 1)
    informe["niveles"] = {k: round(v, 1) for k, v in ref.items() if k[:2] in ("y_", "x_")}
    informe["holgura"] = holgura
    return V, F, nombres, np.array(gcara, int), informe


def mallar_json(datos) -> dict:
    V, F, nombres, gcara, informe = mallar(datos)
    return {
        "posiciones": np.round(V, 4).ravel().tolist(),
        "caras": F.ravel().tolist(),
        "grupos": nombres,
        "grupo_cara": gcara.tolist(),
        "alto": informe["alto"],
        "informe": informe,
    }


def esquema() -> dict:
    return {"medidas": [{"id": k, "nombre": n, "valor": v} for k, n, v in MEDIDAS],
            "talles": TALLES, "tipos": TIPOS, "formas": FORMAS_CUERPO}
