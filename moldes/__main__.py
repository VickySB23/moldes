"""Uso desde la terminal (sin navegador).

Ejemplos:
    python -m moldes ropa remera --pecho 92 --largo_total 65 -o remera.pdf
    python -m moldes ropa falda_circular --cintura 72
    python -m moldes peluche ejemplos/rana.obj --altura 35 -o rana.pdf
    python -m moldes personal ejemplos/falda_recta.json --medida cintura=74 --medida cadera=100
    python -m moldes formas ejemplos/osito.json -o osito.obj        (modelo 3D para Blender)
    python -m moldes maniqui --base mujer_m --busto 90 -o yo.obj    (maniquí con tus medidas)
"""
import argparse
import os
import sys

from . import formas, maniqui, personal, peluche, ropa
from .salida import HOJAS, acomodar, generar_pdf, generar_svg


def _consola_utf8():
    # En Windows la consola suele usar cp1252 y falla con "→", "×" o acentos.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _consola_utf8()
    ap =argparse.ArgumentParser(prog="python -m moldes", description="Moldes de costura en PDF.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("ropa", help="molde de ropa a partir de medidas")
    r.add_argument("prenda", choices=list(ropa.PRENDAS))
    for spec in ropa.PRENDAS.values():
        for k, etiqueta, d in spec["params"]:
            try:
                r.add_argument(f"--{k}", type=float, help=f"{etiqueta} (cm)")
            except argparse.ArgumentError:
                pass
    r.add_argument("--margen", type=float, default=None, help="margen de costura en cm")

    p = sub.add_parser("peluche", help="molde de peluche desde un .obj")
    p.add_argument("obj")
    p.add_argument("--altura", type=float, default=30, help="altura final en cm")
    p.add_argument("--eje", default="y", choices=["x", "y", "z"], help="eje vertical del modelo")
    p.add_argument("--modo", default="auto", choices=["auto", "grupos", "materiales", "uv", "partes"])
    p.add_argument("--margen", type=float, default=0.6)

    q = sub.add_parser("personal", help="prenda personalizada (archivo .json hecho en el editor)")
    q.add_argument("prenda", help="archivo .json de la prenda")
    q.add_argument("--medida", action="append", default=[], metavar="NOMBRE=VALOR",
                   help="cambia una medida (se puede repetir)")
    q.add_argument("--margen", type=float, default=None, help="margen de costura en cm")
    q.add_argument("--medidas", action="store_true", help="solo mostrar las medidas que usa la prenda")

    fo = sub.add_parser("formas", help="exportar a .obj un modelo hecho con formas")
    fo.add_argument("modelo", help="archivo .json de formas (o proyecto exportado del taller)")
    fo.add_argument("-o", "--salida", default=None)
    mq = sub.add_parser("maniqui", help="exportar a .obj un maniquí con tus medidas")
    mq.add_argument("--base", default="mujer_m", choices=list(maniqui.TALLES), help="medidas de partida")
    mq.add_argument("--tipo", default="completo", choices=list(maniqui.TIPOS))
    mq.add_argument("--forma", default=None, choices=list(maniqui.FORMAS_CUERPO))
    mq.add_argument("--holgura", type=float, default=0.0)
    for k, nombre, _ in maniqui.MEDIDAS:
        mq.add_argument(f"--{k}", type=float, help=f"{nombre} (cm)")
    mq.add_argument("-o", "--salida", default=None)

    for sp in (r, p, q):
        sp.add_argument("--hoja", default="A4", choices=list(HOJAS))
        sp.add_argument("-o", "--salida", default=None, help="archivo PDF de salida")
        sp.add_argument("--svg", action="store_true", help="guardar también el SVG a tamaño real")

    a = ap.parse_args(argv)
    if a.cmd in ("formas", "maniqui"):
        return _exportar_obj(a)
    if a.cmd == "ropa":
        spec = ropa.PRENDAS[a.prenda]
        medidas = {k: getattr(a, k) for k, _, _ in spec["params"] if getattr(a, k, None) is not None}
        piezas, informe = ropa.generar(a.prenda, medidas)
        margen = spec["margen"] if a.margen is None else a.margen
        titulo, base = spec["nombre"], a.prenda
    elif a.cmd == "personal":
        with open(a.prenda, encoding="utf-8") as f:
            prenda = personal.cargar(f.read())
        if a.medidas:
            for m in prenda.get("medidas", []):
                print(f"{m['id']:>16} = {m.get('valor')}   {m.get('nombre', '')}")
            return 0
        medidas = {}
        for txt in a.medida:
            k, sep, v = txt.partition("=")
            if not sep:
                raise ValueError(f"--medida {txt}: usá NOMBRE=VALOR, por ejemplo --medida cintura=72")
            medidas[k.strip()] = v.strip()
        conocidas = {m["id"] for m in prenda.get("medidas", [])}
        for k in medidas:
            if k not in conocidas:
                raise ValueError(f"La prenda no tiene la medida «{k}». Medidas: {', '.join(sorted(conocidas))}")
        piezas, informe = personal.generar(prenda, medidas)
        margen = float(prenda.get("margen", 1.0)) if a.margen is None else a.margen
        base = os.path.splitext(os.path.basename(a.prenda))[0]
        titulo = prenda.get("nombre") or base
    else:
        with open(a.obj, encoding="utf-8", errors="replace") as f:
            piezas, informe, _ = peluche.molde_peluche(f.read(), a.altura, a.eje, a.modo)
        if not piezas:
            print("\n".join(informe), file=sys.stderr)
            raise ValueError("No salió ninguna pieza (mirá los avisos de arriba).")
        margen = a.margen
        base = os.path.splitext(os.path.basename(a.obj))[0]
        titulo = f"Peluche: {base}"
    informe.append(f"Margen de costura incluido: {margen:g} cm.")
    ac = acomodar(piezas, margen, a.hoja)
    salida = a.salida or f"molde_{base}.pdf"
    with open(salida, "wb") as f:
        f.write(generar_pdf(ac, titulo, informe, a.hoja))
    if a.svg:
        with open(os.path.splitext(salida)[0] + ".svg", "w", encoding="utf-8") as f:
            f.write(generar_svg(ac))
    print("\n".join(informe))
    print(f"→ {salida} ({len(piezas)} piezas, molde de {ac.ancho:.0f} × {ac.alto:.0f} cm)")


def _exportar_obj(a):
    import json
    if a.cmd == "formas":
        with open(a.modelo, encoding="utf-8") as f:
            d = json.load(f)
        d = d.get("formas") if d.get("formato") == "moldes-taller" else d
        texto = formas.a_obj(d)
        salida = a.salida or os.path.splitext(os.path.basename(a.modelo))[0] + ".obj"
    else:
        med = {k: v for k, v in maniqui.TALLES[a.base].items() if k != "nombre"}
        for k, _, _ in maniqui.MEDIDAS:
            if getattr(a, k) is not None:
                med[k] = getattr(a, k)
        forma = a.forma or ("masculina" if a.base.startswith("hombre") else "neutra" if a.base.startswith("nino") else "femenina")
        V, F, nombres, gcara, inf = maniqui.mallar({"medidas": med, "tipo": a.tipo, "forma": forma, "holgura": a.holgura})
        lineas = ["# Maniquí hecho con Moldes"] + [f"v {x:.4f} {y:.4f} {z:.4f}" for x, y, z in V]
        for gi, nombre in enumerate(nombres):
            lineas.append(f"g {nombre}")
            lineas += [f"f {i} {j} {k}" for i, j, k in F[gcara == gi] + 1]
        texto = "\n".join(lineas) + "\n"
        salida = a.salida or "maniqui.obj"
        print(" · ".join(f"{k}: {inf[k]['medido']} cm (pedido {inf[k]['pedido']})" for k in ("busto", "cintura", "cadera")))
    with open(salida, "w", encoding="utf-8") as f:
        f.write(texto)
    print(f"→ {salida} (eje Y arriba, en cm)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
