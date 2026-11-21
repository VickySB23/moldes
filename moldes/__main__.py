"""Uso desde la terminal (sin navegador).

Ejemplos:
    python -m moldes ropa remera --pecho 92 --largo_total 65 -o remera.pdf
    python -m moldes ropa falda_circular --cintura 72
    python -m moldes peluche ejemplos/rana.obj --altura 35 -o rana.pdf
    python -m moldes personal ejemplos/falda_recta.json --medida cintura=74 --medida cadera=100
"""
import argparse
import os
import sys

from . import personal, peluche, ropa
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

    for sp in (r, p, q):
        sp.add_argument("--hoja", default="A4", choices=list(HOJAS))
        sp.add_argument("-o", "--salida", default=None, help="archivo PDF de salida")
        sp.add_argument("--svg", action="store_true", help="guardar también el SVG a tamaño real")

    a = ap.parse_args(argv)
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
