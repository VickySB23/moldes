# ✂️ Moldes: ropa y peluches en Python

Hace moldes de costura listos para imprimir en hojas A4 (o Carta/A3), con margen de costura, piquetes, letras de unión, flecha de hilo, cuadrado de prueba y mapa para pegar las hojas.

- **Ropa:** el molde se *programa* a partir de tus medidas (por ahora remera básica y falda circular).
- **Mi prenda:** un editor para dibujar **tus propios moldes** con fórmulas que usan las medidas, como en patronaje sobre papel (o en programas como Seamly2D). Cambiás las medidas y todo se recalcula.
- **Peluche (taller 3D):** modelás el muñeco con formas que se funden como plastilina, armás un **maniquí con tus medidas** o subís un `.obj`. Después dibujás las costuras sobre el modelo, la página te dice qué piezas se aplanan bien y el programa aplana cada pieza (LSCM + ARAP) con márgenes, piquetes y letras de unión. Sobre el maniquí se pueden sacar moldes de ropa ajustados.

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

# modelo 3D de formas o maniquí, como .obj (para Blender u otro programa)
python -m moldes formas ejemplos/osito.json -o osito.obj
python -m moldes maniqui --base mujer_m --busto 90 --cintura 70 --tipo torso -o yo.obj

# prenda personalizada (archivo exportado desde «Mi prenda»)
python -m moldes personal ejemplos/falda_recta.json --medidas          # ver qué medidas usa
python -m moldes personal ejemplos/falda_recta.json --medida cintura=74 --medida cadera=100
```

## Prendas personalizadas («Mi prenda»)

En la pestaña **✏️ Mi prenda** armás el molde paso a paso, igual que trazándolo en papel:

1. **Medidas:** las que vas a pedir (`cintura`, `cadera`, `largo_falda`…). Los nombres van sin espacios ni acentos.
2. **Variables:** cuentas intermedias, como `Wq = (cadera + holgura) / 4`.
3. **Puntos:** cada punto se construye con una herramienta de patronaje:

   | Herramienta | Qué hace |
   |---|---|
   | Coordenadas (x, y) | Punto fijo (normalmente el primero, en 0, 0) |
   | Desde otro punto | Se corre `→ x` a la derecha y `↓ y` hacia abajo |
   | Largo y ángulo | A cierta distancia y ángulo (0° derecha, 90° arriba) |
   | Sobre una línea | Sobre la recta de A hacia B, a cierta distancia de A |
   | Punto medio | Entre dos puntos |
   | Cruce de dos líneas | Donde se cruzan las rectas AB y CD |
   | Perpendicular | Pie de la perpendicular desde un punto a una recta |
   | A cierta distancia sobre una línea | Por ejemplo, el largo de hombro desde el cuello hasta tocar la línea de caída |
   | Sobre una curva | A cierta distancia sobre una curva (negativo = desde el final) |

4. **Curvas:** *Bézier* (inicio, control, control, fin), *suave* (pasa por todos los puntos) o *poligonal*.
5. **Piezas:** el contorno (línea de costura) se escribe como una lista de puntos y curvas en orden, o tocándolos en el dibujo. Cada pieza puede llevar doblez (con la opción de *desplegar* la pieza entera), hilo, piquetes con letras de unión, pinzas (pata, vértice, pata), líneas punteadas y un margen distinto por tramo (por ejemplo 3 cm en el ruedo).
6. **Controles:** cuentas para verificar el molde, con mínimo y máximo. Por ejemplo, que la copa de manga mida entre 1 y 2 cm más que la sisa: `largo(copa) - largo(sisa_d) - largo(sisa_e)`.

**Fórmulas:** `+ - * / ** ( )`, decimales con punto, medidas y variables, `A.x`, `A.y`, `dist(A, B)`, `ang(A, B)`, `largo(curva)`, `largo(A, B, C)`, `raiz`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2` (en grados), `min`, `max`, `abs`, `redondear(x, 1)`, `si(condición, a, b)` y `pi`. Se evalúan de forma segura: no ejecutan código.

**Guardar:** *Guardar* la deja en «Mis prendas», en ese navegador, y también aparece en la pestaña Ropa con sus medidas como formulario. *Exportar* baja un `.json` para compartirla, guardarla como respaldo o usarla por terminal. Al renombrar un punto se actualizan todas las fórmulas y piezas que lo usan.

El formato del `.json` está documentado al principio de `moldes/personal.py`, y `ejemplos/falda_recta.json` es un ejemplo completo: falda recta con pinzas, costado curvo, ruedo de 3 cm, pretina y controles.

## Taller 3D (pestaña Peluche)

Funciona en tres pasos:

1. **Modelo**, con una de estas tres opciones:
   - **Formas:** esferas, cápsulas, cilindros, conos, cajas y donas que se funden con una unión suave, como plastilina (superficies implícitas + *surface nets*, en `moldes/formas.py`). Cada forma puede ir *unida*, *aparte* (una pieza suelta, como una oreja) o *restando* (para ahuecar), y con *espejo* izquierda/derecha. Se mueven, giran y escalan con las flechas en 3D o con números. Ejemplo: `ejemplos/osito.json`.
   - **Maniquí:** se arma con tus medidas (estatura, busto, bajo busto, cintura, cadera, cuello, hombros, talle, alto de cadera, entrepierna, brazo, muslo) o desde un talle de partida. Hay dos tipos: cuerpo completo con brazos en A, o maniquí de costura (solo el torso). El torso es un *loft* de elipses. Después **se mide la malla como con un centímetro** (envolvente convexa del corte) y se corrige hasta que busto, cintura y cadera coinciden con lo pedido. La **holgura** infla la superficie para que la prenda no quede justa.
   - **Archivo .obj:** sus grupos (`g`/`o`) se usan como costuras iniciales.
2. **Costuras y piezas:**
   - **Trazar:** tocás puntos y la costura sigue la superficie (camino más corto por la malla, suavizado).
   - **Cuchillo:** trazás una línea recta en la pantalla y corta de lado a lado la pieza que cruza. Los triángulos se parten exactamente sobre el plano, así la costura queda recta aunque la malla sea gruesa.
   - **Borrar** costuras y **Quitar pieza** (por ejemplo, la cabeza y los brazos del maniquí).
   - **Simetría izq/der**: lo que hacés de un lado se repite del otro.
   - Cada zona cerrada por costuras es una pieza. La lista avisa si una pieza está cerrada, si es un tubo o si se deforma mucho al aplanarse.
   - **Costuras de corpiño básico** marca de una vez el centro, los costados, los hombros, el escote, las sisas y la cintura del maniquí.
3. **Molde:** genera el PDF/SVG como siempre. Los modelos de formas y el maniquí salen en tamaño real.

Las costuras se guardan como posiciones y planos en 3D, no como números de vértice: si cambiás las formas o las medidas, se recalculan solas. El proyecto se guarda en el navegador y se puede exportar o importar como `.json`.

**Límites:** no hay simulación de tela. El molde es la superficie del modelo aplanada, así que conviene hacer una prueba en tela barata. Los moldes sobre el maniquí son bases ajustadas (con la holgura que elijas); escotes, largos y pinzas se agregan trazando costuras o retocando el molde.

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
editor.js                        editor de «Mi prenda» (formulario + dibujo en vivo)
taller.js                        taller 3D: formas, maniquí, costuras y piezas (three.js)
moldes/
  pieza.py      Pieza: contorno, margen (shapely), doblez, hilo, marcas
  ropa.py       moldes paramétricos (agregá prendas acá)
  personal.py   prendas personalizadas: fórmulas seguras, puntos, curvas, piezas
  formas.py     modelado con formas (SDF, unión suave, surface nets)
  maniqui.py    maniquí con medidas, calibrado midiendo la malla
  peluche.py    lectura de OBJ, separación en piezas, letras de unión, sentido del pelo
  aplanar.py    LSCM + ARAP con numpy/scipy
  salida.py     acomodo de piezas, PDF en hojas, SVG a tamaño real
  pdf.py        escritor de PDF mínimo (sin dependencias)
  dibujo.py     dibujo de una pieza (compartido por PDF y SVG)
  web.py        funciones que llama la página
  __main__.py   uso por terminal
ejemplos/       rana (.obj), osito (formas + costuras) y falda recta (prenda personalizada)
```

### Agregar una prenda

En `moldes/ropa.py`, escribí una función que reciba las medidas y devuelva `(piezas, informe)`, y registrala en `PRENDAS` con sus parámetros. La página arma el formulario sola. Si agregás un archivo `.py` nuevo, sumalo también a `ARCHIVOS_PY` en `app.js`.

## Ideas para seguir

- Taller 3D: más plantillas de costuras sobre el maniquí (falda, pantalón, manga), pinzas automáticas donde una pieza se deforma, y mover los puntos del maniquí con el mouse.
- En «Mi prenda»: herramientas de pinzas que rotan (traslado de pinzas), copiar y espejar puntos, y escalado por talles.
- Más prendas, o integrar [GarmentCode/pygarment](https://github.com/maria-korosteleva/GarmentCode) para moldes más avanzados.
- Detectar piezas iguales o en espejo y juntarlas ("Cortar 2").
- Pinzas automáticas cuando una pieza se deforma mucho.
- Exportar DXF para plotter de corte.

Licencia MIT.
