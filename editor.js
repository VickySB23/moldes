// Editor de prendas personalizadas: medidas, fórmulas, puntos, curvas y piezas.
// El cálculo lo hace Python (moldes/personal.py); acá solo se edita y se dibuja.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NS = "http://www.w3.org/2000/svg";
const CLAVE_ACTUAL = "moldes:editor";
const CLAVE_LIBRERIA = "moldes:prendas";

let api = null;
let ESQ = null;            // tipos de punto/curva (vienen de Python)
let prenda = null;         // la prenda que se está editando
let ev = null;             // último resultado de evaluar
let seleccion = null;      // id de punto seleccionado
let historial = [], futuro = [];
let ultimoGuardado = "";
let vista = { x: -5, y: -5, w: 100, h: 80 };
let opciones = { construccion: true, nombres: true, margen: true, rejilla: true };

// ------------------------------------------------------------------ plantillas
const NUEVA = () => ({
  formato: "moldes-prenda", version: 1, nombre: "Mi prenda", descripcion: "", margen: 1,
  medidas: [
    { id: "ancho", nombre: "Ancho", valor: 40 },
    { id: "alto", nombre: "Alto", valor: 50 },
  ],
  variables: [],
  puntos: [
    { id: "A", tipo: "xy", x: "0", y: "0" },
    { id: "B", tipo: "desde", base: "A", dx: "ancho", dy: "0" },
    { id: "C", tipo: "desde", base: "B", dx: "0", dy: "alto" },
    { id: "D", tipo: "desde", base: "A", dx: "0", dy: "alto" },
  ],
  curvas: [],
  piezas: [{ nombre: "Pieza 1", cortar: "Cortar 2", color: "#cfe8b0", contorno: ["A", "B", "C", "D"],
    doblez: [], hilo: [], marcas: [], margenes: [], lineas: [], notas: "" }],
  controles: [],
});

// ------------------------------------------------------------------ utilidades
const lista = (v) => (Array.isArray(v) ? v : String(v || "").split(/[\s,;]+/)).filter(Boolean);
const textoLista = (v) => lista(v).join(", ");
function leerLS(k) { try { return JSON.parse(localStorage.getItem(k)); } catch (_) { return null; } }
function guardarLS(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (_) { return false; } }

function idLibre(prefijo, usados) {
  if (!prefijo) {
    for (let i = 0; i < 26 * 27; i++) {
      const a = i < 26 ? String.fromCharCode(65 + i)
        : String.fromCharCode(64 + Math.floor(i / 26)) + String.fromCharCode(65 + (i % 26));
      if (!usados.has(a)) return a;
    }
  }
  for (let i = 1; ; i++) if (!usados.has(prefijo + i)) return prefijo + i;
}
function idsUsados() {
  const s = new Set();
  for (const g of ["medidas", "variables", "puntos", "curvas"]) for (const e of prenda[g] || []) s.add(e.id);
  return s;
}

function normalizar(p) {
  const n = Object.assign(NUEVA(), p);
  for (const g of ["medidas", "variables", "puntos", "curvas", "piezas", "controles"]) n[g] = n[g] || [];
  for (const pz of n.piezas) {
    for (const k of ["marcas", "margenes", "lineas"]) pz[k] = pz[k] || [];
    for (const k of ["contorno", "doblez", "hilo"]) pz[k] = lista(pz[k]);
    for (const l of pz.lineas) l.puntos = lista(l.puntos);
  }
  for (const c of n.curvas) c.puntos = lista(c.puntos);
  return n;
}

// rutas tipo "piezas.0.marcas.1.texto"
function leerRuta(ruta) { return ruta.split(".").reduce((o, k) => (o == null ? o : o[k]), prenda); }
function ponerRuta(ruta, valor) {
  const ks = ruta.split(".");
  const ult = ks.pop();
  const obj = ks.reduce((o, k) => o[k], prenda);
  obj[ult] = valor;
}

// ------------------------------------------------------------------ historial / guardado
function instantanea() { return JSON.stringify(prenda); }
let tHist = null;
function cambio(estructural = false) {
  clearTimeout(tHist);
  const pre = ultimoGuardado;
  tHist = setTimeout(() => {
    const ahora = instantanea();
    if (ahora !== pre && pre) { historial.push(pre); if (historial.length > 200) historial.shift(); futuro = []; }
    ultimoGuardado = ahora;
    guardarLS(CLAVE_ACTUAL, prenda);
    botonesHistorial();
  }, estructural ? 0 : 500);
  if (estructural) render();
  programarEvaluacion();
}
function deshacer() {
  if (!historial.length) return;
  futuro.push(instantanea());
  prenda = normalizar(JSON.parse(historial.pop()));
  ultimoGuardado = instantanea();
  guardarLS(CLAVE_ACTUAL, prenda);
  render(); evaluar(); botonesHistorial();
}
function rehacer() {
  if (!futuro.length) return;
  historial.push(instantanea());
  prenda = normalizar(JSON.parse(futuro.pop()));
  ultimoGuardado = instantanea();
  guardarLS(CLAVE_ACTUAL, prenda);
  render(); evaluar(); botonesHistorial();
}
function botonesHistorial() {
  $("ed-deshacer").disabled = !historial.length;
  $("ed-rehacer").disabled = !futuro.length;
}

function cargarPrenda(p, { ajustar = true } = {}) {
  prenda = normalizar(p);
  historial = []; futuro = [];
  ultimoGuardado = instantanea();
  guardarLS(CLAVE_ACTUAL, prenda);
  seleccion = null;
  render(); evaluar(); botonesHistorial();
  if (ajustar) ajustarVista();
}

// ------------------------------------------------------------------ renombrar
const CAMPOS_REF = ["base", "a", "b", "c", "d", "centro", "curva"];
function renombrar(viejo, nuevo) {
  if (!viejo || viejo === nuevo) return;
  const re = new RegExp(`(^|[^A-Za-z0-9_.])${viejo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![A-Za-z0-9_])`, "g");
  const enFormula = (s) => (typeof s === "string" ? s.replace(re, (m, a) => a + nuevo) : s);
  const enLista = (l) => lista(l).map((x) => (x === viejo ? nuevo : x));
  for (const v of prenda.variables) v.formula = enFormula(v.formula);
  for (const p of prenda.puntos) {
    for (const k of Object.keys(p)) {
      if (k === "id" || k === "tipo") continue;
      if (CAMPOS_REF.includes(k)) { if (p[k] === viejo) p[k] = nuevo; } else p[k] = enFormula(p[k]);
    }
  }
  for (const c of prenda.curvas) c.puntos = enLista(c.puntos);
  for (const pz of prenda.piezas) {
    pz.contorno = enLista(pz.contorno); pz.doblez = enLista(pz.doblez); pz.hilo = enLista(pz.hilo);
    for (const m of pz.marcas) if (m.punto === viejo) m.punto = nuevo;
    for (const m of pz.margenes) {
      if (m.desde === viejo) m.desde = nuevo;
      if (m.hasta === viejo) m.hasta = nuevo;
      m.margen = enFormula(m.margen);
    }
    for (const l of pz.lineas) l.puntos = enLista(l.puntos);
  }
  for (const c of prenda.controles) for (const k of ["formula", "min", "max"]) c[k] = enFormula(c[k]);
  if (seleccion === viejo) seleccion = nuevo;
}

// ------------------------------------------------------------------ formulario
function campo({ ruta, valor, etiqueta = "", clase = "", tipo = "text", acepta = "", lista: dl = "", ph = "", ancho = "" }) {
  return `<label class="ed-campo ${clase}" ${ancho ? `style="flex-basis:${ancho}"` : ""}>` +
    (etiqueta ? `<span>${esc(etiqueta)}</span>` : "") +
    `<input type="${tipo}" data-ruta="${ruta}" value="${esc(valor)}" ${acepta ? `data-acepta="${acepta}"` : ""}` +
    ` ${dl ? `list="${dl}"` : ""} placeholder="${esc(ph)}" spellcheck="false" autocomplete="off"` +
    `${tipo === "number" ? ' step="0.1"' : ""}></label>`;
}
const boton = (accion, txt, titulo = "", extra = "") =>
  `<button type="button" class="ed-mini ${extra}" data-accion="${accion}" title="${esc(titulo)}">${txt}</button>`;

function seccion(id, titulo, cuerpo, ayuda = "") {
  const abierta = (leerLS("moldes:secciones") || {})[id] !== false;
  return `<details class="ed-seccion" data-seccion="${id}" ${abierta ? "open" : ""}>` +
    `<summary>${titulo}<span class="ed-cuenta" id="cuenta-${id}"></span></summary>` +
    (ayuda ? `<p class="ed-ayuda">${ayuda}</p>` : "") + cuerpo + `</details>`;
}

function render() {
  const P = prenda;
  let h = "";
  h += `<div class="ed-fila ed-cabecera">` +
    campo({ ruta: "nombre", valor: P.nombre, etiqueta: "Nombre de la prenda", ancho: "60%" }) +
    campo({ ruta: "margen", valor: P.margen, etiqueta: "Margen general (cm)", tipo: "number", ancho: "30%" }) +
    campo({ ruta: "descripcion", valor: P.descripcion, etiqueta: "Descripción", ancho: "100%" }) + `</div>`;

  // medidas
  let b = "";
  P.medidas.forEach((m, i) => {
    b += `<div class="ed-fila" id="fila-medidas-${esc(m.id)}">` +
      campo({ ruta: `medidas.${i}.id`, valor: m.id, etiqueta: "nombre", clase: "ed-id" }) +
      campo({ ruta: `medidas.${i}.nombre`, valor: m.nombre, etiqueta: "descripción", ancho: "45%" }) +
      campo({ ruta: `medidas.${i}.valor`, valor: m.valor, etiqueta: "cm", tipo: "number", clase: "ed-num" }) +
      boton(`borrar:medidas:${i}`, "✕", "Borrar medida", "ed-borrar") + `<div class="ed-msg"></div></div>`;
  });
  b += boton("agregar:medidas", "+ Medida", "", "ed-agregar");
  h += seccion("medidas", "📏 Medidas", b, "Los valores que cambian para cada persona. Usalas por su nombre en las fórmulas.");

  // variables
  b = "";
  P.variables.forEach((v, i) => {
    b += `<div class="ed-fila" id="fila-variables-${esc(v.id)}">` +
      campo({ ruta: `variables.${i}.id`, valor: v.id, etiqueta: "nombre", clase: "ed-id" }) +
      campo({ ruta: `variables.${i}.formula`, valor: v.formula, etiqueta: "fórmula", clase: "ed-formula", ancho: "45%" }) +
      `<span class="ed-valor" data-valor="variables:${esc(v.id)}"></span>` +
      boton(`borrar:variables:${i}`, "✕", "Borrar variable", "ed-borrar") +
      campo({ ruta: `variables.${i}.nota`, valor: v.nota || "", ph: "nota (opcional)", clase: "ed-nota", ancho: "100%" }) +
      `<div class="ed-msg"></div></div>`;
  });
  b += boton("agregar:variables", "+ Variable", "", "ed-agregar");
  h += seccion("variables", "🧮 Variables", b, "Cuentas intermedias, por ejemplo <code>(cadera + holgura) / 4</code>.");

  // puntos
  b = "";
  P.puntos.forEach((p, i) => {
    const tipo = ESQ.puntos[p.tipo] ? p.tipo : "xy";
    const ops = Object.entries(ESQ.puntos).map(([k, t]) =>
      `<option value="${k}" ${k === tipo ? "selected" : ""}>${esc(t.nombre)}</option>`).join("");
    b += `<div class="ed-fila ed-punto ${seleccion === p.id ? "sel" : ""}" id="fila-puntos-${esc(p.id)}" data-punto="${esc(p.id)}">` +
      campo({ ruta: `puntos.${i}.id`, valor: p.id, etiqueta: "punto", clase: "ed-id" }) +
      `<label class="ed-campo ed-tipo"><span>herramienta</span><select data-ruta="puntos.${i}.tipo">${ops}</select></label>` +
      `<span class="ed-valor" data-valor="puntos:${esc(p.id)}"></span>` +
      boton(`borrar:puntos:${i}`, "✕", "Borrar punto", "ed-borrar") +
      `<div class="ed-campos">` +
      ESQ.puntos[tipo].campos.map((c) => campo({
        ruta: `puntos.${i}.${c.id}`, valor: p[c.id] ?? "", etiqueta: c.etiqueta,
        clase: c.tipo === "formula" ? "ed-formula" : "ed-ref",
        acepta: c.tipo === "formula" ? "formula" : c.tipo, lista: c.tipo === "punto" ? "dl-puntos" : c.tipo === "curva" ? "dl-curvas" : "",
      })).join("") + `</div><div class="ed-msg"></div></div>`;
  });
  b += `<div class="ed-fila">` + boton("agregar:puntos", "+ Punto", "", "ed-agregar") + `</div>`;
  h += seccion("puntos", "📍 Puntos", b,
    "X hacia la derecha, Y hacia <b>abajo</b>, en cm. Ángulos: 0° derecha, 90° arriba. " +
    "Con un campo de punto activo, tocá un punto en el dibujo para elegirlo.");

  // curvas
  b = "";
  P.curvas.forEach((c, i) => {
    const ops = Object.entries(ESQ.curvas).map(([k, t]) =>
      `<option value="${k}" ${k === c.tipo ? "selected" : ""}>${esc(t)}</option>`).join("");
    b += `<div class="ed-fila" id="fila-curvas-${esc(c.id)}">` +
      campo({ ruta: `curvas.${i}.id`, valor: c.id, etiqueta: "curva", clase: "ed-id" }) +
      `<label class="ed-campo ed-tipo"><span>tipo</span><select data-ruta="curvas.${i}.tipo">${ops}</select></label>` +
      `<span class="ed-valor" data-valor="curvas:${esc(c.id)}"></span>` +
      boton(`borrar:curvas:${i}`, "✕", "Borrar curva", "ed-borrar") +
      campo({ ruta: `curvas.${i}.puntos`, valor: textoLista(c.puntos), etiqueta: "puntos (en orden)", acepta: "lista", clase: "ed-lista", ancho: "100%" }) +
      `<div class="ed-msg"></div></div>`;
  });
  b += boton("agregar:curvas", "+ Curva", "", "ed-agregar");
  h += seccion("curvas", "〰️ Curvas", b,
    "Bézier: inicio, control, control, fin (los controles son puntos que «tiran» de la curva). " +
    "Suave: pasa por todos los puntos. Su largo se usa con <code>largo(curva)</code>.");

  // piezas
  b = "";
  P.piezas.forEach((pz, i) => {
    const r = `piezas.${i}`;
    b += `<div class="ed-pieza" id="fila-piezas-${i}">` +
      `<div class="ed-fila">` +
      `<input type="color" data-ruta="${r}.color" value="${esc(pz.color || "#cfe8b0")}" title="Color">` +
      campo({ ruta: `${r}.nombre`, valor: pz.nombre, etiqueta: "pieza", ancho: "35%" }) +
      campo({ ruta: `${r}.cortar`, valor: pz.cortar, etiqueta: "cortar", ancho: "35%" }) +
      boton(`duplicar:piezas:${i}`, "⧉", "Duplicar pieza") +
      boton(`borrar:piezas:${i}`, "✕", "Borrar pieza", "ed-borrar") + `</div>` +
      `<div class="ed-fila">` +
      campo({ ruta: `${r}.contorno`, valor: textoLista(pz.contorno), etiqueta: "contorno: puntos y curvas en orden (se cierra solo)", acepta: "lista", clase: "ed-lista", ancho: "100%" }) +
      campo({ ruta: `${r}.doblez`, valor: textoLista(pz.doblez), etiqueta: "doblez (2 puntos)", acepta: "lista", ancho: "30%" }) +
      campo({ ruta: `${r}.hilo`, valor: textoLista(pz.hilo), etiqueta: "hilo (2 puntos, vacío = auto)", acepta: "lista", ancho: "30%" }) +
      `<label class="ed-check"><input type="checkbox" data-ruta="${r}.desplegar" ${pz.desplegar ? "checked" : ""}> desplegar en el doblez</label>` +
      `</div>` +
      `<div class="ed-sub"><b>Piquetes y letras de unión</b>` +
      pz.marcas.map((m, k) => `<div class="ed-fila">` +
        campo({ ruta: `${r}.marcas.${k}.punto`, valor: m.punto, etiqueta: "en el punto", acepta: "punto", lista: "dl-puntos", clase: "ed-ref" }) +
        campo({ ruta: `${r}.marcas.${k}.texto`, valor: m.texto || "", etiqueta: "letra", clase: "ed-num" }) +
        `<label class="ed-check"><input type="checkbox" data-ruta="${r}.marcas.${k}.piquete" ${m.piquete !== false ? "checked" : ""}> piquete</label>` +
        boton(`borrar:${r}.marcas:${k}`, "✕", "Borrar", "ed-borrar") + `</div>`).join("") +
      boton(`agregar:${r}.marcas`, "+ Piquete", "", "ed-agregar") + `</div>` +
      `<div class="ed-sub"><b>Margen distinto en un tramo</b> <small>(ruedo, cierre…)</small>` +
      pz.margenes.map((m, k) => `<div class="ed-fila">` +
        campo({ ruta: `${r}.margenes.${k}.desde`, valor: m.desde, etiqueta: "de", acepta: "punto", lista: "dl-puntos", clase: "ed-ref" }) +
        campo({ ruta: `${r}.margenes.${k}.hasta`, valor: m.hasta, etiqueta: "a", acepta: "punto", lista: "dl-puntos", clase: "ed-ref" }) +
        campo({ ruta: `${r}.margenes.${k}.margen`, valor: m.margen, etiqueta: "margen (cm)", clase: "ed-formula" }) +
        boton(`borrar:${r}.margenes:${k}`, "✕", "Borrar", "ed-borrar") + `</div>`).join("") +
      boton(`agregar:${r}.margenes`, "+ Margen", "", "ed-agregar") + `</div>` +
      `<div class="ed-sub"><b>Pinzas y líneas interiores</b>` +
      pz.lineas.map((l, k) => `<div class="ed-fila">` +
        campo({ ruta: `${r}.lineas.${k}.puntos`, valor: textoLista(l.puntos), etiqueta: "puntos (pinza: pata, vértice, pata)", acepta: "lista", clase: "ed-lista", ancho: "55%" }) +
        `<label class="ed-campo ed-tipo"><span>estilo</span><select data-ruta="${r}.lineas.${k}.estilo">` +
        Object.entries(ESQ.lineas).map(([v, t]) => `<option value="${v}" ${v === (l.estilo || "linea") ? "selected" : ""}>${esc(t)}</option>`).join("") +
        `</select></label>` + boton(`borrar:${r}.lineas:${k}`, "✕", "Borrar", "ed-borrar") + `</div>`).join("") +
      boton(`agregar:${r}.lineas`, "+ Línea / pinza", "", "ed-agregar") + `</div>` +
      campo({ ruta: `${r}.notas`, valor: pz.notas || "", etiqueta: "notas para el molde", ancho: "100%" }) +
      `<div class="ed-info" data-valor="piezas:${i}"></div><div class="ed-msg"></div></div>`;
  });
  b += boton("agregar:piezas", "+ Pieza", "", "ed-agregar");
  h += seccion("piezas", "✂️ Piezas", b,
    "El contorno es la línea de costura. El margen se agrega solo. Las curvas se dan vuelta solas si hace falta.");

  // controles
  b = "";
  P.controles.forEach((c, i) => {
    b += `<div class="ed-fila" id="fila-controles-${i}">` +
      campo({ ruta: `controles.${i}.nombre`, valor: c.nombre, etiqueta: "control", ancho: "40%" }) +
      campo({ ruta: `controles.${i}.formula`, valor: c.formula, etiqueta: "fórmula", clase: "ed-formula", ancho: "45%" }) +
      boton(`borrar:controles:${i}`, "✕", "Borrar", "ed-borrar") +
      campo({ ruta: `controles.${i}.min`, valor: c.min ?? "", etiqueta: "mínimo", clase: "ed-formula" }) +
      campo({ ruta: `controles.${i}.max`, valor: c.max ?? "", etiqueta: "máximo", clase: "ed-formula" }) +
      `<span class="ed-valor" data-valor="controles:${i}"></span><div class="ed-msg"></div></div>`;
  });
  b += boton("agregar:controles", "+ Control", "", "ed-agregar");
  h += seccion("controles", "✅ Controles", b,
    "Cuentas para verificar el molde. Ej.: <code>largo(copa) - largo(sisa)</code> entre 1 y 2 cm de embebido.");

  $("ed-lado").innerHTML = h;
  // listas para autocompletar
  $("dl-puntos").innerHTML = prenda.puntos.map((p) => `<option value="${esc(p.id)}">`).join("");
  $("dl-curvas").innerHTML = prenda.curvas.map((c) => `<option value="${esc(c.id)}">`).join("");
  pintarResultados();
}

// ------------------------------------------------------------------ eventos del formulario
function valorDeInput(el) {
  if (el.type === "checkbox") return el.checked;
  const ruta = el.dataset.ruta;
  if (/\.(contorno|doblez|hilo|puntos)$/.test(ruta)) return lista(el.value);
  if (el.type === "number") { const v = parseFloat(String(el.value).replace(",", ".")); return isNaN(v) ? el.value : v; }
  return el.value;
}

function accion(txt) {
  const [que, donde, idx] = txt.split(":");
  const arr = leerRuta(donde);
  const usados = idsUsados();
  if (que === "borrar") {
    arr.splice(+idx, 1);
  } else if (que === "duplicar") {
    const copia = JSON.parse(JSON.stringify(arr[+idx]));
    copia.nombre = (copia.nombre || "Pieza") + " (copia)";
    arr.splice(+idx + 1, 0, copia);
  } else if (que === "agregar") {
    if (donde === "medidas") arr.push({ id: idLibre("medida", usados), nombre: "", valor: 0 });
    else if (donde === "variables") arr.push({ id: idLibre("v", usados), formula: "0", nota: "" });
    else if (donde === "puntos") {
      const base = seleccion || (arr.length ? arr[arr.length - 1].id : "");
      arr.push(base ? { id: idLibre("", usados), tipo: "desde", base, dx: "0", dy: "5" }
        : { id: idLibre("", usados), tipo: "xy", x: "0", y: "0" });
      seleccion = arr[arr.length - 1].id;
    } else if (donde === "curvas") arr.push({ id: idLibre("curva", usados), tipo: "bezier", puntos: [] });
    else if (donde === "piezas") arr.push({ nombre: `Pieza ${arr.length + 1}`, cortar: "Cortar 2",
      color: ESQ.colores[arr.length % ESQ.colores.length], contorno: [], doblez: [], hilo: [],
      marcas: [], margenes: [], lineas: [], notas: "" });
    else if (donde === "controles") arr.push({ nombre: "", formula: "", min: "", max: "" });
    else if (donde.endsWith(".marcas")) arr.push({ punto: "", texto: "", piquete: true });
    else if (donde.endsWith(".margenes")) arr.push({ desde: "", hasta: "", margen: "3" });
    else if (donde.endsWith(".lineas")) arr.push({ puntos: [], estilo: "pinza" });
  }
  cambio(true);
  if (que === "agregar") {
    // enfocar el primer campo del elemento nuevo
    const filas = $("ed-lado").querySelectorAll(`[data-ruta^="${donde}.${arr.length - 1}."]`);
    const f = [...filas].find((x) => x.tagName === "INPUT" && !x.dataset.ruta.endsWith(".id")) || filas[0];
    if (f) { f.focus(); f.scrollIntoView({ block: "center", behavior: "smooth" }); }
  }
}

function conectarFormulario() {
  const lado = $("ed-lado");
  lado.addEventListener("input", (e) => {
    const el = e.target;
    if (!el.dataset.ruta || el.dataset.ruta.endsWith(".id")) return;
    if (el.tagName === "SELECT") return;
    ponerRuta(el.dataset.ruta, valorDeInput(el));
    cambio(false);
  });
  lado.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.dataset.ruta) return;
    if (el.dataset.ruta.endsWith(".id")) {
      const viejo = leerRuta(el.dataset.ruta);
      const nuevo = el.value.trim();
      if (!nuevo) { el.value = viejo; return; }
      ponerRuta(el.dataset.ruta, nuevo);
      renombrar(viejo, nuevo);
      cambio(true);
    } else if (el.tagName === "SELECT") {
      ponerRuta(el.dataset.ruta, el.value);
      cambio(true);
    } else if (el.type === "checkbox" || el.type === "color") {
      ponerRuta(el.dataset.ruta, valorDeInput(el));
      cambio(false);
    }
  });
  lado.addEventListener("click", (e) => {
    const b = e.target.closest("[data-accion]");
    if (b) { accion(b.dataset.accion); return; }
  });
  lado.addEventListener("focusin", (e) => {
    const fila = e.target.closest(".ed-punto");
    if (fila && fila.dataset.punto !== seleccion) { seleccion = fila.dataset.punto; marcarSeleccion(); dibujar(); }
  });
  lado.addEventListener("toggle", (e) => {
    const d = e.target.closest("details[data-seccion]");
    if (!d) return;
    const s = leerLS("moldes:secciones") || {};
    s[d.dataset.seccion] = d.open;
    guardarLS("moldes:secciones", s);
  }, true);
}

function marcarSeleccion() {
  $("ed-lado").querySelectorAll(".ed-punto").forEach((f) => f.classList.toggle("sel", f.dataset.punto === seleccion));
}

// elegir puntos/curvas tocando el dibujo
function insertarEnCampo(id, esCurva) {
  const el = document.activeElement;
  if (!el || !el.dataset || !el.dataset.acepta) return false;
  const ac = el.dataset.acepta;
  if (ac === "formula") {
    const ini = el.selectionStart ?? el.value.length, fin = el.selectionEnd ?? ini;
    const txt = esCurva ? `largo(${id})` : id;
    el.value = el.value.slice(0, ini) + txt + el.value.slice(fin);
    el.setSelectionRange(ini + txt.length, ini + txt.length);
  } else if (ac === "lista") {
    el.value = el.value.trim() ? el.value.replace(/[\s,]*$/, "") + ", " + id : id;
  } else if (ac === "punto" && !esCurva) el.value = id;
  else if (ac === "curva" && esCurva) el.value = id;
  else return false;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  if (el.dataset.ruta.endsWith(".id")) el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

// ------------------------------------------------------------------ evaluación
let tEval = null;
function programarEvaluacion() { clearTimeout(tEval); tEval = setTimeout(evaluar, 120); }
function margenVista() { const m = parseFloat($("per-margen").value); return isNaN(m) ? (prenda.margen ?? 1) : m; }
function evaluar() {
  if (!api) return;
  try {
    ev = JSON.parse(api.evaluar_personal(JSON.stringify(prenda), margenVista()));
  } catch (err) {
    console.error(err);
    ev = { puntos: {}, curvas: {}, construccion: [], piezas: [], variables: {}, controles: [], largos: {},
      errores: [{ donde: "prenda", campo: "", mensaje: String(err.message || err).split("\n").filter(Boolean).pop() }] };
  }
  pintarResultados();
  dibujar();
}

function pintarResultados() {
  if (!ev) return;
  const lado = $("ed-lado");
  lado.querySelectorAll(".ed-fila.error, .ed-pieza.error").forEach((f) => f.classList.remove("error"));
  lado.querySelectorAll("input.error, select.error").forEach((f) => f.classList.remove("error"));
  lado.querySelectorAll(".ed-msg").forEach((m) => (m.textContent = ""));
  const fmt = (v) => (Math.round(v * 100) / 100).toLocaleString("es-AR");
  lado.querySelectorAll("[data-valor]").forEach((el) => {
    const [g, id] = el.dataset.valor.split(":");
    let t = "";
    if (g === "variables" && id in ev.variables) t = "= " + fmt(ev.variables[id]);
    if (g === "puntos" && ev.puntos[id]) t = `(${fmt(ev.puntos[id][0])}, ${fmt(ev.puntos[id][1])})`;
    if (g === "curvas" && id in ev.largos) t = `largo ${fmt(ev.largos[id])} cm`;
    if (g === "piezas" && ev.piezas[+id]) {
      const p = ev.piezas[+id];
      t = `Contorno ${fmt(p.perimetro)} cm · superficie ${fmt(p.area)} cm²`;
    }
    if (g === "controles" && ev.controles[+id]) {
      const c = ev.controles[+id];
      t = c.valor == null ? "" : `= ${fmt(c.valor)} ${c.ok === false ? "⚠️ fuera de rango" : c.ok ? "✔" : ""}`;
      el.classList.toggle("aviso", c.ok === false);
    }
    el.textContent = t;
  });
  const cuentas = { medidas: prenda.medidas.length, variables: prenda.variables.length, puntos: prenda.puntos.length,
    curvas: prenda.curvas.length, piezas: prenda.piezas.length, controles: prenda.controles.length };
  const errPorGrupo = {};
  for (const e of ev.errores) {
    const [g, id] = e.donde.split(":");
    errPorGrupo[g] = (errPorGrupo[g] || 0) + 1;
    const fila = $(`fila-${g}-${id}`);
    if (!fila) continue;
    fila.classList.add("error");
    const msg = fila.querySelector(":scope > .ed-msg");
    if (msg && !msg.textContent) msg.textContent = e.mensaje;
    if (e.campo) {
      const inp = [...fila.querySelectorAll("[data-ruta]")].find((x) => x.dataset.ruta.split(".").pop() === e.campo
        || x.dataset.ruta.endsWith("." + e.campo));
      if (inp) inp.classList.add("error");
    }
  }
  for (const [g, n] of Object.entries(cuentas)) {
    const c = $(`cuenta-${g}`);
    if (c) c.innerHTML = ` <small>${n}</small>` + (errPorGrupo[g] ? ` <em class="ed-err">${errPorGrupo[g]} con error</em>` : "");
  }
  const n = ev.errores.length;
  const gen = ev.errores.find((e) => !$(`fila-${e.donde.split(":")[0]}-${e.donde.split(":")[1]}`));
  $("ed-estado").innerHTML = n
    ? `<span class="ed-err">⚠️ ${n} ${n === 1 ? "problema" : "problemas"}</span>` + (gen ? ` — ${esc(gen.mensaje)}` : " (marcados en rojo)")
    : `✔ Sin errores · ${ev.piezas.filter(Boolean).length} ${ev.piezas.filter(Boolean).length === 1 ? "pieza" : "piezas"}`;
}

// ------------------------------------------------------------------ dibujo
function el(tag, attrs = {}, padre = null) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (padre) padre.appendChild(e);
  return e;
}
const camino = (pts, cerrado = false) =>
  pts.length ? "M" + pts.map((p) => `${p[0]},${p[1]}`).join("L") + (cerrado ? "Z" : "") : "";

function limites() {
  const xs = [], ys = [];
  for (const p of Object.values(ev?.puntos || {})) { xs.push(p[0]); ys.push(p[1]); }
  for (const pz of ev?.piezas || []) if (pz) for (const p of pz.corte) { xs.push(p[0]); ys.push(p[1]); }
  if (!xs.length) return { x: -5, y: -5, w: 60, h: 60 };
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  return { x: x0, y: y0, w: Math.max(x1 - x0, 5), h: Math.max(y1 - y0, 5) };
}
function ajustarVista() {
  const svg = $("ed-svg");
  const r = svg.getBoundingClientRect();
  const asp = (r.height || 400) / (r.width || 600);
  const b = limites();
  const pad = Math.max(b.w, b.h) * 0.08 + 2;
  let w = b.w + 2 * pad, h = b.h + 2 * pad;
  if (h / w > asp) w = h / asp; else h = w * asp;
  vista = { x: b.x + b.w / 2 - w / 2, y: b.y + b.h / 2 - h / 2, w, h };
  dibujar();
}

function dibujar() {
  const svg = $("ed-svg");
  if (!svg || !ev) return;
  const r = svg.getBoundingClientRect();
  if (r.width) vista.h = vista.w * (r.height / r.width);
  svg.setAttribute("viewBox", `${vista.x} ${vista.y} ${vista.w} ${vista.h}`);
  svg.innerHTML = "";
  const px = vista.w / (r.width || 600);    // cm por píxel de pantalla
  const fs = 12 * px;

  if (opciones.rejilla) {
    const g = el("g", { class: "rejilla" }, svg);
    const paso = px < 0.08 ? 1 : px < 0.4 ? 5 : 10;
    const x0 = Math.floor(vista.x / paso) * paso, y0 = Math.floor(vista.y / paso) * paso;
    let d1 = "", d5 = "";
    for (let x = x0; x <= vista.x + vista.w; x += paso) (Math.round(x) % (paso * 5) === 0 ? (d5 += `M${x},${vista.y}V${vista.y + vista.h}`) : (d1 += `M${x},${vista.y}V${vista.y + vista.h}`));
    for (let y = y0; y <= vista.y + vista.h; y += paso) (Math.round(y) % (paso * 5) === 0 ? (d5 += `M${vista.x},${y}H${vista.x + vista.w}`) : (d1 += `M${vista.x},${y}H${vista.x + vista.w}`));
    el("path", { d: d1, class: "rej1" }, g);
    el("path", { d: d5, class: "rej5" }, g);
    el("path", { d: `M${vista.x},0H${vista.x + vista.w}M0,${vista.y}V${vista.y + vista.h}`, class: "rej0" }, g);
  }

  const gp = el("g", {}, svg);
  ev.piezas.forEach((pz) => {
    if (!pz) return;
    const g = el("g", { class: "pieza" }, gp);
    if (opciones.margen && pz.corte.length) el("path", { d: camino(pz.corte, true), fill: pz.color, class: "corte" }, g);
    el("path", { d: camino(pz.contorno, true), fill: opciones.margen ? "none" : pz.color, class: opciones.margen ? "costura" : "costura sola" }, g);
    if (pz.doblez) el("path", { d: camino(pz.doblez), class: "doblez" }, g);
    for (const [pts, est] of pz.lineas) el("path", { d: camino(pts), class: "linea-" + est }, g);
    if (pz.hilo) {
      const [a, b] = pz.hilo;
      const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1, ux = dx / L, uy = dy / L, s = 0.6;
      const punta = (p, sg) => `M${p[0] - sg * ux * s - uy * s * 0.45},${p[1] - sg * uy * s + ux * s * 0.45}L${p[0]},${p[1]}L${p[0] - sg * ux * s + uy * s * 0.45},${p[1] - sg * uy * s - ux * s * 0.45}`;
      el("path", { d: camino([a, b]) + punta(b, 1) + punta(a, -1), class: "hilo" }, g);
    }
    for (const m of pz.marcas) {
      el("path", { d: `M${m.p[0] + m.n[0] * 0.3},${m.p[1] + m.n[1] * 0.3}L${m.p[0] - m.n[0] * 0.8},${m.p[1] - m.n[1] * 0.8}`, class: "piquete" }, g);
      if (m.t) { const t = el("text", { x: m.p[0] + m.n[0] * 1.1, y: m.p[1] + m.n[1] * 1.1, "font-size": fs * 1.1, class: "letra" }, g); t.textContent = m.t; }
    }
    const t = el("text", { x: pz.etiqueta[0], y: pz.etiqueta[1], "font-size": fs * 1.3, class: "nombre-pieza" }, g);
    t.textContent = pz.nombre;
  });

  if (opciones.construccion) {
    el("path", { d: ev.construccion.map((l) => camino(l)).join(""), class: "construccion" }, svg);
  }
  const gc = el("g", {}, svg);
  for (const [id, pts] of Object.entries(ev.curvas)) {
    el("path", { d: camino(pts), class: "curva" }, gc);
    const hit = el("path", { d: camino(pts), class: "toque", "data-curva": id }, gc);
    const tt = el("title", {}, hit); tt.textContent = `${id} · ${ev.largos[id]} cm`;
  }
  const gpt = el("g", {}, svg);
  for (const [id, p] of Object.entries(ev.puntos)) {
    const g = el("g", { class: "punto" + (id === seleccion ? " sel" : ""), "data-punto": id }, gpt);
    el("circle", { cx: p[0], cy: p[1], r: 9 * px, class: "toque" }, g);
    el("circle", { cx: p[0], cy: p[1], r: (id === seleccion ? 4.5 : 3) * px }, g);
    if (opciones.nombres || id === seleccion) {
      const t = el("text", { x: p[0] + 5 * px, y: p[1] - 5 * px, "font-size": fs }, g);
      t.textContent = id;
    }
    const tt = el("title", {}, g); tt.textContent = `${id} (${p[0]}, ${p[1]})`;
  }
}

function conectarLienzo() {
  const svg = $("ed-svg");
  const aCm = (e) => {
    const r = svg.getBoundingClientRect();
    return [vista.x + (e.clientX - r.left) / r.width * vista.w, vista.y + (e.clientY - r.top) / r.height * vista.h];
  };
  let arrastre = null;
  svg.addEventListener("mousedown", (e) => {
    e.preventDefault();   // mantiene el foco en el campo que se está editando
    arrastre = { x: e.clientX, y: e.clientY, vx: vista.x, vy: vista.y, movio: false };
  });
  window.addEventListener("mousemove", (e) => {
    const [cx, cy] = aCm(e);
    if (e.target.closest && e.target.closest("#ed-svg")) $("ed-coord").textContent = `x ${cx.toFixed(1)} · y ${cy.toFixed(1)} cm`;
    if (!arrastre) return;
    const r = svg.getBoundingClientRect();
    const dx = e.clientX - arrastre.x, dy = e.clientY - arrastre.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) arrastre.movio = true;
    vista.x = arrastre.vx - dx / r.width * vista.w;
    vista.y = arrastre.vy - dy / r.height * vista.h;
    svg.setAttribute("viewBox", `${vista.x} ${vista.y} ${vista.w} ${vista.h}`);
  });
  window.addEventListener("mouseup", (e) => {
    if (!arrastre) return;
    const movio = arrastre.movio;
    arrastre = null;
    if (movio) { dibujar(); return; }
    const gp = e.target.closest && e.target.closest("[data-punto]");
    const gc = e.target.closest && e.target.closest("[data-curva]");
    if (gp && svg.contains(gp)) {
      const id = gp.dataset.punto;
      if (!insertarEnCampo(id, false)) {
        seleccion = id; marcarSeleccion(); dibujar();
        const f = $(`fila-puntos-${id}`);
        if (f) { f.closest("details").open = true; f.scrollIntoView({ block: "center", behavior: "smooth" }); f.classList.add("brillo"); setTimeout(() => f.classList.remove("brillo"), 900); }
      }
    } else if (gc && svg.contains(gc)) {
      insertarEnCampo(gc.dataset.curva, true);
    }
  });
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const [cx, cy] = aCm(e);
    const f = Math.exp(e.deltaY * 0.0015);
    const w = Math.min(Math.max(vista.w * f, 2), 2000);
    const k = w / vista.w;
    vista = { x: cx - (cx - vista.x) * k, y: cy - (cy - vista.y) * k, w, h: vista.h * k };
    dibujar();
  }, { passive: false });
  // táctil: arrastrar con un dedo
  let toque = null;
  svg.addEventListener("touchstart", (e) => { if (e.touches.length === 1) toque = { x: e.touches[0].clientX, y: e.touches[0].clientY, vx: vista.x, vy: vista.y }; }, { passive: true });
  svg.addEventListener("touchmove", (e) => {
    if (!toque || e.touches.length !== 1) return;
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    vista.x = toque.vx - (e.touches[0].clientX - toque.x) / r.width * vista.w;
    vista.y = toque.vy - (e.touches[0].clientY - toque.y) / r.height * vista.h;
    dibujar();
  }, { passive: false });
  svg.addEventListener("touchend", () => (toque = null));
  new ResizeObserver(() => dibujar()).observe(svg);
  for (const k of Object.keys(opciones)) {
    const c = $(`ed-ver-${k}`);
    c.checked = opciones[k];
    c.addEventListener("change", () => { opciones[k] = c.checked; guardarLS("moldes:vista", opciones); dibujar(); });
  }
  $("ed-ajustar").addEventListener("click", ajustarVista);
}

// ------------------------------------------------------------------ librería y archivos
export function prendasGuardadas() { return leerLS(CLAVE_LIBRERIA) || {}; }
function claveDe(nombre) { return (nombre || "prenda").trim().toLowerCase().replace(/\s+/g, "_").slice(0, 60); }

function refrescarLibreria() {
  const lib = prendasGuardadas();
  const sel = $("ed-libreria");
  sel.innerHTML = `<option value="">📂 Mis prendas…</option>` +
    Object.entries(lib).sort((a, b) => (a[1].nombre || "").localeCompare(b[1].nombre || ""))
      .map(([k, p]) => `<option value="${esc(k)}">${esc(p.nombre || k)}</option>`).join("");
  $("ed-borrar-guardada").disabled = true;
  document.dispatchEvent(new CustomEvent("moldes:prendas-cambiaron"));
}

function descargar(nombre, texto, tipo) {
  const u = URL.createObjectURL(new Blob([texto], { type: tipo }));
  const a = document.createElement("a");
  a.href = u; a.download = nombre;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 2000);
}

function aviso(msg, tipo = "ok") {
  const e = $("estado");
  e.textContent = msg;
  e.className = "estado " + tipo;
}

function conectarBarra() {
  $("ed-nueva").addEventListener("click", () => {
    if (historial.length && !confirm("¿Empezar una prenda nueva? Lo que no guardaste en «Mis prendas» se pierde.")) return;
    cargarPrenda(NUEVA());
  });
  $("ed-ejemplo").addEventListener("click", async () => {
    if (historial.length && !confirm("¿Abrir el ejemplo? Lo que no guardaste en «Mis prendas» se pierde.")) return;
    const r = await fetch("ejemplos/falda_recta.json?v=" + Date.now());
    cargarPrenda(await r.json());
  });
  $("ed-guardar").addEventListener("click", () => {
    const lib = prendasGuardadas();
    const k = claveDe(prenda.nombre);
    if (lib[k] && JSON.stringify(lib[k]) !== instantanea() &&
      !confirm(`Ya hay una prenda «${prenda.nombre}» guardada. ¿Reemplazarla?`)) return;
    lib[k] = JSON.parse(instantanea());
    if (guardarLS(CLAVE_LIBRERIA, lib)) aviso(`Guardada en «Mis prendas»: ${prenda.nombre} ✔`);
    else aviso("No pude guardar en este navegador. Usá «Exportar» para bajar el archivo.", "error");
    refrescarLibreria();
    $("ed-libreria").value = k;
    $("ed-borrar-guardada").disabled = false;
  });
  $("ed-libreria").addEventListener("change", (e) => {
    const k = e.target.value;
    $("ed-borrar-guardada").disabled = !k;
    if (!k) return;
    const p = prendasGuardadas()[k];
    if (p) cargarPrenda(p);
  });
  $("ed-borrar-guardada").addEventListener("click", () => {
    const k = $("ed-libreria").value;
    const lib = prendasGuardadas();
    if (!k || !lib[k]) return;
    if (!confirm(`¿Borrar «${lib[k].nombre}» de «Mis prendas»? (no se puede deshacer)`)) return;
    delete lib[k];
    guardarLS(CLAVE_LIBRERIA, lib);
    refrescarLibreria();
  });
  $("ed-exportar").addEventListener("click", () =>
    descargar(claveDe(prenda.nombre) + ".json", JSON.stringify(prenda, null, 2), "application/json"));
  $("ed-importar").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try {
      const p = JSON.parse(await f.text());
      if (p.formato && p.formato !== "moldes-prenda") throw new Error("no es una prenda de Moldes");
      cargarPrenda(p);
      aviso(`Prenda importada: ${prenda.nombre} ✔`);
    } catch (err) {
      aviso("No pude abrir ese archivo: " + err.message, "error");
    }
  });
  $("ed-deshacer").addEventListener("click", deshacer);
  $("ed-rehacer").addEventListener("click", rehacer);
  document.addEventListener("keydown", (e) => {
    if (!$("panel-personal").classList.contains("activo")) return;
    const enCampo = /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "");
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !enCampo) { e.preventDefault(); e.shiftKey ? rehacer() : deshacer(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y" && !enCampo) { e.preventDefault(); rehacer(); }
  });
  $("per-margen").addEventListener("input", programarEvaluacion);
}

// ------------------------------------------------------------------ arranque
export async function iniciarEditor(apiPython, generar) {
  api = apiPython;
  ESQ = JSON.parse(api.esquema_personal());
  opciones = Object.assign(opciones, leerLS("moldes:vista") || {});
  conectarFormulario();
  conectarLienzo();
  conectarBarra();
  refrescarLibreria();
  $("btn-personal").addEventListener("click", () => generar(prenda, margenVista(), $("per-hoja").value));
  const guardada = leerLS(CLAVE_ACTUAL);
  if (guardada && guardada.puntos) cargarPrenda(guardada);
  else {
    try { cargarPrenda(await (await fetch("ejemplos/falda_recta.json")).json()); }
    catch (_) { cargarPrenda(NUEVA()); }
  }
  // al mostrar la pestaña por primera vez el lienzo recién tiene tamaño
  document.querySelector('[data-panel="panel-personal"]').addEventListener("click", () =>
    requestAnimationFrame(() => (vista.w > 0 && !ajustado ? (ajustado = true, ajustarVista()) : dibujar())));
}
let ajustado = false;
