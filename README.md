# ✂️ Moldes: ropa y peluches en Python

Hace moldes de costura listos para imprimir en hojas A4 (o Carta/A3), con margen de costura, piquetes, letras de unión, flecha de hilo, cuadrado de prueba y mapa para pegar las hojas.

- **Ropa:** el molde se *programa* a partir de tus medidas (por ahora remera básica y falda circular).
- **Peluche:** subís un modelo 3D (`.obj`) dividido en piezas y el programa aplana cada pieza (LSCM + ARAP), agrega costuras y te avisa cuánto se deforma.

Funciona de dos formas con **el mismo código Python**:

1. **Página web** (GitHub Pages): el Python corre dentro del navegador con [Pyodide](https://pyodide.org). No hace falta servidor y anda en el celular.
2. **Terminal:** `python -m moldes ...`

## Activar la página en GitHub Pages

1. En el repositorio, entrá en **Settings → Pages**.
2. En *Build and deployment → Source* elegí **Deploy from a branch**.
3. En *Branch* elegí **main** y la carpeta **/ (root)**, y tocá **Save**.
4. Esperá 1 o 2 minutos. La página queda en `https://<tu-usuario>.github.io/<nombre-del-repo>/`.

En el plan gratis de GitHub, Pages funciona con repositorios **públicos**. La primera carga tarda un poco porque descarga Python, numpy, scipy y shapely; después el navegador los guarda en caché.

## Uso desde la terminal

```bash
pip install -r requirements.txt

python -m moldes ropa remera --pecho 92 --largo_total 65 --svg
python -m moldes ropa falda_circular --cintura 72 --largo_falda 50 --hoja Carta
python -m moldes peluche ejemplos/rana.obj --altura 35
```

## Preparar un peluche en Blender

1. Modelá con formas suaves. Los detalles finos (ojos, boca) van bordados o aplicados.
2. Definí las piezas de alguna de estas formas:
   - **Por objetos/grupos:** separá cada pieza (*Edit Mode → P → Selection*) y exportá con *File → Export → Wavefront (.obj)* marcando **Object Groups**.
   - **Por islas UV:** marcá costuras (*Edge → Mark Seam*), hacé *UV → Unwrap* y exportá con UV. En la web elegí "Por islas UV".
3. Cada pieza tiene que poder abrirse plana. Una esfera entera o un tubo necesitan costuras. Si una pieza se deforma más de ~6 %, el programa te avisa: agregá una pinza o dividila.
4. Blender exporta con **Y arriba** por defecto (opción *Forward/Up* del exportador). Si tu modelo aparece acostado, cambiá el eje vertical.

El archivo `ejemplos/rana.obj` es una rana simple de prueba (lo genera `ejemplos/generar_rana.py`).

## Cómo leer el molde

| Marca | Significado |
|---|---|
| Línea continua | Línea de corte (ya incluye el margen) |
| Línea punteada | Línea de costura |
| Letra + piquete | Se cose con la otra pieza que tiene la misma letra |
| Flecha HILO | Paralela al hilo de la tela (orillo) |
| Flecha PELO / HILO | En peluches: sentido del pelo de la tela, hacia abajo del muñeco |
| DOBLEZ DE LA TELA | Ese borde va sobre el doblez y no lleva margen |

Las piezas de peluche se ven desde el **derecho** de la tela.

## Estructura

```
index.html, app.js, estilo.css   página web (carga Pyodide y three.js desde CDN)
moldes/
  pieza.py      Pieza: contorno, margen (shapely), doblez, hilo, marcas
  ropa.py       moldes paramétricos (agregá prendas acá)
  peluche.py    lectura de OBJ, separación en piezas, letras de unión, sentido del pelo
  aplanar.py    LSCM + ARAP con numpy/scipy
  salida.py     acomodo de piezas, PDF en hojas, SVG a tamaño real
  pdf.py        escritor de PDF mínimo (sin dependencias)
  dibujo.py     dibujo de una pieza (compartido por PDF y SVG)
  web.py        funciones que llama la página
  __main__.py   uso por terminal
ejemplos/       rana de ejemplo
```

### Agregar una prenda

En `moldes/ropa.py`, escribí una función que reciba las medidas y devuelva `(piezas, informe)`, y registrala en `PRENDAS` con sus parámetros. La página arma el formulario sola. Si agregás un archivo `.py` nuevo, sumalo también a `ARCHIVOS_PY` en `app.js`.

## Ideas para seguir

- Más prendas, o integrar [GarmentCode/pygarment](https://github.com/maria-korosteleva/GarmentCode) para moldes más avanzados.
- Detectar piezas iguales o en espejo y juntarlas ("Cortar 2").
- Pinzas automáticas cuando una pieza se deforma mucho.
- Exportar DXF para plotter de corte.

Licencia MIT.
