"""Genera ejemplos/rana.obj: una rana simple dividida en piezas (grupos).

Cabeza en 6 gajos, cuerpo en 4 gajos, brazos y piernas largas en 2 mitades.
Es sólo un ejemplo para probar el aplanado; podés reemplazarlo por tu modelo
exportado desde Blender (File > Export > Wavefront .obj, con "Object Groups").
"""
import math
import os

import numpy as np


def rotacion_hacia(eje):
    """Matriz que lleva el eje Z local a la dirección 'eje'."""
    z = np.asarray(eje, float)
    z /= np.linalg.norm(z)
    aux = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(aux, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def elipsoide_gajos(nombre, centro, radios, gajos, eje=(0, 1, 0), nu=48, nv=28,
                    fase=0.0, aplastar=0.0):
    """Elipsoide con polos sobre 'eje', dividido en 'gajos' a lo largo."""
    rx, ry, rz = radios  # rz = semieje sobre el eje de los polos
    R = rotacion_hacia(eje)
    verts = [np.array([0, 0, rz])]
    for j in range(1, nv):
        th = math.pi * j / nv
        for i in range(nu):
            ph = 2 * math.pi * i / nu + fase
            z = rz * math.cos(th)
            r_ = math.sin(th)
            if aplastar and z < 0:  # base un poco más plana (para sentarse)
                z *= (1 - aplastar)
            verts.append(np.array([rx * r_ * math.cos(ph), ry * r_ * math.sin(ph), z]))
    verts.append(np.array([0, 0, -rz]))
    V = [R @ v + np.asarray(centro, float) for v in verts]

    def idx(j, i):
        return 1 + (j - 1) * nu + (i % nu)

    sur = len(V) - 1
    caras = {g: [] for g in range(gajos)}
    por_gajo = nu // gajos
    for i in range(nu):
        g = i // por_gajo
        caras[g].append((0, idx(1, i + 1), idx(1, i)))
        for j in range(1, nv - 1):
            a, b = idx(j, i), idx(j, i + 1)
            c, d = idx(j + 1, i + 1), idx(j + 1, i)
            caras[g] += [(a, b, c), (a, c, d)]
        caras[g].append((sur, idx(nv - 1, i), idx(nv - 1, i + 1)))
    nombres = {g: f"{nombre} {g+1}" for g in range(gajos)}
    return V, caras, nombres


def main():
    piezas = [
        # nombre, centro, radios (rx, ry, r_polar), gajos, eje, fase
        ("Cabeza", (0, 24.5, 0), (7.5, 6.0, 5.5), 6, (0, 1, 0), 0.0, 0.0),
        ("Cuerpo", (0, 13.0, 0), (5.0, 4.0, 7.5), 4, (0, 1, 0), math.pi / 4, 0.0),
        ("Brazo izq", (-6.5, 12.0, 0), (1.6, 1.6, 6.5), 2, (-0.45, -1, 0), math.pi / 2, 0),
        ("Brazo der", (6.5, 12.0, 0), (1.6, 1.6, 6.5), 2, (0.45, -1, 0), math.pi / 2, 0),
        ("Pierna izq", (-2.6, 2.5, 0.5), (1.9, 1.9, 8.5), 2, (0, -1, 0.15), math.pi / 2, 0),
        ("Pierna der", (2.6, 2.5, 0.5), (1.9, 1.9, 8.5), 2, (0, -1, 0.15), math.pi / 2, 0),
    ]
    lineas = ["# Rana de ejemplo para moldes.py", "# Unidades arbitrarias; el programa escala a la altura pedida"]
    base = 0
    caras_txt = []
    for nombre, c, r, g, eje, fase, apl in piezas:
        V, caras, nombres = elipsoide_gajos(nombre, c, r, g, eje, fase=fase, aplastar=apl)
        for v in V:
            lineas.append("v %.5f %.5f %.5f" % tuple(v))
        for k, tris in caras.items():
            caras_txt.append(f"g {nombres[k]}")
            for t in tris:
                caras_txt.append("f %d %d %d" % tuple(base + x + 1 for x in t[::-1]))  # normales hacia afuera
        base += len(V)
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rana.obj")
    with open(ruta, "w") as f:
        f.write("\n".join(lineas + caras_txt) + "\n")
    print("escrito", ruta)


if __name__ == "__main__":
    main()
