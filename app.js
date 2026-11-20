// Interfaz de la página: carga el paquete Python "moldes" en Pyodide y lo usa.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const VERSION = "0.1.0";
const ARCHIVOS_PY = [
  "__init__.py", "pieza.py", "dibujo.py", "pdf.py", "salida.py",
  "ropa.py", "aplanar.py", "peluche.py", "web.py",
];

const $ = (id) => document.getElementById(id);
const estado = (msg, tipo = "") => {
  const e = $("estado");
  e.textContent = msg;
  e.className = "estado " + tipo;
};

let py = null;
let api = null;
let textoObj = null;
let nombreObj = "peluche";
let urlsDescarga = [];

// ---------------------------------------------------------------- arranque
async function iniciar() {
  try {
    py = await loadPyodide();
    estado("Cargando numpy, scipy y shapely…");
    await py.loadPackage(["numpy", "scipy", "shapely"]);
    estado("Cargando el código de moldes…");
    py.FS.mkdirTree("/home/pyodide/moldes");
    for (const f of ARCHIVOS_PY) {
      const r = await fetch(`moldes/${f}?v=${VERSION}`);
      if (!r.ok) throw new Error(`No pude leer moldes/${f} (${r.status})`);
      py.FS.writeFile(`/home/pyodide/moldes/${f}`, await r.text());
    }
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
    api = py.pyimport("moldes.web");
    armarFormularioRopa();
    $("btn-ropa").disabled = false;
    $("btn-peluche").disabled = !textoObj;
    estado("Listo ✔", "ok");
  } catch (err) {
    console.error(err);
    estado("No se pudo iniciar Python: " + err.message, "error");
  }
}

// ---------------------------------------------------------------- pestañas
document.querySelectorAll(".pestana").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".pestana").forEach((x) => x.classList.remove("activa"));
    document.querySelectorAll(".panel").forEach((x) => x.classList.remove("activo"));
    b.classList.add("activa");
    $(b.dataset.panel).classList.add("activo");
  })
);

// ---------------------------------------------------------------- ropa
let PRENDAS = {};
function guardar(clave, valor) {
  try { localStorage.setItem("moldes:" + clave, JSON.stringify(valor)); } catch (_) {}
}
function leer(clave) {
  try { return JSON.parse(localStorage.getItem("moldes:" + clave)); } catch (_) { return null; }
}

function armarFormularioRopa() {
  PRENDAS = JSON.parse(api.prendas());
  const sel = $("prenda");
  sel.innerHTML = "";
  for (const [id, p] of Object.entries(PRENDAS)) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = p.nombre;
    sel.appendChild(o);
  }
  sel.onchange = camposPrenda;
  camposPrenda();
}

function camposPrenda() {
  const id = $("prenda").value;
  const p = PRENDAS[id];
  const guardadas = leer("medidas:" + id) || {};
  const cont = $("medidas");
  cont.innerHTML = "";
  for (const prm of p.params) {
    const l = document.createElement("label");
    l.textContent = prm.etiqueta + " (cm)";
    const i = document.createElement("input");
    i.type = "number";
    i.step = "0.5";
    i.id = "m-" + prm.id;
    i.value = guardadas[prm.id] ?? prm.valor;
    l.appendChild(i);
    cont.appendChild(l);
  }
  $("ropa-margen").value = p.margen;
}

$("btn-ropa").addEventListener("click", () => {
  const id = $("prenda").value;
  const medidas = {};
  for (const prm of PRENDAS[id].params) medidas[prm.id] = parseFloat($("m-" + prm.id).value);
  guardar("medidas:" + id, medidas);
  ejecutar(() =>
    api.generar_ropa(JSON.stringify({
      prenda: id, medidas,
      margen: parseFloat($("ropa-margen").value),
      hoja: $("ropa-hoja").value,
    })), id);
});

// ---------------------------------------------------------------- peluche
$("obj").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  textoObj = await f.text();
  nombreObj = f.name.replace(/\.obj$/i, "");
  $("obj-nombre").textContent = `Modelo: ${f.name} (${(f.size / 1024).toFixed(0)} KB)`;
  $("btn-peluche").disabled = !api;
});

$("btn-ejemplo").addEventListener("click", async () => {
  const r = await fetch(`ejemplos/rana.obj?v=${VERSION}`);
  textoObj = await r.text();
  nombreObj = "rana";
  $("obj-nombre").textContent = "Modelo: rana de ejemplo (18 piezas)";
  $("eje").value = "y";
  $("btn-peluche").disabled = !api;
});

$("btn-peluche").addEventListener("click", () => {
  if (!textoObj) return;
  ejecutar(() =>
    api.generar_peluche(textoObj, JSON.stringify({
      altura: parseFloat($("altura").value),
      eje: $("eje").value,
      modo: $("modo").value,
      margen: parseFloat($("pel-margen").value),
      hoja: $("pel-hoja").value,
      titulo: "Peluche: " + nombreObj,
    })), nombreObj);
});

// ---------------------------------------------------------------- común
async function ejecutar(fn, nombre) {
  const botones = [$("btn-ropa"), $("btn-peluche")];
  botones.forEach((b) => (b.disabled = true));
  estado("Generando…");
  await new Promise((r) => setTimeout(r, 30)); // deja que se pinte el mensaje
  try {
    const t0 = performance.now();
    const res = JSON.parse(fn());
    mostrar(res, nombre);
    estado(`Listo ✔ ${res.piezas} piezas en ${((performance.now() - t0) / 1000).toFixed(1)} s`, "ok");
  } catch (err) {
    console.error(err);
    const msg = String(err.message || err).split("\n").filter(Boolean);
    estado("Error: " + msg[msg.length - 1], "error");
  } finally {
    $("btn-ropa").disabled = !api;
    $("btn-peluche").disabled = !(api && textoObj);
  }
}

function mostrar(res, nombre) {
  $("resultado").classList.remove("oculto");
  const ul = $("informe");
  ul.innerHTML = "";
  for (const linea of res.informe) {
    const li = document.createElement("li");
    li.textContent = linea;
    if (/aviso|deforma|cerrada|tubo|superponen|muy chica|revis/i.test(linea)) li.className = "aviso";
    ul.appendChild(li);
  }
  const li = document.createElement("li");
  li.textContent = `Tamaño del molde completo: ${res.ancho_cm} × ${res.alto_cm} cm`;
  ul.appendChild(li);

  $("vista2d").innerHTML = res.svg;
  const svg = $("vista2d").querySelector("svg");
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  aplicarZoom();

  urlsDescarga.forEach((u) => URL.revokeObjectURL(u));
  urlsDescarga = [];
  const bin = Uint8Array.from(atob(res.pdf), (c) => c.charCodeAt(0));
  const enlace = (id, datos, tipo, archivo) => {
    const u = URL.createObjectURL(new Blob([datos], { type: tipo }));
    urlsDescarga.push(u);
    $(id).href = u;
    $(id).download = archivo;
  };
  enlace("dl-pdf", bin, "application/pdf", `molde_${nombre}.pdf`);
  enlace("dl-svg", res.svg, "image/svg+xml", `molde_${nombre}.svg`);
  enlace("dl-svg2", res.svg_impresion, "image/svg+xml", `molde_${nombre}_proyector.svg`);

  if (res.vista3d && res.vista3d.posiciones.length) {
    $("vista3d").classList.remove("oculto");
    vista3d(res.vista3d);
  } else {
    $("vista3d").classList.add("oculto");
  }
  $("resultado").scrollIntoView({ behavior: "smooth" });
}

function aplicarZoom() {
  $("vista2d").style.setProperty("--zoom", $("zoom").value);
}
$("zoom").addEventListener("input", aplicarZoom);

// ---------------------------------------------------------------- vista 3D
let render3d = null;
function vista3d(datos) {
  const cont = $("vista3d");
  if (render3d) {
    render3d.dispose();
    cont.innerHTML = "";
  }
  const w = cont.clientWidth || 600, h = cont.clientHeight || 340;
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(w, h);
  cont.appendChild(renderer.domElement);
  const escena = new THREE.Scene();
  escena.background = new THREE.Color(0xeef1ec);

  const pos = new Float32Array(datos.posiciones);
  const col = new Float32Array(pos.length);
  const c = new THREE.Color();
  for (let t = 0; t < datos.colores.length; t++) {
    c.set(datos.colores[t]);
    for (let k = 0; k < 3; k++) col.set([c.r, c.g, c.b], (t * 3 + k) * 3);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, side: THREE.DoubleSide, flatShading: true });
  // poner el modelo "parado" según el eje vertical elegido
  if (datos.eje === "z") geo.rotateX(-Math.PI / 2);
  if (datos.eje === "x") geo.rotateZ(Math.PI / 2);
  geo.computeBoundingSphere();
  const malla = new THREE.Mesh(geo, mat);
  const centro = geo.boundingSphere.center;
  malla.position.sub(centro);
  escena.add(malla);
  const bordes = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 25),
    new THREE.LineBasicMaterial({ color: 0x333333 }));
  bordes.position.copy(malla.position);
  escena.add(bordes);

  escena.add(new THREE.HemisphereLight(0xffffff, 0x888877, 1.6));
  const luz = new THREE.DirectionalLight(0xffffff, 1.2);
  luz.position.set(1, 2, 3);
  escena.add(luz);

  const r = geo.boundingSphere.radius;
  const cam = new THREE.PerspectiveCamera(40, w / h, r / 100, r * 100);
  cam.position.set(0, r * 0.3, r * 2.6);
  const ctrl = new OrbitControls(cam, renderer.domElement);
  ctrl.enableDamping = true;

  let vivo = true;
  (function animar() {
    if (!vivo) return;
    ctrl.update();
    renderer.render(escena, cam);
    requestAnimationFrame(animar);
  })();
  render3d = {
    dispose() { vivo = false; renderer.dispose(); geo.dispose(); },
  };
}

iniciar();
