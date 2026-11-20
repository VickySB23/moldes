"""Funciones que llama la página web (Pyodide). Devuelven JSON."""
from __future__ import annotations

import base64
import json

from . import peluche, ropa
from .salida import acomodar, generar_pdf, generar_svg


def prendas() -> str:
    return json.dumps({k: {"nombre": v["nombre"], "margen": v["margen"],
                           "params": [{"id": a, "etiqueta": b, "valor": c} for a, b, c in v["params"]]}
                       for k, v in ropa.PRENDAS.items()})


def _resultado(piezas, informe, titulo, margen, hoja, extra=None):
    ac = acomodar(piezas, margen, hoja)
    pdf = generar_pdf(ac, titulo, informe, hoja)
    res = {
        "informe": informe,
        "svg": generar_svg(ac, color=True),
        "svg_impresion": generar_svg(ac, color=False),
        "pdf": base64.b64encode(pdf).decode(),
        "ancho_cm": round(ac.ancho, 1),
        "alto_cm": round(ac.alto, 1),
        "piezas": len(piezas),
    }
    if extra:
        res.update(extra)
    return json.dumps(res)


def generar_ropa(opciones_json: str) -> str:
    o = json.loads(opciones_json)
    prenda = o["prenda"]
    piezas, informe = ropa.generar(prenda, o.get("medidas", {}))
    margen = float(o.get("margen", ropa.PRENDAS[prenda]["margen"]))
    informe = informe + [f"Margen de costura incluido: {margen:g} cm (línea punteada = costura)."]
    return _resultado(piezas, informe, ropa.PRENDAS[prenda]["nombre"], margen, o.get("hoja", "A4"))


def generar_peluche(texto_obj: str, opciones_json: str) -> str:
    o = json.loads(opciones_json)
    margen = float(o.get("margen", 0.6))
    piezas, informe, vista = peluche.molde_peluche(
        texto_obj,
        altura_cm=float(o.get("altura", 30)),
        eje=o.get("eje", "y"),
        modo=o.get("modo", "auto"),
        iteraciones=int(o.get("iteraciones", 15)),
    )
    if not piezas:
        avisos = informe[3:]
        resumen = " ".join(avisos[:2]) + (f" (y {len(avisos)-2} avisos más)" if len(avisos) > 2 else "")
        raise ValueError("No salió ninguna pieza. " + resumen)
    informe = informe + [f"Margen de costura incluido: {margen:g} cm (línea punteada = costura)."]
    return _resultado(piezas, informe, o.get("titulo") or "Peluche", margen, o.get("hoja", "A4"),
                      {"vista3d": vista})
