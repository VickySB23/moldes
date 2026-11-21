"""Prendas personalizadas: moldes que dibujás vos, con fórmulas que usan tus medidas.

Una prenda es un JSON (ver README, sección "Prendas personalizadas") con:

    medidas    valores que se cambian para cada persona       {"id", "nombre", "valor"}
    variables  cuentas intermedias con fórmulas                {"id", "formula"}
    puntos     construidos con herramientas de patronaje       {"id", "tipo", ...campos}
    curvas     Bézier o suaves, pasando por puntos              {"id", "tipo", "puntos"}
    piezas     contorno de puntos y curvas + doblez, hilo,
               piquetes, pinzas y margen por tramo
    controles  cuentas para verificar el molde (p. ej. copa vs. sisa)

Coordenadas en cm. X hacia la derecha, Y hacia ABAJO (como en el papel).
Ángulos en grados: 0 = derecha, 90 = arriba, 180 = izquierda, 270 = abajo.

Las fórmulas son expresiones aritméticas seguras (no se ejecuta código):
    + - * / ** %   paréntesis   números con punto decimal (1.5)
    nombres de medidas y variables
    A.x  A.y              coordenadas del punto A
    dist(A, B)            distancia entre dos puntos
    ang(A, B)             ángulo de A hacia B
    largo(curva)          largo de una curva
    largo(A, B, ...)      largo de una poligonal que pasa por esos puntos
    raiz, sin, cos, tan, asin, acos, atan, atan2 (en grados), abs, min, max,
    redondear(x, decimales), si(condición, valor_si, valor_no), pi
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re

from shapely.geometry import LineString, Point

from .pieza import Pieza, marca_en

FORMATO = "moldes-prenda"
VERSION = 1
ID_VALIDO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COLORES = ["#cfe8b0", "#c4def4", "#f8e7a6", "#f6c9d6", "#ddd0f2", "#fbd5b5", "#c9ece6"]

# ---------------------------------------------------------------------- tipos de punto
# Cada campo es ("nombre", "punto" | "curva" | "formula", "etiqueta")
TIPOS_PUNTO = {
    "xy": {
        "nombre": "Coordenadas (x, y)",
        "campos": [("x", "formula", "x"), ("y", "formula", "y")],
    },
    "desde": {
        "nombre": "Desde otro punto (→ x, ↓ y)",
        "campos": [("base", "punto", "desde"), ("dx", "formula", "→ derecha"),
                   ("dy", "formula", "↓ abajo")],
    },
    "polar": {
        "nombre": "Largo y ángulo",
        "campos": [("base", "punto", "desde"), ("largo", "formula", "largo"),
                   ("angulo", "formula", "ángulo°")],
    },
    "sobre_linea": {
        "nombre": "Sobre una línea (a cierta distancia)",
        "campos": [("a", "punto", "desde"), ("b", "punto", "hacia"), ("largo", "formula", "largo")],
    },
    "medio": {
        "nombre": "Punto medio",
        "campos": [("a", "punto", "entre"), ("b", "punto", "y")],
    },
    "interseccion": {
        "nombre": "Cruce de dos líneas",
        "campos": [("a", "punto", "línea 1: de"), ("b", "punto", "a"),
                   ("c", "punto", "línea 2: de"), ("d", "punto", "a")],
    },
    "pie": {
        "nombre": "Perpendicular desde un punto a una línea",
        "campos": [("base", "punto", "desde"), ("a", "punto", "línea: de"), ("b", "punto", "a")],
    },
    "circulo_linea": {
        "nombre": "Sobre una línea, a cierta distancia de otro punto",
        "campos": [("centro", "punto", "centro"), ("radio", "formula", "distancia"),
                   ("a", "punto", "línea: de"), ("b", "punto", "hacia")],
    },
    "en_curva": {
        "nombre": "Sobre una curva (negativo = desde el final)",
        "campos": [("curva", "curva", "curva"), ("largo", "formula", "largo")],
    },
}

TIPOS_CURVA = {
    "bezier": "Bézier (inicio, control, control, fin)",
    "suave": "Suave (pasa por todos los puntos)",
    "poligonal": "Poligonal (rectas entre los puntos)",
}

ESTILOS_LINEA = {"pinza": "Pinza", "linea": "Línea", "punteada": "Punteada (doblez, referencia)"}


class ErrorPrenda(ValueError):
    def __init__(self, donde: str, mensaje: str, campo: str = ""):
        super().__init__(mensaje)
        self.donde = donde
        self.campo = campo
        self.mensaje = mensaje


# ---------------------------------------------------------------------- fórmulas

_BINARIOS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
             ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod}
_COMPARA = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
            ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}


def _grados(f):
    return lambda x: f(math.radians(x))


def _agrados(f):
    return lambda *a: math.degrees(f(*a))


FUNCIONES = {
    "raiz": math.sqrt, "sqrt": math.sqrt,
    "sin": _grados(math.sin), "cos": _grados(math.cos), "tan": _grados(math.tan),
    "asin": _agrados(math.asin), "acos": _agrados(math.acos),
    "atan": _agrados(math.atan), "atan2": _agrados(math.atan2),
    "abs": abs, "min": min, "max": max,
    "redondear": lambda x, d=0: round(x, int(d)), "round": lambda x, d=0: round(x, int(d)),
    "si": lambda c, a, b: a if c else b,
}
FUNCIONES_REF = {"dist", "ang", "largo"}
CONSTANTES = {"pi": math.pi}
RESERVADOS = set(FUNCIONES) | FUNCIONES_REF | set(CONSTANTES) | {"x", "y"}


def _numero(texto: str) -> str:
    """Acepta coma decimal sola ("1,5") cuando no hay funciones de por medio."""
    t = str(texto).strip()
    if re.fullmatch(r"-?\d+,\d+", t):
        t = t.replace(",", ".")
    return t


def nombres_en(formula: str) -> set:
    """Nombres que usa una fórmula (para dependencias / renombrar)."""
    try:
        arbol = ast.parse(_numero(formula), mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}


# ---------------------------------------------------------------------- geometría

def _bezier_cubica(p0, p1, p2, p3, n=32):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return pts


def _catmull_rom(pts, n=20):
    """Curva suave (Catmull-Rom centrípeta) que pasa por todos los puntos."""
    if len(pts) < 3:
        return list(pts)
    p = [(2 * pts[0][0] - pts[1][0], 2 * pts[0][1] - pts[1][1])] + list(pts) + \
        [(2 * pts[-1][0] - pts[-2][0], 2 * pts[-1][1] - pts[-2][1])]
    salida = [pts[0]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]

        def tj(ti, a, b):
            return ti + max(math.dist(a, b), 1e-6) ** 0.5

        t0 = 0.0
        t1 = tj(t0, p0, p1)
        t2 = tj(t1, p1, p2)
        t3 = tj(t2, p2, p3)
        for k in range(1, n + 1):
            t = t1 + (t2 - t1) * k / n

            def lerp(a, b, ta, tb):
                if tb - ta < 1e-12:
                    return a
                return ((tb - t) / (tb - ta) * a[0] + (t - ta) / (tb - ta) * b[0],
                        (tb - t) / (tb - ta) * a[1] + (t - ta) / (tb - ta) * b[1])

            a1 = lerp(p0, p1, t0, t1)
            a2 = lerp(p1, p2, t1, t2)
            a3 = lerp(p2, p3, t2, t3)
            b1 = lerp(a1, a2, t0, t2)
            b2 = lerp(a2, a3, t1, t3)
            salida.append(lerp(b1, b2, t1, t2))
    return salida


def _largo(pts):
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _a_distancia(pts, d):
    """Punto sobre una poligonal a distancia d del inicio (d < 0: desde el final)."""
    total = _largo(pts)
    if d < 0:
        d = total + d
    d = max(0.0, min(total, d))
    for i in range(len(pts) - 1):
        s = math.dist(pts[i], pts[i + 1])
        if d <= s or i == len(pts) - 2:
            t = 0 if s < 1e-12 else d / s
            return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t,
                    pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t)
        d -= s
    return pts[-1]


def _reflejar(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1.0
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
    fx, fy = a[0] + t * dx, a[1] + t * dy
    return (2 * fx - p[0], 2 * fy - p[1])


# ---------------------------------------------------------------------- motor

class Motor:
    """Evalúa una prenda: resuelve fórmulas, puntos y curvas de forma perezosa."""

    def __init__(self, prenda: dict, medidas: dict | None = None):
        self.prenda = prenda
        self.medidas = {}
        self.etiquetas = {}
        for m in prenda.get("medidas", []):
            v = (medidas or {}).get(m["id"], m.get("valor", 0))
            try:
                self.medidas[m["id"]] = float(_numero(v))
            except (TypeError, ValueError):
                raise ErrorPrenda("medidas:" + m["id"], f"La medida {m['id']} no es un número.", "valor")
            self.etiquetas[m["id"]] = m.get("nombre") or m["id"]
        self.def_var = {v["id"]: v for v in prenda.get("variables", [])}
        self.def_pto = {p["id"]: p for p in prenda.get("puntos", [])}
        self.def_cur = {c["id"]: c for c in prenda.get("curvas", [])}
        self.vars, self.ptos, self.curs = {}, {}, {}
        self._pila = []
        self.construccion = {}   # id de punto -> líneas auxiliares para la vista
        self._validar_ids()

    # ---- ids
    def _validar_ids(self):
        vistos = {}
        for grupo, lista in (("medidas", self.prenda.get("medidas", [])),
                             ("variables", self.prenda.get("variables", [])),
                             ("puntos", self.prenda.get("puntos", [])),
                             ("curvas", self.prenda.get("curvas", []))):
            for el in lista:
                i = str(el.get("id", ""))
                donde = f"{grupo}:{i}"
                if not ID_VALIDO.match(i):
                    raise ErrorPrenda(donde, f"El nombre «{i}» no sirve: usá letras, números y _ "
                                             "(sin espacios ni acentos, sin empezar con número).", "id")
                if i in RESERVADOS:
                    raise ErrorPrenda(donde, f"«{i}» es una palabra reservada; elegí otro nombre.", "id")
                if i in vistos:
                    raise ErrorPrenda(donde, f"El nombre «{i}» está repetido (también en {vistos[i]}).", "id")
                vistos[i] = grupo

    # ---- ciclos
    def _entrar(self, clave, donde):
        if clave in self._pila:
            ciclo = " → ".join(k.split(":", 1)[1] for k in self._pila[self._pila.index(clave):] + [clave])
            raise ErrorPrenda(donde, f"Referencia circular: {ciclo}")
        self._pila.append(clave)

    def _salir(self):
        self._pila.pop()

    # ---- valores
    def valor(self, nombre: str, donde: str = "") -> float:
        if nombre in self.medidas:
            return self.medidas[nombre]
        if nombre in CONSTANTES:
            return CONSTANTES[nombre]
        if nombre in self.def_var:
            if nombre not in self.vars:
                self._entrar("variables:" + nombre, "variables:" + nombre)
                try:
                    self.vars[nombre] = self.formula(self.def_var[nombre].get("formula", ""),
                                                     "variables:" + nombre, "formula")
                finally:
                    self._salir()
            return self.vars[nombre]
        if nombre in self.def_pto:
            raise ErrorPrenda(donde, f"«{nombre}» es un punto: usá {nombre}.x o {nombre}.y")
        if nombre in self.def_cur:
            raise ErrorPrenda(donde, f"«{nombre}» es una curva: usá largo({nombre})")
        raise ErrorPrenda(donde, f"No existe ninguna medida o variable llamada «{nombre}».")

    def formula(self, texto, donde: str, campo: str = "") -> float:
        if isinstance(texto, (int, float)):
            return float(texto)
        t = _numero(texto)
        if not t:
            raise ErrorPrenda(donde, "Falta completar este valor.", campo)
        try:
            arbol = ast.parse(t, mode="eval")
        except SyntaxError:
            raise ErrorPrenda(donde, f"No entiendo la fórmula «{texto}». Revisá paréntesis y "
                                     "usá punto para los decimales (1.5).", campo)
        try:
            v = self._eval(arbol.body, donde, campo)
        except ErrorPrenda as e:
            if not e.campo:
                e.campo = campo
            if not e.donde:
                e.donde = donde
            raise
        except ZeroDivisionError:
            raise ErrorPrenda(donde, "División por cero.", campo)
        except (ValueError, OverflowError, TypeError) as e:
            raise ErrorPrenda(donde, f"Cuenta imposible en «{texto}» ({e}).", campo)
        if isinstance(v, bool):
            v = float(v)
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ErrorPrenda(donde, f"La fórmula «{texto}» no da un número.", campo)
        return float(v)

    def _eval(self, n, donde, campo):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _BINARIOS:
            a, b = self._eval(n.left, donde, campo), self._eval(n.right, donde, campo)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ErrorPrenda(donde, "Exponente demasiado grande.", campo)
            return _BINARIOS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = self._eval(n.operand, donde, campo)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.Compare) and len(n.ops) == 1 and type(n.ops[0]) in _COMPARA:
            return _COMPARA[type(n.ops[0])](self._eval(n.left, donde, campo),
                                            self._eval(n.comparators[0], donde, campo))
        if isinstance(n, ast.Name):
            return self.valor(n.id, donde)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.attr in ("x", "y"):
            p = self.punto(n.value.id, donde)
            return p[0] if n.attr == "x" else p[1]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.keywords:
            f = n.func.id
            if f in FUNCIONES_REF:
                return self._funcion_ref(f, n.args, donde)
            if f in FUNCIONES:
                return FUNCIONES[f](*[self._eval(a, donde, campo) for a in n.args])
            raise ErrorPrenda(donde, f"No conozco la función «{f}».")
        raise ErrorPrenda(donde, "Esa fórmula usa algo que no está permitido.")

    def _ref(self, nodo, donde):
        if isinstance(nodo, ast.Name):
            return nodo.id
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            return nodo.value
        raise ErrorPrenda(donde, "dist, ang y largo reciben nombres de puntos o curvas.")

    def _funcion_ref(self, f, args, donde):
        ids = [self._ref(a, donde) for a in args]
        if f == "largo":
            if len(ids) == 1 and ids[0] in self.def_cur:
                return _largo(self.curva(ids[0], donde))
            if len(ids) >= 2:
                return _largo([self.punto(i, donde) for i in ids])
            raise ErrorPrenda(donde, "largo() recibe una curva, o dos o más puntos.")
        if len(ids) != 2:
            raise ErrorPrenda(donde, f"{f}() recibe dos puntos.")
        a, b = self.punto(ids[0], donde), self.punto(ids[1], donde)
        if f == "dist":
            return math.dist(a, b)
        return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0])) % 360

    # ---- puntos
    def punto(self, pid: str, donde: str = ""):
        if pid in self.ptos:
            return self.ptos[pid]
        if pid not in self.def_pto:
            raise ErrorPrenda(donde, f"No existe el punto «{pid}».")
        clave = "puntos:" + pid
        self._entrar(clave, clave)
        try:
            self.ptos[pid] = self._calcular_punto(self.def_pto[pid])
        finally:
            self._salir()
        return self.ptos[pid]

    def _calcular_punto(self, d):
        pid = d["id"]
        donde = "puntos:" + pid
        tipo = d.get("tipo", "xy")
        if tipo not in TIPOS_PUNTO:
            raise ErrorPrenda(donde, f"Tipo de punto desconocido: {tipo}", "tipo")

        def P(campo):
            ref = str(d.get(campo, "")).strip()
            if not ref:
                raise ErrorPrenda(donde, f"Falta elegir el punto «{campo}».", campo)
            if ref == pid:
                raise ErrorPrenda(donde, "Un punto no puede depender de sí mismo.", campo)
            try:
                return self.punto(ref, donde)
            except ErrorPrenda as e:
                if e.donde != donde and not e.mensaje.startswith("Referencia circular"):
                    raise ErrorPrenda(donde, f"Depende de «{ref}», que tiene un error.", campo)
                e.campo = e.campo or campo
                raise

        def F(campo):
            return self.formula(d.get(campo, ""), donde, campo)

        aux = []
        if tipo == "xy":
            p = (F("x"), F("y"))
        elif tipo == "desde":
            b = P("base")
            p = (b[0] + F("dx"), b[1] + F("dy"))
            aux = [[b, p]]
        elif tipo == "polar":
            b = P("base")
            L, a = F("largo"), math.radians(F("angulo"))
            p = (b[0] + L * math.cos(a), b[1] - L * math.sin(a))
            aux = [[b, p]]
        elif tipo == "sobre_linea":
            a, b = P("a"), P("b")
            L = F("largo")
            D = math.dist(a, b)
            if D < 1e-9:
                raise ErrorPrenda(donde, "Los dos puntos de la línea coinciden.", "b")
            p = (a[0] + (b[0] - a[0]) * L / D, a[1] + (b[1] - a[1]) * L / D)
            aux = [[a, p if L > D else b]]
        elif tipo == "medio":
            a, b = P("a"), P("b")
            p = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        elif tipo == "interseccion":
            a, b, c, e = P("a"), P("b"), P("c"), P("d")
            d1x, d1y = b[0] - a[0], b[1] - a[1]
            d2x, d2y = e[0] - c[0], e[1] - c[1]
            den = d1x * d2y - d1y * d2x
            if abs(den) < 1e-9:
                raise ErrorPrenda(donde, "Las dos líneas son paralelas: no se cruzan.", "c")
            t = ((c[0] - a[0]) * d2y - (c[1] - a[1]) * d2x) / den
            p = (a[0] + t * d1x, a[1] + t * d1y)
            aux = [[a, p], [c, p]]
        elif tipo == "pie":
            o, a, b = P("base"), P("a"), P("b")
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            if L2 < 1e-12:
                raise ErrorPrenda(donde, "Los dos puntos de la línea coinciden.", "b")
            t = ((o[0] - a[0]) * dx + (o[1] - a[1]) * dy) / L2
            p = (a[0] + t * dx, a[1] + t * dy)
            aux = [[o, p], [a, p]]
        elif tipo == "circulo_linea":
            o, a, b = P("centro"), P("a"), P("b")
            r = F("radio")
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            if L < 1e-9:
                raise ErrorPrenda(donde, "Los dos puntos de la línea coinciden.", "b")
            ux, uy = dx / L, dy / L
            fx, fy = a[0] - o[0], a[1] - o[1]
            bq = fx * ux + fy * uy
            disc = bq * bq - (fx * fx + fy * fy - r * r)
            if disc < 0:
                raise ErrorPrenda(donde, f"Ningún punto de la línea está a {r:g} cm de "
                                         f"«{d.get('centro')}». Probá con una distancia mayor.", "radio")
            t = -bq + math.sqrt(disc)   # la solución más avanzada en el sentido a → b
            p = (a[0] + t * ux, a[1] + t * uy)
            aux = [[o, p], [a, p]]
        elif tipo == "en_curva":
            cid = str(d.get("curva", "")).strip()
            if not cid:
                raise ErrorPrenda(donde, "Falta elegir la curva.", "curva")
            pts = self.curva(cid, donde)
            p = _a_distancia(pts, F("largo"))
        self.construccion[pid] = aux
        return p

    # ---- curvas
    def curva(self, cid: str, donde: str = ""):
        if cid in self.curs:
            return self.curs[cid]
        if cid not in self.def_cur:
            raise ErrorPrenda(donde, f"No existe la curva «{cid}».")
        clave = "curvas:" + cid
        self._entrar(clave, clave)
        try:
            self.curs[cid] = self._calcular_curva(self.def_cur[cid])
        finally:
            self._salir()
        return self.curs[cid]

    def ids_curva(self, d) -> list:
        ids = d.get("puntos", [])
        if isinstance(ids, str):
            ids = [s for s in re.split(r"[\s,;]+", ids) if s]
        return ids

    def _calcular_curva(self, d):
        cid = d["id"]
        donde = "curvas:" + cid
        tipo = d.get("tipo", "bezier")
        ids = self.ids_curva(d)
        if len(ids) < 2:
            raise ErrorPrenda(donde, "Una curva necesita al menos 2 puntos.", "puntos")
        pts = []
        for i in ids:
            try:
                pts.append(self.punto(i, donde))
            except ErrorPrenda as e:
                if e.donde != donde:
                    raise ErrorPrenda(donde, f"Depende de «{i}», que tiene un error.", "puntos")
                e.campo = "puntos"
                raise
        if tipo == "poligonal":
            return pts
        if tipo == "suave":
            return _catmull_rom(pts)
        if tipo == "bezier":
            if len(pts) == 2:
                return pts
            if len(pts) == 3:   # cuadrática → cúbica
                p0, c, p2 = pts
                c1 = (p0[0] + 2 / 3 * (c[0] - p0[0]), p0[1] + 2 / 3 * (c[1] - p0[1]))
                c2 = (p2[0] + 2 / 3 * (c[0] - p2[0]), p2[1] + 2 / 3 * (c[1] - p2[1]))
                return _bezier_cubica(p0, c1, c2, p2)
            if (len(pts) - 1) % 3:
                raise ErrorPrenda(donde, "Una Bézier lleva inicio, control, control, fin "
                                         "(4 puntos; o 7, 10… para encadenar tramos).", "puntos")
            salida = []
            for k in range(0, len(pts) - 1, 3):
                tramo = _bezier_cubica(*pts[k:k + 4])
                salida.extend(tramo if not salida else tramo[1:])
            return salida
        raise ErrorPrenda(donde, f"Tipo de curva desconocido: {tipo}", "tipo")

    def extremos_curva(self, cid):
        d = self.def_cur[cid]
        ids = self.ids_curva(d)
        return ids[0], ids[-1]

    # ---- piezas
    def pieza(self, d: dict, indice: int = 0) -> Pieza:
        nombre = d.get("nombre") or f"Pieza {indice + 1}"
        donde = f"piezas:{indice}"
        elementos = d.get("contorno", [])
        if isinstance(elementos, str):
            elementos = [s for s in re.split(r"[\s,;]+", elementos) if s]
        if len(elementos) < 2:
            raise ErrorPrenda(donde, "El contorno necesita puntos y/o curvas (al menos 3 puntos en total).",
                              "contorno")

        # 1) tramos: cada uno va de un nodo (punto con nombre) al siguiente
        nodos = []      # [(id, (x, y))]
        tramos = []     # [lista de puntos intermedios entre nodo k y k+1 (sin extremos)]
        for k, el in enumerate(elementos):
            if el in self.def_cur:
                ini, fin = self.extremos_curva(el)
                pts = self.curva(el, donde)
                ultimo = nodos[-1][0] if nodos else None
                if ultimo is None:
                    # orientar según el elemento siguiente
                    sig = elementos[(k + 1) % len(elementos)]
                    cerca = sig if sig in self.def_pto else (self.extremos_curva(sig) if sig in self.def_cur else ())
                    if (fin not in cerca if isinstance(cerca, tuple) else fin != cerca) and \
                            (ini in cerca if isinstance(cerca, tuple) else ini == cerca):
                        ini, fin, pts = fin, ini, pts[::-1]
                elif ultimo == fin and ultimo != ini:
                    ini, fin, pts = fin, ini, pts[::-1]
                elif ultimo != ini:
                    raise ErrorPrenda(donde, f"La curva «{el}» no empieza ni termina en «{ultimo}», "
                                             "el punto anterior del contorno.", "contorno")
                if not nodos:
                    nodos.append((ini, pts[0]))
                tramos.append(list(pts[1:-1]))
                nodos.append((fin, pts[-1]))
            elif el in self.def_pto:
                p = self.punto(el, donde)
                if nodos and nodos[-1][0] == el:
                    continue
                if nodos:
                    tramos.append([])
                nodos.append((el, p))
            else:
                raise ErrorPrenda(donde, f"«{el}» no es un punto ni una curva.", "contorno")
        if len(nodos) > 1 and nodos[-1][0] == nodos[0][0]:
            nodos.pop()
        else:
            tramos.append([])   # cierre recto del último nodo al primero
        if len(nodos) < 3 and sum(len(t) for t in tramos) == 0:
            raise ErrorPrenda(donde, "El contorno necesita al menos 3 puntos.", "contorno")

        # márgenes por tramo (por par de nodos, en cualquier orden)
        margen_tramo = {}
        for m in d.get("margenes", []):
            a, b = str(m.get("desde", "")).strip(), str(m.get("hasta", "")).strip()
            if not a or not b:
                continue
            val = self.formula(m.get("margen", ""), donde, "margenes")
            margen_tramo[frozenset((a, b))] = val
        doblez = d.get("doblez") or []
        if isinstance(doblez, str):
            doblez = [s for s in re.split(r"[\s,;]+", doblez) if s]
        doblez = [x for x in doblez if x]
        if doblez and len(doblez) != 2:
            raise ErrorPrenda(donde, "El doblez se marca con dos puntos del contorno.", "doblez")
        if doblez:
            margen_tramo[frozenset(doblez)] = 0.0

        n = len(nodos)
        ids_nodos = [i for i, _ in nodos]
        if doblez:
            for x in doblez:
                if x not in ids_nodos:
                    raise ErrorPrenda(donde, f"El doblez usa «{x}», que no está en el contorno.", "doblez")
            ia, ib = ids_nodos.index(doblez[0]), ids_nodos.index(doblez[1])
            if (ia + 1) % n != ib and (ib + 1) % n != ia:
                raise ErrorPrenda(donde, "Los dos puntos del doblez tienen que ser vecinos en el contorno.",
                                  "doblez")
            k_doblez = ia if (ia + 1) % n == ib else ib
            if tramos[k_doblez]:
                raise ErrorPrenda(donde, "El doblez tiene que ser un tramo recto.", "doblez")

        # 2) desplegar (espejar sobre el doblez) si corresponde
        espejo = None
        if d.get("desplegar") and doblez:
            A = nodos[k_doblez][1]
            B = nodos[(k_doblez + 1) % n][1]
            a_id, b_id = ids_nodos[k_doblez], ids_nodos[(k_doblez + 1) % n]

            def prima(x):
                return x if x in (a_id, b_id) else x + "'"

            orden = [(k_doblez + 1 + t) % n for t in range(n)]   # de B ... hasta A
            orig_n = [nodos[k] for k in orden]
            orig_t = [tramos[k] for k in orden[:-1]]             # sin el tramo del doblez
            refl_t = [[_reflejar(q, A, B) for q in tr][::-1] for tr in orig_t]
            nodos = orig_n + [(prima(orig_n[t][0]), _reflejar(orig_n[t][1], A, B))
                              for t in range(n - 2, 0, -1)]
            tramos = orig_t + [refl_t[t] for t in range(n - 2, -1, -1)]
            for clave, val in list(margen_tramo.items()):
                margen_tramo.setdefault(frozenset(prima(x) for x in clave), val)
            margen_tramo.pop(frozenset(doblez), None)
            espejo = (A, B)
            doblez = []
            n = len(nodos)

        # 3) contorno final y margen por arista
        contorno, margenes = [], []
        for k in range(n):
            ida, p = nodos[k]
            idb = nodos[(k + 1) % n][0]
            m = margen_tramo.get(frozenset((ida, idb)))
            contorno.append(p)
            margenes.append(m)
            for q in tramos[k]:
                contorno.append(q)
                margenes.append(m)
        if all(m is None for m in margenes):
            margenes = None

        hilo = d.get("hilo") or []
        if isinstance(hilo, str):
            hilo = [s for s in re.split(r"[\s,;]+", hilo) if s]
        hilo = [h for h in hilo if h]
        color = d.get("color") or COLORES[indice % len(COLORES)]
        pz = Pieza(nombre, contorno, cortar=d.get("cortar") or "Cortar 1", color=color,
                   margenes=margenes)
        if pz.poligono().area < 1e-6:
            raise ErrorPrenda(donde, "La pieza no tiene superficie: revisá el orden del contorno.", "contorno")
        if doblez:
            pz.doblez = (self.punto(doblez[0], donde), self.punto(doblez[1], donde))
            if "doblez" not in pz.cortar.lower() and pz.cortar.strip().lower().startswith("cortar"):
                pz.cortar = pz.cortar + " al doblez"
        if len(hilo) == 2:
            pz.hilo = (self.punto(hilo[0], donde), self.punto(hilo[1], donde))
        elif not d.get("sin_hilo"):
            minx, miny, maxx, maxy = pz.poligono().bounds
            cx, cy = pz.punto_etiqueta()
            L = max(2.0, min(25.0, (maxy - miny) * 0.45))
            off = min(4.0, (maxx - minx) * 0.18)
            pz.hilo = ((cx + off, cy - L / 2), (cx + off, cy + L / 2))
            if not pz.poligono().contains(LineString(pz.hilo)):
                pz.hilo = ((cx, cy + 1.5), (cx, cy + 1.5 + L / 2))

        for m in d.get("marcas", []):
            pid = str(m.get("punto", "")).strip()
            if not pid:
                continue
            x, y = self.punto(pid, donde)
            pz.marcas.append(marca_en(pz, x, y, str(m.get("texto", "")), bool(m.get("piquete", True))))
            if espejo:
                rx, ry = _reflejar((x, y), *espejo)
                if math.dist((rx, ry), (x, y)) > 0.05:
                    pz.marcas.append(marca_en(pz, rx, ry, str(m.get("texto", "")),
                                              bool(m.get("piquete", True))))
        for ln in d.get("lineas", []):
            ids = ln.get("puntos", [])
            if isinstance(ids, str):
                ids = [s for s in re.split(r"[\s,;]+", ids) if s]
            pts = []
            for i in ids:
                pts.extend(self.curva(i, donde) if i in self.def_cur else [self.punto(i, donde)])
            if len(pts) >= 2:
                est = ln.get("estilo", "linea")
                pz.lineas.append((pts, est))
                if espejo:
                    pz.lineas.append(([_reflejar(p, *espejo) for p in pts], est))
                if est == "pinza" and len(pts) == 3 and ln.get("piquetes", True):
                    # piquete en cada pata de la pinza que toca el borde
                    for q in (pts[0], pts[2]):
                        for qq in ([q, _reflejar(q, *espejo)] if espejo else [q]):
                            if pz.poligono().exterior.distance(Point(qq)) < 0.3:
                                pz.marcas.append(marca_en(pz, qq[0], qq[1], ""))
        notas = d.get("notas") or ""
        pz.notas = [s.strip() for s in str(notas).split("\n") if s.strip()]
        return pz


# ---------------------------------------------------------------------- API

def cargar(texto_o_dict) -> dict:
    prenda = json.loads(texto_o_dict) if isinstance(texto_o_dict, str) else texto_o_dict
    if not isinstance(prenda, dict):
        raise ErrorPrenda("prenda", "El archivo no es una prenda de Moldes.")
    if prenda.get("formato", FORMATO) != FORMATO:
        raise ErrorPrenda("prenda", "El archivo no es una prenda de Moldes (formato desconocido).")
    if int(prenda.get("version", 1)) > VERSION:
        raise ErrorPrenda("prenda", "Esta prenda se hizo con una versión más nueva de Moldes.")
    return prenda


def _r(p):
    return [round(p[0], 3), round(p[1], 3)]


def evaluar(texto_o_dict, medidas: dict | None = None, margen: float | None = None) -> dict:
    """Evalúa todo lo que se pueda y junta los errores (para la vista del editor)."""
    res = {"puntos": {}, "curvas": {}, "construccion": [], "piezas": [], "variables": {},
           "controles": [], "errores": [], "largos": {}}
    try:
        prenda = cargar(texto_o_dict)
        mot = Motor(prenda, medidas)
    except ErrorPrenda as e:
        res["errores"].append({"donde": e.donde, "campo": e.campo, "mensaje": e.mensaje})
        return res
    margen = float(prenda.get("margen", 1.0) if margen is None else margen)

    def intentar(donde, fn):
        try:
            return fn()
        except ErrorPrenda as e:
            res["errores"].append({"donde": e.donde if e.donde.split(":")[0] == donde.split(":")[0]
                                   and e.donde == donde else donde,
                                   "campo": e.campo, "mensaje": e.mensaje})
        except Exception as e:   # noqa: BLE001 — cualquier falla geométrica se informa
            res["errores"].append({"donde": donde, "campo": "", "mensaje": f"Error inesperado: {e}"})
        return None

    for v in prenda.get("variables", []):
        val = intentar("variables:" + v["id"], lambda v=v: mot.valor(v["id"]))
        if val is not None:
            res["variables"][v["id"]] = round(val, 4)
    for p in prenda.get("puntos", []):
        val = intentar("puntos:" + p["id"], lambda p=p: mot.punto(p["id"]))
        if val is not None:
            res["puntos"][p["id"]] = _r(val)
            for a, b in mot.construccion.get(p["id"], []):
                res["construccion"].append([_r(a), _r(b)])
    for c in prenda.get("curvas", []):
        val = intentar("curvas:" + c["id"], lambda c=c: mot.curva(c["id"]))
        if val is not None:
            res["curvas"][c["id"]] = [_r(q) for q in val]
            res["largos"][c["id"]] = round(_largo(val), 2)
    for i, d in enumerate(prenda.get("piezas", [])):
        pz = intentar(f"piezas:{i}", lambda d=d, i=i: mot.pieza(d, i))
        if pz is None:
            res["piezas"].append(None)
            continue
        corte = pz.corte(margen)
        anillo = list(getattr(corte, "exterior", corte).coords) if not corte.is_empty else []
        res["piezas"].append({
            "nombre": pz.nombre, "color": pz.color,
            "contorno": [_r(q) for q in pz.contorno],
            "corte": [_r(q) for q in anillo],
            "doblez": [_r(q) for q in pz.doblez] if pz.doblez else None,
            "hilo": [_r(q) for q in pz.hilo] if pz.hilo else None,
            "lineas": [[[_r(q) for q in pts], est] for pts, est in pz.lineas],
            "marcas": [{"p": _r((m.x, m.y)), "n": [round(m.nx, 3), round(m.ny, 3)], "t": m.texto}
                       for m in pz.marcas],
            "etiqueta": _r(pz.punto_etiqueta()),
            "perimetro": round(pz.poligono().exterior.length, 1),
            "area": round(pz.poligono().area, 1),
        })
    for i, c in enumerate(prenda.get("controles", [])):
        val = intentar(f"controles:{i}", lambda c=c, i=i: mot.formula(c.get("formula", ""),
                                                                    f"controles:{i}", "formula"))
        ok = None
        if val is not None:
            ok = True
            for lim, cmp in (("min", lambda v, x: v >= x), ("max", lambda v, x: v <= x)):
                if str(c.get(lim, "")).strip() != "":
                    x = intentar(f"controles:{i}", lambda c=c, lim=lim: mot.formula(c[lim], f"controles:{i}", lim))
                    if x is not None and not cmp(val, x - 1e-9):
                        ok = False
        res["controles"].append({"nombre": c.get("nombre", ""), "valor": None if val is None else round(val, 2),
                                 "ok": ok})
    return res


def generar(texto_o_dict, medidas: dict | None = None):
    """Devuelve (piezas, informe). Si hay errores, ValueError con la lista."""
    prenda = cargar(texto_o_dict)
    ev = evaluar(prenda, medidas)
    if ev["errores"]:
        lineas = []
        for e in ev["errores"][:6]:
            grupo, _, ident = e["donde"].partition(":")
            if grupo == "piezas" and ident.isdigit() and int(ident) < len(prenda.get("piezas", [])):
                ident = prenda["piezas"][int(ident)].get("nombre") or ident
            lineas.append(f"{grupo} {ident}: {e['mensaje']}")
        mas = f" (y {len(ev['errores']) - 6} más)" if len(ev["errores"]) > 6 else ""
        raise ValueError("La prenda tiene errores: " + " · ".join(lineas) + mas)
    mot = Motor(prenda, medidas)
    piezas = [mot.pieza(d, i) for i, d in enumerate(prenda.get("piezas", []))]
    if not piezas:
        raise ValueError("La prenda no tiene piezas todavía.")
    nombre = prenda.get("nombre") or "Prenda personalizada"
    usadas = ", ".join(f"{mot.etiquetas[k]} {v:g}" for k, v in mot.medidas.items())
    informe = [f"{nombre}" + (f" · {usadas}" if usadas else "")]
    if prenda.get("descripcion"):
        informe.append(str(prenda["descripcion"]))
    for c in ev["controles"]:
        estado = "" if c["ok"] is None else (" ✔" if c["ok"] else " — aviso: fuera de rango, revisá")
        informe.append(f"{c['nombre']}: {c['valor']:g}{estado}" if c["valor"] is not None else c["nombre"])
    return piezas, informe


def esquema() -> dict:
    """Describe los tipos de punto/curva/línea para armar el editor."""
    return {
        "puntos": {k: {"nombre": v["nombre"],
                       "campos": [{"id": a, "tipo": b, "etiqueta": c} for a, b, c in v["campos"]]}
                   for k, v in TIPOS_PUNTO.items()},
        "curvas": TIPOS_CURVA,
        "lineas": ESTILOS_LINEA,
        "colores": COLORES,
        "reservados": sorted(RESERVADOS),
    }
