"""Escritor de PDF mínimo (sin dependencias) para moldes vectoriales.

Sólo líneas, polígonos y texto Helvetica. Suficiente para moldes y
funciona igual en Python de escritorio y en el navegador (Pyodide).
"""
from __future__ import annotations

import math
import zlib

PT_POR_MM = 72 / 25.4


def _num(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _txt(s: str) -> str:
    s = s.replace("→", "->").replace("↓", "v").replace("≈", "~")
    b = s.encode("cp1252", errors="replace").decode("latin-1")
    return b.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def ancho_texto(s: str, tam: float) -> float:
    """Ancho aproximado de un texto en Helvetica."""
    w = 0.0
    for ch in s:
        if ch in "il.,:;'|!":
            w += 0.28
        elif ch in "mwMW":
            w += 0.85
        elif ch.isupper() or ch.isdigit():
            w += 0.66
        elif ch == " ":
            w += 0.28
        else:
            w += 0.52
    return w * tam


class Pagina:
    """Página con coordenadas en mm, origen arriba a la izquierda, Y hacia abajo."""

    def __init__(self, ancho_mm: float, alto_mm: float):
        self.w, self.h = ancho_mm, alto_mm
        self.ops: list[str] = [
            f"{_num(PT_POR_MM)} 0 0 {_num(-PT_POR_MM)} 0 {_num(alto_mm * PT_POR_MM)} cm",
            "1 J 1 j",
        ]
        self.escala = 1.0  # unidades actuales -> mm (para el lienzo en cm)

    # estado
    def guardar(self):
        self.ops.append("q")

    def restaurar(self):
        self.ops.append("Q")

    def transformar(self, a, b, c, d, e, f):
        self.ops.append(" ".join(_num(v) for v in (a, b, c, d, e, f)) + " cm")

    def recortar_rect(self, x, y, w, h):
        self.ops.append(f"{_num(x)} {_num(y)} {_num(w)} {_num(h)} re W n")

    # dibujo
    def linea(self, pts, cerrada=False, ancho=0.3, trazo=None, color=(0, 0, 0), relleno=None):
        if len(pts) < 2:
            return
        o = self.ops
        o.append(f"{_num(ancho)} w")
        o.append("[" + " ".join(_num(v) for v in trazo) + "] 0 d" if trazo else "[] 0 d")
        o.append("{} {} {} RG".format(*(_num(c) for c in color)))
        if relleno:
            o.append("{} {} {} rg".format(*(_num(c) for c in relleno)))
        seg = [f"{_num(pts[0][0])} {_num(pts[0][1])} m"]
        seg += [f"{_num(x)} {_num(y)} l" for x, y in pts[1:]]
        o.append(" ".join(seg))
        if relleno:
            o.append("h B" if cerrada else "B")
        else:
            o.append("h S" if cerrada else "S")

    def rect(self, x, y, w, h, **kw):
        self.linea([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], cerrada=True, **kw)

    def texto(self, x, y, s, tam=3.5, ang=0.0, ancla="centro", color=(0, 0, 0), negrita=False):
        if not s:
            return
        w = ancho_texto(s, tam)
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        off = {"centro": -w / 2, "izq": 0.0, "der": -w}[ancla]
        # centrar verticalmente aprox. (altura de mayúscula ~0.7 tam)
        vy = tam * 0.35
        px = x + ca * off - sa * vy
        py = y + sa * off + ca * vy
        fuente = "/F2" if negrita else "/F1"
        self.ops.append("{} {} {} rg".format(*(_num(c) for c in color)))
        self.ops.append(
            f"BT {fuente} 1 Tf {_num(tam*ca)} {_num(tam*sa)} {_num(tam*sa)} {_num(-tam*ca)} "
            f"{_num(px)} {_num(py)} Tm ({_txt(s)}) Tj ET"
        )


class LienzoCm:
    """Adaptador: recibe coordenadas en cm y dibuja en una Página (mm)."""

    def __init__(self, pagina: Pagina):
        self.p = pagina

    def linea(self, pts, cerrada=False, ancho=0.03, trazo=None, color=(0, 0, 0), relleno=None):
        self.p.linea([(x * 10, y * 10) for x, y in pts], cerrada, ancho * 10,
                     [t * 10 for t in trazo] if trazo else None, color, relleno)

    def texto(self, x, y, s, tam=0.5, ang=0.0, ancla="centro", color=(0, 0, 0)):
        self.p.texto(x * 10, y * 10, s, tam * 10, ang, ancla, color)


class PDF:
    def __init__(self, titulo: str = "Molde"):
        self.paginas: list[Pagina] = []
        self.titulo = titulo

    def nueva_pagina(self, ancho_mm=210.0, alto_mm=297.0) -> Pagina:
        p = Pagina(ancho_mm, alto_mm)
        self.paginas.append(p)
        return p

    def bytes(self) -> bytes:
        objs: list[bytes] = []

        def add(b: bytes) -> int:
            objs.append(b)
            return len(objs)

        cat = add(b"")  # 1 catálogo (se completa después)
        pags = add(b"")  # 2 árbol de páginas
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        kids = []
        for pg in self.paginas:
            datos = zlib.compress("\n".join(pg.ops).encode("latin-1"))
            cont = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(datos) + datos + b"\nendstream")
            w, h = pg.w * PT_POR_MM, pg.h * PT_POR_MM
            kid = add(
                (f"<< /Type /Page /Parent {pags} 0 R /MediaBox [0 0 {_num(w)} {_num(h)}] "
                 f"/Resources << /Font << /F1 {f1} 0 R /F2 {f2} 0 R >> >> /Contents {cont} 0 R >>").encode()
            )
            kids.append(kid)
        objs[cat - 1] = f"<< /Type /Catalog /Pages {pags} 0 R >>".encode()
        objs[pags - 1] = (f"<< /Type /Pages /Count {len(kids)} /Kids [" +
                          " ".join(f"{k} 0 R" for k in kids) + "] >>").encode()
        info = add(f"<< /Title ({_txt(self.titulo)}) /Producer (moldes.py) >>".encode("latin-1"))

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, b in enumerate(objs, 1):
            offs.append(len(out))
            out += f"{i} 0 obj\n".encode() + b + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode()
        for o in offs:
            out += f"{o:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {len(objs)+1} /Root {cat} 0 R /Info {info} 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)
