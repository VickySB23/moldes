// Taller 3D de la pestaña Peluche: modelar con formas, armar un maniquí con
// medidas, cargar un .obj, dibujar costuras sobre el modelo y elegir las piezas.
// La geometría pesada (mallas, aplanado, moldes) la hace Python (Pyodide).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const CLAVE = "moldes:taller";
const COLORES = ["#cfe8b0", "#f6c9d6", "#c4def4", "#f8e7a6", "#ddd0f2", "#f9d3b4",
  "#bfe7dc", "#e8d5b5", "#d9e3a5", "#f2c0c0", "#c9cdf2", "#e2e2e2"];
const ESTADOS = {
  ok: ["✔", "se aplana bien"], cerrada: ["⛔", "cerrada: le falta una costura"],
  tubo: ["⚠️", "tubo: agregá una costura a lo largo"], deforma: ["⚠️", "se deforma: sumá una costura o pinza"],
  error: ["⛔", "no se pudo aplanar"],
};

let api = null, ESQ = null, generar = null, aviso = null;

// ------------------------------------------------------------------ estado
const est = {
  fuente: "formas",
  formas: null,                 // documento de formas
  maniqui: null,                // {medidas, tipo, forma, holgura, resolucion, talle}
  archivo: null,                // {nombre, texto, eje}
  costuras: { formas: [], maniqui: [], archivo: [] },
  descartes: { formas: [], maniqui: [], archivo: [] },
  tocadas: { archivo: false },  // si se editaron las costuras del archivo
  paso: "modelo",
  herramienta: "trazar",
  simetria: true,
  verEstado: false,
  sel: 0,                       // forma seleccionada
};
let modelo = null;      // {base, pos, caras, grupoCara, grupos, eje, alto, fuente, nombre, real}
let topo = null;        // vecinos, aristas→caras, longitudes
let res = null;         // costuras resueltas y piezas
let analisis = {};      // nombre de pieza → resultado de Python
let siguienteId = 1;

function guardar() {
  const copia = { ...est, archivo: est.archivo && est.archivo.texto.length < 3e6 ? est.archivo : null };
  try { localStorage.setItem(CLAVE, JSON.stringify(copia)); } catch (_) {}
}
function leerGuardado() {
  try { return JSON.parse(localStorage.getItem(CLAVE)); } catch (_) { return null; }
}

// ------------------------------------------------------------------ escena
let renderer, escena, camara, orbit, tc, grupoModelo, malla, lineas, previa, marcador, grid, ayudantes;
const raycaster = new THREE.Raycaster();

function iniciarEscena() {
  const cont = $("tl-vista3d");
  renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  cont.appendChild(renderer.domElement);
  escena = new THREE.Scene();
  escena.background = new THREE.Color(0xf3f1ec);
  camara = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
  camara.position.set(0, 20, 90);
  orbit = new OrbitControls(camara, renderer.domElement);
  orbit.enableDamping = true;
  escena.add(new THREE.HemisphereLight(0xffffff, 0x8a8478, 1.7));
  const luz = new THREE.DirectionalLight(0xffffff, 1.4);
  luz.position.set(40, 80, 60);
  escena.add(luz);
  const luz2 = new THREE.DirectionalLight(0xffffff, 0.5);
  luz2.position.set(-50, 30, -60);
  escena.add(luz2);
  grupoModelo = new THREE.Group();
  escena.add(grupoModelo);
  ayudantes = new THREE.Group();
  escena.add(ayudantes);
  tc = new TransformControls(camara, renderer.domElement);
  tc.setSize(0.8);
  escena.add(tc.getHelper ? tc.getHelper() : tc);
  tc.addEventListener("dragging-changed", (e) => { orbit.enabled = !e.value; });
  tc.addEventListener("objectChange", desdeAyudante);
  tc.addEventListener("mouseUp", () => { programarMalla(0); });
  const r = () => {
    const w = cont.clientWidth, h = cont.clientHeight;
    if (!w || !h) return;   // pestaña oculta: se mide cuando se muestre
    renderer.setSize(w, h);
    camara.aspect = w / h;
    camara.updateProjectionMatrix();
  };
  new ResizeObserver(r).observe(cont);
  window.addEventListener("resize", () => requestAnimationFrame(r));
  renderer.setSize(600, 420);
  r();
  (function animar() {
    orbit.update();
    renderer.render(escena, camara);
    requestAnimationFrame(animar);
  })();
  conectarPuntero();
}

function encuadrar(dir = null) {
  if (!malla) return;
  const caja = new THREE.Box3().setFromObject(malla);
  const c = caja.getCenter(new THREE.Vector3());
  const r = caja.getSize(new THREE.Vector3()).length() / 2 || 10;
  const d = dir ? new THREE.Vector3(...dir).normalize() : camara.position.clone().sub(orbit.target).normalize();
  orbit.target.copy(c);
  camara.position.copy(c).add(d.multiplyScalar(r * 2.8));
  camara.near = r / 50; camara.far = r * 60;
  camara.updateProjectionMatrix();
  if (grid) grid.position.y = caja.min.y - 0.01;
}

// ------------------------------------------------------------------ modelo
function ponerModelo(datos, fuente, nombre, eje = "y", real = true) {
  const base = new Float32Array(datos.posiciones);
  const carasBase = new Uint32Array(datos.caras);
  const grupoBase = Int32Array.from(datos.grupo_cara || new Array(carasBase.length / 3).fill(0));
  modelo = {
    base, carasBase, grupoBase, pos: base.slice(), caras: carasBase.slice(), grupoCara: grupoBase.slice(),
    grupos: datos.grupos || ["Pieza"], eje, alto: datos.alto || 0, fuente, nombre, real,
  };
  topo = topologia(modelo.pos, modelo.caras);
  grupoModelo.rotation.set(0, 0, 0);
  if (eje === "z") grupoModelo.rotation.x = -Math.PI / 2;
  if (eje === "x") grupoModelo.rotation.z = Math.PI / 2;
  grupoModelo.updateMatrixWorld(true);
  if (!grid) {
    grid = new THREE.GridHelper(400, 80, 0xd8d2c6, 0xe7e2d8);
    escena.add(grid);
  }
  const nuevo = !malla;
  resolver();
  if (nuevo) encuadrar([0, 0.15, 1]);
  else { const caja = new THREE.Box3().setFromObject(malla); grid.position.y = caja.min.y - 0.01; }
  $("tl-info").textContent = `${nombre} · ${(carasBase.length / 3).toLocaleString("es-AR")} triángulos` +
    (real && modelo.alto ? ` · ${modelo.alto.toLocaleString("es-AR")} cm de alto` : "");
  actualizarBotones();
}

// claves de arista estables aunque se agreguen vértices al partir triángulos
const K = 1048576;
const claveArista = (a, b) => (a < b ? a * K + b : b * K + a);
const deA = (k) => Math.floor(k / K);
const deB = (k) => k % K;

function topologia(P, F) {
  const nV = P.length / 3, nF = F.length / 3;
  const aristas = new Map();   // clave → [cara, cara]
  const vecinos = Array.from({ length: nV }, () => []);
  const carasDe = Array.from({ length: nV }, () => []);
  let suma = 0, n = 0;
  for (let f = 0; f < nF; f++) {
    for (let k = 0; k < 3; k++) {
      const a = F[f * 3 + k], b = F[f * 3 + (k + 1) % 3];
      carasDe[a].push(f);
      const c = claveArista(a, b);
      const l = aristas.get(c);
      if (l) l.push(f);
      else {
        aristas.set(c, [f]);
        const L = Math.hypot(P[a * 3] - P[b * 3], P[a * 3 + 1] - P[b * 3 + 1], P[a * 3 + 2] - P[b * 3 + 2]);
        vecinos[a].push(b, L); vecinos[b].push(a, L);
        suma += L; n++;
      }
    }
  }
  return { nV, nF, aristas, vecinos, carasDe, largoMedio: suma / Math.max(n, 1) };
}

function verticeCercano(p, pos = modelo.pos) {
  let mejor = -1, md = Infinity;
  const n = pos.length / 3;
  for (let i = 0; i < n; i++) {
    const dx = pos[i * 3] - p[0], dy = pos[i * 3 + 1] - p[1], dz = pos[i * 3 + 2] - p[2];
    const d = dx * dx + dy * dy + dz * dz;
    if (d < md) { md = d; mejor = i; }
  }
  return mejor;
}

function caraCercana(p, pos = modelo.pos) {
  const F = modelo.caras;
  let mejor = 0, md = Infinity;
  const nF = F.length / 3;
  for (let f = 0; f < nF; f++) {
    const a = F[f * 3] * 3, b = F[f * 3 + 1] * 3, c = F[f * 3 + 2] * 3;
    const dx = (pos[a] + pos[b] + pos[c]) / 3 - p[0], dy = (pos[a + 1] + pos[b + 1] + pos[c + 1]) / 3 - p[1], dz = (pos[a + 2] + pos[b + 2] + pos[c + 2]) / 3 - p[2];
    const d = dx * dx + dy * dy + dz * dz;
    if (d < md) { md = d; mejor = f; }
  }
  return mejor;
}
function centroCara(f, pos = modelo.pos) {
  const F = modelo.caras, a = F[f * 3] * 3, b = F[f * 3 + 1] * 3, c = F[f * 3 + 2] * 3;
  return [0, 1, 2].map((k) => (pos[a + k] + pos[b + k] + pos[c + k]) / 3);
}

function dijkstra(a, b) {
  if (a === b) return [a];
  const n = topo.nV, dist = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1);
  const heap = [[0, a]];
  dist[a] = 0;
  const push = (it) => { heap.push(it); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
  while (heap.length) {
    const [d, u] = pop();
    if (u === b) break;
    if (d > dist[u]) continue;
    const vs = topo.vecinos[u];
    for (let k = 0; k < vs.length; k += 2) {
      const v = vs[k], nd = d + vs[k + 1];
      if (nd < dist[v]) { dist[v] = nd; prev[v] = u; push([nd, v]); }
    }
  }
  if (prev[b] < 0) return null;
  const camino = [b];
  for (let v = b; v !== a; v = prev[v]) camino.push(prev[v]);
  return camino.reverse();
}

// unión-búsqueda de caras separadas por las costuras
function componentes(costura) {
  const nF = topo.nF, p = new Int32Array(nF);
  for (let i = 0; i < nF; i++) p[i] = i;
  const raiz = (a) => { while (p[a] !== a) { p[a] = p[p[a]]; a = p[a]; } return a; };
  for (const [c, fs] of topo.aristas) {
    if (fs.length === 2 && !costura.has(c)) { const a = raiz(fs[0]), b = raiz(fs[1]); if (a !== b) p[a] = b; }
  }
  const pieza = new Int32Array(nF);
  const ids = new Map();
  for (let f = 0; f < nF; f++) { const r = raiz(f); if (!ids.has(r)) ids.set(r, ids.size); pieza[f] = ids.get(r); }
  return { pieza, n: ids.size };
}

// ------------------------------------------------------------------ costuras
function resolver() {
  if (!modelo) return;
  // malla de trabajo: se parte en cada corte recto (los vértices nuevos van al final)
  modelo.pos = Array.from(modelo.base);
  modelo.caras = Array.from(modelo.carasBase);
  modelo.grupoCara = Array.from(modelo.grupoBase);
  topo = topologia(modelo.pos, modelo.caras);
  const costura = new Set();
  const dueno = new Map();
  const enCostura = new Set();
  const lista = est.costuras[est.fuente];
  const avisos = [];
  const orden = [...lista.filter((c) => c.tipo === "aristas"), ...lista.filter((c) => c.tipo !== "aristas")];
  for (const c of orden) {
    let aristas = [];
    try {
      if (c.tipo === "trazo") aristas = resolverTrazo(c, enCostura);
      else if (c.tipo === "plano") aristas = resolverPlano(c, costura, dueno, enCostura);
      else if (c.tipo === "aristas") aristas = c.aristas.filter(([a, b]) => topo.aristas.has(claveArista(a, b)));
    } catch (e) { console.warn(e); }
    if (!aristas.length) avisos.push(c);
    for (const [a, b] of aristas) {
      const k = claveArista(a, b);
      costura.add(k);
      if (!dueno.has(k)) dueno.set(k, c.id);
      enCostura.add(a); enCostura.add(b);
    }
  }
  modelo.pos = Float32Array.from(modelo.pos);
  modelo.caras = Uint32Array.from(modelo.caras);
  modelo.grupoCara = Int32Array.from(modelo.grupoCara);
  const pos = modelo.pos;
  let comp = componentes(costura);
  // piezas diminutas (astillas donde se cruzan cortes): se unen a la vecina con la que más comparten
  {
    const tam = new Int32Array(comp.n);
    for (let f = 0; f < topo.nF; f++) tam[comp.pieza[f]]++;
    const minimo = Math.max(10, topo.nF * 0.002);
    let cambio = false;
    for (let p = 0; p < comp.n; p++) {
      if (tam[p] >= minimo) continue;
      const vecinas = new Map();
      for (const k of costura) {
        const fs = topo.aristas.get(k);
        if (!fs || fs.length !== 2) continue;
        const [a, b] = fs.map((f) => comp.pieza[f]);
        if (a === p && b !== p) vecinas.set(b, (vecinas.get(b) || []).concat(k));
        else if (b === p && a !== p) vecinas.set(a, (vecinas.get(a) || []).concat(k));
      }
      let mejor = null;
      for (const [q, ks] of vecinas) if (!mejor || ks.length > mejor.length) mejor = ks;
      if (mejor) { for (const k of mejor) costura.delete(k); cambio = true; }
    }
    if (cambio) comp = componentes(costura);
  }
  // piezas: nombre por grupo mayoritario + lado
  const piezas = Array.from({ length: comp.n }, (_, i) => ({ i, caras: [], votos: new Map(), cx: 0, cy: 0, cz: 0 }));
  const F = modelo.caras;
  for (let f = 0; f < topo.nF; f++) {
    const pz = piezas[comp.pieza[f]];
    pz.caras.push(f);
    const g = modelo.grupoCara[f];
    pz.votos.set(g, (pz.votos.get(g) || 0) + 1);
    for (let k = 0; k < 3; k++) { const v = F[f * 3 + k]; pz.cx += pos[v * 3]; pz.cy += pos[v * 3 + 1]; pz.cz += pos[v * 3 + 2]; }
  }
  let xmin = Infinity, xmax = -Infinity;
  for (let i = 0; i < topo.nV; i++) { xmin = Math.min(xmin, pos[i * 3]); xmax = Math.max(xmax, pos[i * 3]); }
  const ancho = xmax - xmin || 1;
  const usados = new Map();
  piezas.sort((a, b) => b.caras.length - a.caras.length);
  for (const pz of piezas) {
    const n = pz.caras.length * 3;
    pz.cx /= n; pz.cy /= n; pz.cz /= n;
    let g = 0, mv = -1;
    for (const [k, v] of pz.votos) if (v > mv) { mv = v; g = k; }
    let base = modelo.grupos[g] || "Pieza";
    if (modelo.fuente === "maniqui" && /Torso|Busto|Hombro/.test(base)) base = pz.cz >= 0 ? "Delantero" : "Espalda";
    if (modelo.fuente !== "archivo" && Math.abs(pz.cx) > Math.min(ancho * 0.06, 2.5)) base += pz.cx < 0 ? " der" : " izq";
    const k = usados.get(base) || 0;
    usados.set(base, k + 1);
    pz.base = base;
    pz.nombre = k ? `${base} ${k + 1}` : base;
  }
  for (const [b, k] of usados) if (k > 1) for (const pz of piezas) if (pz.base === b && pz.nombre === b) pz.nombre = `${b} 1`;
  piezas.forEach((pz, j) => { pz.color = COLORES[j % COLORES.length]; pz.idx = j; });
  const piezaDeCara = new Int32Array(topo.nF);
  piezas.forEach((pz, j) => { for (const f of pz.caras) piezaDeCara[f] = j; });
  // descartes: la pieza que contiene la cara más cercana a cada punto guardado
  for (const p of est.descartes[est.fuente]) piezas[piezaDeCara[caraCercana(p)]].descartada = true;
  res = { costura, dueno, piezas, piezaDeCara, avisos };
  dibujarModelo();
  pintarPiezas();
  programarAnalisis();
}

function resolverTrazo(c, enCostura) {
  const pos = modelo.pos;
  const vs = c.puntos.map((p) => verticeCercano(p, pos));
  const camino = [];
  const tramos = vs.length - 1 + (c.cerrada ? 1 : 0);
  for (let i = 0; i < tramos; i++) {
    const t = dijkstra(vs[i], vs[(i + 1) % vs.length]);
    if (!t) continue;
    camino.push(...(camino.length ? t.slice(1) : t));
  }
  if (camino.length < 2) return [];
  // suavizar la costura (saca el escalonado de la malla)
  const fijos = new Set([camino[0], camino[camino.length - 1]]);
  for (let it = 0; it < 4; it++) {
    for (let i = 1; i < camino.length - 1; i++) {
      const v = camino[i];
      if (fijos.has(v) || enCostura.has(v)) continue;
      const a = camino[i - 1], b = camino[i + 1];
      moverSeguro(v, [0, 1, 2].map((k) => pos[v * 3 + k] + 0.5 * ((pos[a * 3 + k] + pos[b * 3 + k]) / 2 - pos[v * 3 + k])), pos);
    }
  }
  const ar = [];
  for (let i = 0; i < camino.length - 1; i++) if (camino[i] !== camino[i + 1]) ar.push([camino[i], camino[i + 1]]);
  return ar;
}

// Corte recto: parte los triángulos justo sobre el plano y devuelve la costura nueva.
function resolverPlano(c, costura, dueno, enCostura) {
  const O = c.punto, n = c.normal;
  const pos = modelo.pos, F = modelo.caras;
  const dist = (v) => n[0] * (pos[v * 3] - O[0]) + n[1] * (pos[v * 3 + 1] - O[1]) + n[2] * (pos[v * 3 + 2] - O[2]);
  // región: las piezas (hasta ahora) que tocan las anclas
  const comp = componentes(costura);
  const piezasRegion = new Set(c.anclas.map((p) => comp.pieza[caraCercana(p)]));
  const enRegion = (f) => piezasRegion.has(comp.pieza[f]);
  const nF0 = F.length / 3;
  // 1) vértices casi sobre el plano: se llevan al plano (evita triángulos finitos)
  const tol = topo.largoMedio * 0.12;
  const s = [];
  for (let v = 0; v < pos.length / 3; v++) s.push(dist(v));
  const vistos = new Set();
  for (let f = 0; f < nF0; f++) {
    if (!enRegion(f)) continue;
    for (let k = 0; k < 3; k++) {
      const v = F[f * 3 + k];
      if (vistos.has(v)) continue;
      vistos.add(v);
      if (s[v] !== 0 && Math.abs(s[v]) < tol) {
        if (!enCostura.has(v)) {
          moverSeguro(v, [pos[v * 3] - s[v] * n[0], pos[v * 3 + 1] - s[v] * n[1], pos[v * 3 + 2] - s[v] * n[2]], pos);
          s[v] = dist(v);
        }
        // si no se pudo mover del todo, el corte pasa por este vértice (evita triángulos de área cero)
        if (Math.abs(s[v]) < tol) s[v] = 0;
      }
    }
  }
  // 2) puntos de corte en las aristas que cruzan el plano (en la región)
  const corte = new Map();   // clave de arista → vértice nuevo
  for (let f = 0; f < nF0; f++) {
    if (!enRegion(f)) continue;
    for (let k = 0; k < 3; k++) {
      const a = F[f * 3 + k], b = F[f * 3 + (k + 1) % 3];
      if ((s[a] > 0 && s[b] < 0) || (s[a] < 0 && s[b] > 0)) {
        const key = claveArista(a, b);
        if (corte.has(key)) continue;
        const t = s[a] / (s[a] - s[b]);
        const m = pos.length / 3;
        pos.push(pos[a * 3] + t * (pos[b * 3] - pos[a * 3]), pos[a * 3 + 1] + t * (pos[b * 3 + 1] - pos[a * 3 + 1]),
          pos[a * 3 + 2] + t * (pos[b * 3 + 2] - pos[a * 3 + 2]));
        s.push(0);
        corte.set(key, m);
      }
    }
  }
  // 3) tramos de costura dentro de cada triángulo cortado
  const tramos = [];
  for (let f = 0; f < nF0; f++) {
    if (!enRegion(f)) continue;
    const pts = [];
    for (let k = 0; k < 3; k++) {
      const a = F[f * 3 + k], b = F[f * 3 + (k + 1) % 3];
      if (s[a] === 0) pts.push(a);
      const m = corte.get(claveArista(a, b));
      if (m !== undefined) pts.push(m);
    }
    if (pts.length === 2 && pts[0] !== pts[1]) tramos.push(pts);
    else if (pts.length === 3 && s[F[f * 3]] === 0 && s[F[f * 3 + 1]] === 0 && s[F[f * 3 + 2]] === 0) {
      // triángulo apoyado entero sobre el plano: sus aristas siguen la línea de corte
      tramos.push([F[f * 3], F[f * 3 + 1]], [F[f * 3 + 1], F[f * 3 + 2]], [F[f * 3 + 2], F[f * 3]]);
    }
  }
  // 4) volver a triangular (también los vecinos fuera de la región que comparten una arista cortada)
  const nuevas = [], grupos = [];
  const G = modelo.grupoCara;
  const tri = (a, b, c2, g) => { nuevas.push(a, b, c2); grupos.push(g); };
  for (let f = 0; f < nF0; f++) {
    const a = F[f * 3], b = F[f * 3 + 1], c2 = F[f * 3 + 2], g = G[f];
    const mab = corte.get(claveArista(a, b)), mbc = corte.get(claveArista(b, c2)), mca = corte.get(claveArista(c2, a));
    const cuenta = (mab !== undefined) + (mbc !== undefined) + (mca !== undefined);
    if (cuenta === 0) tri(a, b, c2, g);
    else if (cuenta === 1) {
      if (mab !== undefined) { tri(a, mab, c2, g); tri(mab, b, c2, g); }
      else if (mbc !== undefined) { tri(b, mbc, a, g); tri(mbc, c2, a, g); }
      else { tri(c2, mca, b, g); tri(mca, a, b, g); }
    } else if (cuenta === 2) {
      // v0 = vértice entre las dos aristas cortadas; m en (v0,v1), q en (v2,v0)
      let v0, v1, v2, m, q;
      if (mab === undefined) { v0 = c2; v1 = a; v2 = b; m = mca; q = mbc; }
      else if (mbc === undefined) { v0 = a; v1 = b; v2 = c2; m = mab; q = mca; }
      else { v0 = b; v1 = c2; v2 = a; m = mbc; q = mab; }
      tri(v0, m, q, g); tri(m, v1, v2, g); tri(m, v2, q, g);
    } else {
      tri(a, mab, mca, g); tri(mab, b, mbc, g); tri(mca, mbc, c2, g); tri(mab, mbc, mca, g);
    }
  }
  // 5) las costuras anteriores que se partieron siguen siendo costura
  for (const [key, m] of corte) {
    if (!costura.has(key)) continue;
    const a = deA(key), b = deB(key), d = dueno.get(key);
    costura.delete(key); dueno.delete(key);
    for (const k2 of [claveArista(a, m), claveArista(m, b)]) { costura.add(k2); dueno.set(k2, d); }
    enCostura.add(m);
  }
  modelo.caras = nuevas;
  modelo.grupoCara = grupos;
  topo = topologia(pos, nuevas);
  // 6) quedarse con las líneas que tocan alguna ancla (la más cercana a cada una)
  const p = new Map();
  const raiz = (x) => { while (p.get(x) !== x) { p.set(x, p.get(p.get(x))); x = p.get(x); } return x; };
  for (const [a, b] of tramos) { if (!p.has(a)) p.set(a, a); if (!p.has(b)) p.set(b, b); const ra = raiz(a), rb = raiz(b); if (ra !== rb) p.set(ra, rb); }
  const buenas = new Set();
  const vs = [...p.keys()];
  for (const q of c.anclas) {
    let mejor = -1, md = Infinity;
    for (const v of vs) {
      const d = (pos[v * 3] - q[0]) ** 2 + (pos[v * 3 + 1] - q[1]) ** 2 + (pos[v * 3 + 2] - q[2]) ** 2;
      if (d < md) { md = d; mejor = v; }
    }
    if (mejor >= 0) buenas.add(raiz(mejor));
  }
  return tramos.filter(([a, b]) => buenas.has(raiz(a)) && topo.aristas.has(claveArista(a, b)));
}

// mueve un vértice sin dar vuelta ni aplastar los triángulos vecinos (si no puede, se mueve menos)
function normalCara(f, pos) {
  const F = modelo.caras, a = F[f * 3], b = F[f * 3 + 1], c = F[f * 3 + 2];
  const ux = pos[b * 3] - pos[a * 3], uy = pos[b * 3 + 1] - pos[a * 3 + 1], uz = pos[b * 3 + 2] - pos[a * 3 + 2];
  const vx = pos[c * 3] - pos[a * 3], vy = pos[c * 3 + 1] - pos[a * 3 + 1], vz = pos[c * 3 + 2] - pos[a * 3 + 2];
  return [uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx];
}
function moverSeguro(v, destino, pos) {
  const caras = topo.carasDe[v];
  const antes = caras.map((f) => normalCara(f, pos));
  const orig = [pos[v * 3], pos[v * 3 + 1], pos[v * 3 + 2]];
  for (const t of [1, 0.6, 0.3]) {
    for (let k = 0; k < 3; k++) pos[v * 3 + k] = orig[k] + (destino[k] - orig[k]) * t;
    let ok = true;
    for (let i = 0; i < caras.length && ok; i++) {
      const n0 = antes[i], n1 = normalCara(caras[i], pos);
      const a0 = Math.hypot(...n0), a1 = Math.hypot(...n1);
      if (a1 < 0.3 * a0 || n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2] < 0.6 * a0 * a1) ok = false;
    }
    if (ok) return;
  }
  for (let k = 0; k < 3; k++) pos[v * 3 + k] = orig[k];
}

function nuevaCostura(c) {
  c.id = siguienteId++;
  const lista = est.costuras[est.fuente];
  lista.push(c);
  if (est.simetria) {
    const esp = espejar(c);
    if (esp) { esp.id = siguienteId++; esp.par = c.id; c.par = esp.id; lista.push(esp); }
  }
  if (est.fuente === "archivo") est.tocadas.archivo = true;
  guardar();
  resolver();
}

const M = (p) => [-p[0], p[1], p[2]];
function espejar(c) {
  const tol = topo.largoMedio * 1.5;
  if (c.tipo === "trazo") {
    if (c.puntos.every((p) => Math.abs(p[0]) < tol)) return null;
    return { tipo: "trazo", puntos: c.puntos.map(M), cerrada: c.cerrada };
  }
  if (c.tipo === "plano") {
    const n2 = [-c.normal[0], c.normal[1], c.normal[2]];
    const mismo = Math.abs(Math.abs(n2[0] * c.normal[0] + n2[1] * c.normal[1] + n2[2] * c.normal[2]) - 1) < 1e-3 &&
      Math.abs(c.normal[0] * (-2 * c.punto[0])) < tol;
    if (mismo || c.anclas.every((p) => Math.abs(p[0]) < tol)) return null;
    return { tipo: "plano", punto: M(c.punto), normal: n2, anclas: c.anclas.map(M) };
  }
  return null;
}

function borrarCostura(id) {
  const lista = est.costuras[est.fuente];
  const c = lista.find((x) => x.id === id);
  if (!c) return;
  est.costuras[est.fuente] = lista.filter((x) => x.id !== id && x.id !== c.par);
  if (est.fuente === "archivo") est.tocadas.archivo = true;
  guardar();
  resolver();
}

// ------------------------------------------------------------------ dibujo
function dibujarModelo() {
  const m = modelo, F = m.caras, P = m.pos, nF = topo.nF;
  // normales suaves por vértice
  const N = new Float32Array(P.length);
  for (let f = 0; f < nF; f++) {
    const a = F[f * 3], b = F[f * 3 + 1], c = F[f * 3 + 2];
    const ux = P[b * 3] - P[a * 3], uy = P[b * 3 + 1] - P[a * 3 + 1], uz = P[b * 3 + 2] - P[a * 3 + 2];
    const vx = P[c * 3] - P[a * 3], vy = P[c * 3 + 1] - P[a * 3 + 1], vz = P[c * 3 + 2] - P[a * 3 + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const v of [a, b, c]) { N[v * 3] += nx; N[v * 3 + 1] += ny; N[v * 3 + 2] += nz; }
  }
  const pos = new Float32Array(nF * 9), nor = new Float32Array(nF * 9), col = new Float32Array(nF * 9);
  const color = new THREE.Color();
  const colorPieza = res.piezas.map((pz) => {
    if (pz.descartada) return new THREE.Color("#b9b4ab");
    if (est.verEstado) {
      const a = analisis[pz.nombre];
      const e = a ? a.estado : null;
      return new THREE.Color(e === "ok" ? "#7cc46f" : e === "cerrada" || e === "error" ? "#e2584f" : e ? "#f0b43c" : "#d7d3cb");
    }
    return new THREE.Color(pz.color);
  });
  for (let f = 0; f < nF; f++) {
    color.copy(colorPieza[res.piezaDeCara[f]]);
    if (resaltada === res.piezaDeCara[f]) color.lerp(new THREE.Color("#ffffff"), 0.45);
    for (let k = 0; k < 3; k++) {
      const v = F[f * 3 + k], o = f * 9 + k * 3;
      pos[o] = P[v * 3]; pos[o + 1] = P[v * 3 + 1]; pos[o + 2] = P[v * 3 + 2];
      const l = Math.hypot(N[v * 3], N[v * 3 + 1], N[v * 3 + 2]) || 1;
      nor[o] = N[v * 3] / l; nor[o + 1] = N[v * 3 + 1] / l; nor[o + 2] = N[v * 3 + 2] / l;
      col[o] = color.r; col[o + 1] = color.g; col[o + 2] = color.b;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  geo.computeBoundingSphere();
  if (!malla) {
    malla = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
      vertexColors: true, roughness: 0.92, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1,
    }));
    grupoModelo.add(malla);
  } else { malla.geometry.dispose(); malla.geometry = geo; }
  // costuras
  const seg = new Float32Array(res.costura.size * 6);
  let i = 0;
  for (const k of res.costura) {
    const a = deA(k), b = deB(k);
    seg.set([P[a * 3], P[a * 3 + 1], P[a * 3 + 2], P[b * 3], P[b * 3 + 1], P[b * 3 + 2]], i);
    i += 6;
  }
  const g2 = new THREE.BufferGeometry();
  g2.setAttribute("position", new THREE.BufferAttribute(seg, 3));
  if (!lineas) {
    lineas = new THREE.LineSegments(g2, new THREE.LineBasicMaterial({ color: 0xc1121f }));
    grupoModelo.add(lineas);
  } else { lineas.geometry.dispose(); lineas.geometry = g2; }
}

let resaltada = -1;
function pintarPiezas() {
  const ul = $("tl-piezas");
  if (!res) { ul.innerHTML = ""; return; }
  const activas = res.piezas.filter((p) => !p.descartada).length;
  $("tl-resumen").textContent = `${activas} ${activas === 1 ? "pieza" : "piezas"} en el molde` +
    (res.piezas.length > activas ? ` · ${res.piezas.length - activas} fuera` : "") +
    ` · ${est.costuras[est.fuente].length} costuras`;
  ul.innerHTML = res.piezas.map((pz) => {
    const a = analisis[pz.nombre];
    const e = pz.descartada ? null : a ? ESTADOS[a.estado] : null;
    const def = a && a.media != null ? ` · ${String(a.media).replace(".", ",")} %` : "";
    return `<li data-pieza="${pz.idx}" class="${pz.descartada ? "fuera" : ""}">` +
      `<span class="tl-color" style="background:${pz.descartada ? "#ccc" : pz.color}"></span>` +
      `<span class="tl-nombre">${esc(pz.nombre)}</span>` +
      `<span class="tl-estado">${pz.descartada ? "no va en el molde" : e ? `${e[0]} ${e[1]}${def}` : "…"}</span>` +
      `<label title="Incluir en el molde"><input type="checkbox" data-incluir="${pz.idx}" ${pz.descartada ? "" : "checked"}></label></li>`;
  }).join("");
}

// ------------------------------------------------------------------ OBJ de las piezas (para Python)
function objPiezas() {
  const F = modelo.caras, P = modelo.pos, nF = topo.nF;
  // esquinas: misma clase si comparten vértice a través de una arista que no es costura
  const p = new Int32Array(nF * 3);
  for (let i = 0; i < p.length; i++) p[i] = i;
  const raiz = (a) => { while (p[a] !== a) { p[a] = p[p[a]]; a = p[a]; } return a; };
  const esquina = (f, v) => f * 3 + (F[f * 3] === v ? 0 : F[f * 3 + 1] === v ? 1 : 2);
  for (const [k, fs] of topo.aristas) {
    if (fs.length !== 2 || res.costura.has(k)) continue;
    const a = deA(k), b = deB(k);
    for (const v of [a, b]) { const x = raiz(esquina(fs[0], v)), y = raiz(esquina(fs[1], v)); if (x !== y) p[x] = y; }
  }
  const vt = new Map();
  const lineas = ["# moldes:editor", `# ${modelo.nombre}`];
  for (let i = 0; i < topo.nV; i++) lineas.push(`v ${P[i * 3].toFixed(4)} ${P[i * 3 + 1].toFixed(4)} ${P[i * 3 + 2].toFixed(4)}`);
  const cuerpo = [];
  for (const pz of res.piezas) {
    if (pz.descartada) continue;
    cuerpo.push(`g ${pz.nombre}`);
    for (const f of pz.caras) {
      const t = [0, 1, 2].map((k) => {
        const r = raiz(f * 3 + k);
        if (!vt.has(r)) vt.set(r, vt.size + 1);
        return `${F[f * 3 + k] + 1}/${vt.get(r)}`;
      });
      cuerpo.push(`f ${t.join(" ")}`);
    }
  }
  for (let i = 0; i < vt.size; i++) lineas.push("vt 0 0");
  return lineas.concat(cuerpo).join("\n") + "\n";
}

let tAnalisis = null;
function programarAnalisis(ms = 700) {
  clearTimeout(tAnalisis);
  if (!$("tl-auto").checked || est.paso === "modelo") return;
  tAnalisis = setTimeout(analizar, ms);
}
async function analizar() {
  if (!res || !api) return;
  if (!res.piezas.some((p) => !p.descartada)) { analisis = {}; pintarPiezas(); return; }
  $("tl-revisar").disabled = true;
  $("tl-resumen").textContent = "Revisando piezas…";
  await new Promise((r) => setTimeout(r, 30));
  try {
    const lista = JSON.parse(api.analizar_piezas(objPiezas()));
    analisis = {};
    for (const a of lista) analisis[a.nombre] = a;
  } catch (e) { console.error(e); aviso("No pude revisar las piezas: " + String(e.message || e).split("\n").pop(), "error"); }
  $("tl-revisar").disabled = false;
  pintarPiezas();
  if (est.verEstado) dibujarModelo();
}

// ------------------------------------------------------------------ puntero: trazar, cuchillo, borrar, quitar
let trazo = null;     // {puntos: [[x,y,z]], vertices: []}
let cuchillo = null;  // {x, y} primer punto en pantalla
function aLocal(v) { return grupoModelo.worldToLocal(v.clone()); }
function golpe(ev) {
  if (!malla) return null;
  const r = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  raycaster.setFromCamera(ndc, camara);
  const h = raycaster.intersectObject(malla, false)[0];
  if (!h) return null;
  const p = aLocal(h.point);
  const f = h.faceIndex;
  const F = modelo.caras, P = modelo.pos;
  let mejor = F[f * 3], md = Infinity;
  for (let k = 0; k < 3; k++) {
    const v = F[f * 3 + k];
    const d = (P[v * 3] - p.x) ** 2 + (P[v * 3 + 1] - p.y) ** 2 + (P[v * 3 + 2] - p.z) ** 2;
    if (d < md) { md = d; mejor = v; }
  }
  return { p: [p.x, p.y, p.z], v: mejor, f };
}

function marcar(v) {
  if (!marcador) {
    marcador = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), new THREE.MeshBasicMaterial({ color: 0xff8800 }));
    grupoModelo.add(marcador);
  }
  if (v == null) { marcador.visible = false; return; }
  const P = modelo.pos;
  marcador.visible = true;
  marcador.position.set(P[v * 3], P[v * 3 + 1], P[v * 3 + 2]);
  marcador.scale.setScalar(topo.largoMedio * 0.45);
}

function dibujarPrevia() {
  if (previa) { grupoModelo.remove(previa); previa.geometry.dispose(); previa = null; }
  if (!trazo || !trazo.vertices.length) return;
  const P = modelo.pos, pts = [];
  for (let i = 0; i < trazo.vertices.length - 1; i++) {
    const t = dijkstra(trazo.vertices[i], trazo.vertices[i + 1]) || [];
    for (const v of t) pts.push(new THREE.Vector3(P[v * 3], P[v * 3 + 1], P[v * 3 + 2]));
  }
  if (pts.length < 2) for (const v of trazo.vertices) pts.push(new THREE.Vector3(P[v * 3], P[v * 3 + 1], P[v * 3 + 2]));
  previa = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xff8800, depthTest: false }));
  previa.renderOrder = 5;
  grupoModelo.add(previa);
}

function terminarTrazo(cerrar = false) {
  if (!trazo) return;
  if (trazo.puntos.length >= 2) nuevaCostura({ tipo: "trazo", puntos: trazo.puntos, cerrada: cerrar && trazo.puntos.length >= 3 });
  trazo = null;
  dibujarPrevia();
  ayudaHerramienta();
}

function cortarConLinea(a, b) {
  const r = renderer.domElement.getBoundingClientRect();
  const rayo = (x, y) => {
    raycaster.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), camara);
    return raycaster.ray.clone();
  };
  const r1 = rayo(a.x, a.y), r2 = rayo(b.x, b.y);
  const inv = new THREE.Matrix4().copy(grupoModelo.matrixWorld).invert();
  r1.applyMatrix4(inv); r2.applyMatrix4(inv);
  const n = new THREE.Vector3().crossVectors(r1.direction, r2.direction);
  if (n.length() < 1e-6) return;
  n.normalize();
  const anclas = [];
  for (let i = 0; i <= 60; i++) {
    const t = i / 60;
    raycaster.setFromCamera(new THREE.Vector2(((a.x + (b.x - a.x) * t - r.left) / r.width) * 2 - 1,
      -((a.y + (b.y - a.y) * t - r.top) / r.height) * 2 + 1), camara);
    const h = raycaster.intersectObject(malla, false)[0];
    if (h) { const p = aLocal(h.point); anclas.push([p.x, p.y, p.z]); }
  }
  if (!anclas.length) { aviso("La línea del cuchillo tiene que cruzar el modelo.", "error"); return; }
  // menos anclas alcanzan (una cada tanto)
  const pocas = anclas.filter((_, i) => i % 4 === 0);
  nuevaCostura({ tipo: "plano", punto: [r1.origin.x, r1.origin.y, r1.origin.z], normal: [n.x, n.y, n.z], anclas: pocas });
}

function conectarPuntero() {
  const el = renderer.domElement;
  let abajo = null;
  el.addEventListener("pointerdown", (e) => { abajo = { x: e.clientX, y: e.clientY, t: performance.now(), sobreGizmo: tc.axis !== null && tc.object }; });
  el.addEventListener("pointerup", (e) => {
    if (!abajo) return;
    const movio = Math.hypot(e.clientX - abajo.x, e.clientY - abajo.y) > 5;
    const sobre = abajo.sobreGizmo;
    abajo = null;
    if (movio || sobre || est.paso === "modelo") return;
    clic(e);
  });
  el.addEventListener("dblclick", (e) => { if (est.paso === "costuras" && est.herramienta === "trazar" && trazo) { e.preventDefault(); terminarTrazo(false); } });
  el.addEventListener("pointermove", (e) => {
    if (est.paso !== "costuras" || !malla) { marcar(null); return; }
    if (est.herramienta === "trazar") { const g = golpe(e); marcar(g ? g.v : null); }
    if (est.herramienta === "cuchillo" && cuchillo) {
      const r = el.getBoundingClientRect();
      let x = e.clientX, y = e.clientY;
      if (e.shiftKey) { if (Math.abs(x - cuchillo.x) > Math.abs(y - cuchillo.y)) y = cuchillo.y; else x = cuchillo.x; }
      const l = $("tl-linea");
      l.setAttribute("x1", cuchillo.x - r.left); l.setAttribute("y1", cuchillo.y - r.top);
      l.setAttribute("x2", x - r.left); l.setAttribute("y2", y - r.top);
      l.style.display = "";
    }
  });
  el.addEventListener("pointerleave", () => marcar(null));
  window.addEventListener("keydown", (e) => {
    if (!$("panel-peluche").classList.contains("activo") || /INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName || "")) return;
    if (est.paso === "costuras") {
      if (e.key === "Enter" && trazo) { e.preventDefault(); terminarTrazo(false); }
      if (e.key === "Escape") { trazo = null; cuchillo = null; $("tl-linea").style.display = "none"; dibujarPrevia(); ayudaHerramienta(); }
      if (e.key === "Backspace" && trazo) { e.preventDefault(); trazo.puntos.pop(); trazo.vertices.pop(); if (!trazo.puntos.length) trazo = null; dibujarPrevia(); }
      const t = { t: "trazar", c: "cuchillo", b: "borrar", q: "quitar" }[e.key.toLowerCase()];
      if (t && !e.ctrlKey && !e.metaKey) elegirHerramienta(t);
    } else if (est.paso === "modelo" && est.fuente === "formas") {
      const m = { g: "translate", w: "translate", r: "rotate", e: "rotate", s: "scale" }[e.key.toLowerCase()];
      if (m && !e.ctrlKey && !e.metaKey) modoGizmo(m);
      if (e.key === "Delete" && est.formas.formas.length) borrarForma(est.sel);
    }
  });
}

function clic(e) {
  const h = est.herramienta;
  if (h === "cuchillo") {
    let x = e.clientX, y = e.clientY;
    if (!cuchillo) { cuchillo = { x, y }; ayudaHerramienta(); return; }
    if (e.shiftKey) { if (Math.abs(x - cuchillo.x) > Math.abs(y - cuchillo.y)) y = cuchillo.y; else x = cuchillo.x; }
    const a = cuchillo;
    cuchillo = null;
    $("tl-linea").style.display = "none";
    if (Math.hypot(x - a.x, y - a.y) > 8) cortarConLinea(a, { x, y });
    ayudaHerramienta();
    return;
  }
  const g = golpe(e);
  if (!g) return;
  if (h === "trazar") {
    if (!trazo) trazo = { puntos: [], vertices: [] };
    // tocar el primer punto cierra la costura
    if (trazo.vertices.length >= 3) {
      const P = modelo.pos, v0 = trazo.vertices[0];
      const d = Math.hypot(P[v0 * 3] - g.p[0], P[v0 * 3 + 1] - g.p[1], P[v0 * 3 + 2] - g.p[2]);
      if (d < topo.largoMedio * 2.5) { terminarTrazo(true); return; }
    }
    const P = modelo.pos;
    trazo.vertices.push(g.v);
    trazo.puntos.push([P[g.v * 3], P[g.v * 3 + 1], P[g.v * 3 + 2]]);
    dibujarPrevia();
    ayudaHerramienta();
  } else if (h === "borrar") {
    let mejor = null, md = Infinity;
    const P = modelo.pos;
    for (const k of res.costura) {
      const a = deA(k), b = deB(k);
      const d = ((P[a * 3] + P[b * 3]) / 2 - g.p[0]) ** 2 + ((P[a * 3 + 1] + P[b * 3 + 1]) / 2 - g.p[1]) ** 2 + ((P[a * 3 + 2] + P[b * 3 + 2]) / 2 - g.p[2]) ** 2;
      if (d < md) { md = d; mejor = k; }
    }
    if (mejor !== null && md < (topo.largoMedio * 4) ** 2) borrarCostura(res.dueno.get(mejor));
  } else if (h === "quitar") {
    alternarDescarte(res.piezaDeCara[g.f], centroCara(g.f));
  }
}

function alternarDescarte(idx, punto = null) {
  const pz = res.piezas[idx];
  const lista = est.descartes[est.fuente];
  if (pz.descartada) {
    // sacar los puntos que caen en esta pieza
    est.descartes[est.fuente] = lista.filter((p) => res.piezaDeCara[caraCercana(p)] !== idx);
  } else {
    if (!punto) punto = centroCara(pz.caras[Math.floor(pz.caras.length / 2)]);
    lista.push(punto);
  }
  guardar();
  resolver();
}

function elegirHerramienta(t) {
  est.herramienta = t;
  trazo = null; cuchillo = null;
  $("tl-linea").style.display = "none";
  dibujarPrevia();
  document.querySelectorAll("[data-herramienta]").forEach((b) => b.classList.toggle("activa", b.dataset.herramienta === t));
  renderer.domElement.style.cursor = t === "trazar" || t === "cuchillo" ? "crosshair" : t === "borrar" ? "not-allowed" : "pointer";
  ayudaHerramienta();
}

function ayudaHerramienta() {
  const t = est.herramienta;
  const txt = {
    trazar: trazo ? `Punto ${trazo.puntos.length}. Seguí tocando; <b>Enter</b> o doble clic termina, tocar el primer punto la cierra, <b>Retroceso</b> borra el último.`
      : "Tocá puntos sobre el modelo: la costura sigue la superficie entre ellos.",
    cuchillo: cuchillo ? "Ahora tocá el otro extremo de la línea (con <b>Shift</b> queda recta)."
      : "Trazá una línea recta sobre la pantalla (dos clics): corta de lado a lado la pieza que cruza. Ideal para la costura del centro o para separar un brazo.",
    borrar: "Tocá una costura para borrarla.",
    quitar: "Tocá una pieza para sacarla del molde (o volver a ponerla): cabeza y brazos de un maniquí, por ejemplo.",
  }[t];
  $("tl-ayuda").innerHTML = txt;
}

// ------------------------------------------------------------------ formas: editor
let tMalla = null;
function programarMalla(ms = 300) {
  clearTimeout(tMalla);
  tMalla = setTimeout(mallarFormas, ms);
}
function mallarFormas() {
  if (est.fuente !== "formas" || !api) return;
  try {
    const d = JSON.parse(api.mallar_formas(JSON.stringify(est.formas)));
    ponerModelo(d, "formas", est.formas.nombre || "Formas", "y", true);
    $("tl-error").textContent = "";
  } catch (e) {
    $("tl-error").textContent = String(e.message || e).split("\n").filter(Boolean).pop();
  }
  dibujarAyudantes();
  guardar();
}

function geoAyudante(f) {
  const t = f.tipo;
  if (t === "caja") return new THREE.BoxGeometry(1, 1, 1);
  if (t === "cilindro") return new THREE.CylinderGeometry(0.5, 0.5, 1, 24);
  if (t === "cono") return new THREE.CylinderGeometry(0.5 * (f.afinado ?? 0.35), 0.5, 1, 24);
  if (t === "capsula") {
    const r = 0.5, ratio = Math.max(f.tam[1] / Math.max((f.tam[0] + f.tam[2]) / 2, 0.01), 1);
    const g = new THREE.CapsuleGeometry(r, Math.max(ratio - 1, 0.01), 6, 16);
    g.scale(1, 1 / ratio, 1);
    return g;
  }
  if (t === "toro") {
    const tubo = Math.min(f.tam[1] / 2, f.tam[0] / 2), R = Math.max(f.tam[0] / 2 - tubo, 0.1);
    const g = new THREE.TorusGeometry(R / f.tam[0], tubo / f.tam[0], 10, 32);
    g.rotateX(Math.PI / 2);
    g.scale(1, f.tam[0] / Math.max(f.tam[1], 0.01), 1);
    return g;
  }
  return new THREE.SphereGeometry(0.5, 24, 16);
}

let ayudanteSel = null;
function dibujarAyudantes() {
  tc.detach();
  ayudanteSel = null;
  for (const c of [...ayudantes.children]) { ayudantes.remove(c); c.geometry.dispose(); }
  if (est.fuente !== "formas" || est.paso !== "modelo") return;
  est.formas.formas.forEach((f, i) => {
    if (f.oculta) return;
    const sel = i === est.sel;
    const copias = [false];
    if (f.espejo && Math.abs(f.pos[0]) > 1e-6) copias.push(true);
    for (const esp of copias) {
      const m = new THREE.Mesh(geoAyudante(f), new THREE.MeshBasicMaterial({
        color: f.modo === "restar" ? 0xd62828 : sel ? 0xff8800 : 0x6c8cbf, wireframe: true, transparent: true, opacity: sel ? 0.55 : 0.18,
      }));
      m.position.set(esp ? -f.pos[0] : f.pos[0], f.pos[1], f.pos[2]);
      m.rotation.set(THREE.MathUtils.degToRad(f.rot[0]), THREE.MathUtils.degToRad(esp ? -f.rot[1] : f.rot[1]),
        THREE.MathUtils.degToRad(esp ? -f.rot[2] : f.rot[2]), "XYZ");
      m.scale.set(...f.tam);
      m.userData = { i, esp };
      ayudantes.add(m);
      if (sel && !esp) ayudanteSel = m;
    }
  });
  if (ayudanteSel) tc.attach(ayudanteSel);
}

function desdeAyudante() {
  if (!ayudanteSel) return;
  const f = est.formas.formas[ayudanteSel.userData.i];
  const r = (v) => Math.round(v * 10) / 10;
  f.pos = ayudanteSel.position.toArray().map(r);
  f.rot = [ayudanteSel.rotation.x, ayudanteSel.rotation.y, ayudanteSel.rotation.z].map((a) => r(THREE.MathUtils.radToDeg(a)));
  f.tam = ayudanteSel.scale.toArray().map((v) => Math.max(r(Math.abs(v)), 0.2));
  // el espejo se mueve junto
  for (const c of ayudantes.children) {
    if (c.userData.i === ayudanteSel.userData.i && c.userData.esp) {
      c.position.set(-f.pos[0], f.pos[1], f.pos[2]);
      c.rotation.set(ayudanteSel.rotation.x, -ayudanteSel.rotation.y, -ayudanteSel.rotation.z);
      c.scale.copy(ayudanteSel.scale);
    }
  }
  actualizarCamposForma(ayudanteSel.userData.i);
}

function modoGizmo(m) {
  tc.setMode(m);
  document.querySelectorAll("[data-gizmo]").forEach((b) => b.classList.toggle("activa", b.dataset.gizmo === m));
}

function nuevaForma(tipo) {
  const L = est.formas.formas;
  const ref = L[est.sel];
  const tam = { esfera: [8, 8, 8], capsula: [5, 12, 5], cilindro: [6, 10, 6], cono: [6, 10, 6], caja: [8, 8, 8], toro: [10, 3, 10] }[tipo];
  const pos = ref ? [Math.round(ref.pos[0] + ref.tam[0] / 2 + 2), ref.pos[1], ref.pos[2]] : [0, tam[1] / 2, 0];
  L.push({ nombre: ESQ.formas.tipos[tipo].split(" ")[0], tipo, modo: "unir", pos, tam, rot: [0, 0, 0], espejo: pos[0] !== 0 });
  est.sel = L.length - 1;
  pintarFormas();
  programarMalla(0);
}
function borrarForma(i) {
  est.formas.formas.splice(i, 1);
  est.sel = Math.max(0, Math.min(est.sel, est.formas.formas.length - 1));
  pintarFormas();
  programarMalla(0);
}

function pintarFormas() {
  const F = est.formas;
  $("tl-formas-nombre").value = F.nombre || "";
  $("tl-suavidad").value = F.suavidad ?? 2;
  $("tl-resolucion").value = F.resolucion || "media";
  const opt = (obj, v) => Object.entries(obj).map(([k, t]) => `<option value="${k}" ${k === v ? "selected" : ""}>${esc(t)}</option>`).join("");
  const num = (i, campo, k, et) => `<label><span>${et}</span><input type="number" step="0.5" data-f="${i}" data-campo="${campo}" data-k="${k}" value="${F.formas[i][campo][k]}"></label>`;
  $("tl-lista-formas").innerHTML = F.formas.map((f, i) => `
    <div class="tl-forma ${i === est.sel ? "sel" : ""}" data-sel="${i}">
      <div class="tl-fila">
        <input class="tl-fnombre" data-f="${i}" data-campo="nombre" value="${esc(f.nombre)}">
        <select data-f="${i}" data-campo="tipo">${opt(ESQ.formas.tipos, f.tipo)}</select>
        <button type="button" class="ed-mini" data-accion-forma="ocultar" data-f="${i}" title="Ocultar">${f.oculta ? "🙈" : "👁"}</button>
        <button type="button" class="ed-mini" data-accion-forma="duplicar" data-f="${i}" title="Duplicar">⧉</button>
        <button type="button" class="ed-mini ed-borrar" data-accion-forma="borrar" data-f="${i}" title="Borrar">✕</button>
      </div>
      ${i === est.sel ? `
      <div class="tl-fila">
        <select data-f="${i}" data-campo="modo">${opt(ESQ.formas.modos, f.modo)}</select>
        <label class="ed-check"><input type="checkbox" data-f="${i}" data-campo="espejo" ${f.espejo ? "checked" : ""}> espejo izq/der</label>
      </div>
      <div class="tl-xyz"><b>Posición</b>${num(i, "pos", 0, "x")}${num(i, "pos", 1, "y ↑")}${num(i, "pos", 2, "z →frente")}</div>
      <div class="tl-xyz"><b>Tamaño</b>${num(i, "tam", 0, "ancho")}${num(i, "tam", 1, "alto")}${num(i, "tam", 2, "prof.")}</div>
      <div class="tl-xyz"><b>Giro °</b>${num(i, "rot", 0, "x")}${num(i, "rot", 1, "y")}${num(i, "rot", 2, "z")}</div>
      <div class="tl-fila">
        ${f.tipo === "cono" ? `<label><span>punta (0–1)</span><input type="number" step="0.05" min="0" max="1" data-f="${i}" data-campo="afinado" value="${f.afinado ?? 0.35}"></label>` : ""}
        <label><span>suavidad propia (cm)</span><input type="number" step="0.5" min="0" data-f="${i}" data-campo="suavidad" value="${f.suavidad ?? ""}" placeholder="general"></label>
      </div>` : ""}
    </div>`).join("");
}
function actualizarCamposForma(i) {
  const f = est.formas.formas[i];
  document.querySelectorAll(`#tl-lista-formas input[data-f="${i}"][data-k]`).forEach((inp) => {
    inp.value = f[inp.dataset.campo][+inp.dataset.k];
  });
}

function conectarFormas() {
  const lista = $("tl-lista-formas");
  lista.addEventListener("input", (e) => {
    const t = e.target, i = +t.dataset.f;
    if (Number.isNaN(i)) return;
    const f = est.formas.formas[i], campo = t.dataset.campo;
    if (t.dataset.k !== undefined) { const v = parseFloat(t.value); if (!Number.isNaN(v)) f[campo][+t.dataset.k] = v; }
    else if (t.type === "checkbox") f[campo] = t.checked;
    else if (campo === "afinado" || campo === "suavidad") f[campo] = t.value === "" ? null : parseFloat(t.value);
    else f[campo] = t.value;
    if (t.tagName === "SELECT" || t.type === "checkbox") pintarFormas();
    dibujarAyudantes();
    programarMalla();
  });
  lista.addEventListener("click", (e) => {
    const b = e.target.closest("[data-accion-forma]");
    if (b) {
      const i = +b.dataset.f, L = est.formas.formas;
      if (b.dataset.accionForma === "borrar") { borrarForma(i); return; }
      if (b.dataset.accionForma === "duplicar") {
        const c = JSON.parse(JSON.stringify(L[i]));
        c.pos[0] += 3; c.nombre += " 2";
        L.splice(i + 1, 0, c); est.sel = i + 1;
      }
      if (b.dataset.accionForma === "ocultar") L[i].oculta = !L[i].oculta;
      pintarFormas(); programarMalla(0); return;
    }
    const card = e.target.closest("[data-sel]");
    if (card && +card.dataset.sel !== est.sel && !/INPUT|SELECT|BUTTON/.test(e.target.tagName)) {
      est.sel = +card.dataset.sel; pintarFormas(); dibujarAyudantes();
    }
  });
  lista.addEventListener("focusin", (e) => {
    const card = e.target.closest("[data-sel]");
    if (card && +card.dataset.sel !== est.sel) { est.sel = +card.dataset.sel; dibujarAyudantes(); card.classList.add("sel"); }
  });
  $("tl-formas-nombre").addEventListener("input", (e) => { est.formas.nombre = e.target.value; guardar(); });
  $("tl-suavidad").addEventListener("input", (e) => { est.formas.suavidad = parseFloat(e.target.value) || 0; programarMalla(); });
  $("tl-resolucion").addEventListener("change", (e) => { est.formas.resolucion = e.target.value; programarMalla(0); });
  document.querySelectorAll("[data-nueva-forma]").forEach((b) => b.addEventListener("click", () => nuevaForma(b.dataset.nuevaForma)));
  document.querySelectorAll("[data-gizmo]").forEach((b) => b.addEventListener("click", () => modoGizmo(b.dataset.gizmo)));
  $("tl-osito").addEventListener("click", async () => {
    if (est.costuras.formas.length && !confirm("¿Abrir el osito de ejemplo? Se reemplazan tus formas y costuras.")) return;
    await cargarOsito();
  });
  $("tl-vacio").addEventListener("click", () => {
    if (!confirm("¿Empezar con una sola esfera? Se borran las formas y costuras actuales.")) return;
    est.formas = { formato: "moldes-formas", version: 1, nombre: "Mi peluche", suavidad: 2, resolucion: "media",
      formas: [{ nombre: "Cuerpo", tipo: "esfera", modo: "unir", pos: [0, 10, 0], tam: [16, 20, 14], rot: [0, 0, 0] }] };
    est.costuras.formas = []; est.descartes.formas = []; est.sel = 0;
    pintarFormas(); programarMalla(0);
  });
}

async function cargarOsito() {
  const d = await (await fetch("ejemplos/osito.json?v=" + Date.now())).json();
  est.costuras.formas = (d.costuras || []).flatMap((c) => {
    const a = { ...c, id: siguienteId++ };
    delete a.espejo;
    if (!c.espejo) return [a];
    const b = { tipo: c.tipo, punto: M(c.punto), normal: [-c.normal[0], c.normal[1], c.normal[2]], anclas: c.anclas.map(M), id: siguienteId++, par: a.id };
    a.par = b.id;
    return [a, b];
  });
  delete d.costuras;
  est.formas = d;
  est.descartes.formas = [];
  est.sel = 0;
  pintarFormas();
  mallarFormas();
  encuadrar([0, 0.15, 1]);
}

// ------------------------------------------------------------------ maniquí
function pintarManiqui() {
  const m = est.maniqui;
  $("mq-talle").innerHTML = `<option value="">Personalizado</option>` +
    Object.entries(ESQ.maniqui.talles).map(([k, t]) => `<option value="${k}" ${k === m.talle ? "selected" : ""}>${esc(t.nombre)}</option>`).join("");
  $("mq-tipo").innerHTML = Object.entries(ESQ.maniqui.tipos).map(([k, t]) => `<option value="${k}" ${k === m.tipo ? "selected" : ""}>${esc(t)}</option>`).join("");
  $("mq-forma").innerHTML = Object.entries(ESQ.maniqui.formas).map(([k, t]) => `<option value="${k}" ${k === m.forma ? "selected" : ""}>${esc(t)}</option>`).join("");
  $("mq-holgura").value = m.holgura ?? 0;
  $("mq-resolucion").value = m.resolucion || "media";
  $("mq-medidas").innerHTML = ESQ.maniqui.medidas.map((d) =>
    `<label>${esc(d.nombre)} (cm)<input type="number" step="0.5" data-medida="${d.id}" value="${m.medidas[d.id] ?? d.valor}"></label>`).join("");
}

function conectarManiqui() {
  $("mq-talle").addEventListener("change", (e) => {
    const t = ESQ.maniqui.talles[e.target.value];
    est.maniqui.talle = e.target.value;
    if (t) { for (const d of ESQ.maniqui.medidas) est.maniqui.medidas[d.id] = t[d.id]; if (/hombre/.test(e.target.value)) est.maniqui.forma = "masculina"; else if (/nino/.test(e.target.value)) est.maniqui.forma = "neutra"; else est.maniqui.forma = "femenina"; }
    pintarManiqui(); guardar();
  });
  $("mq-medidas").addEventListener("input", (e) => {
    const id = e.target.dataset.medida;
    if (!id) return;
    est.maniqui.medidas[id] = parseFloat(e.target.value);
    est.maniqui.talle = "";
    $("mq-talle").value = "";
    guardar();
  });
  for (const [id, campo] of [["mq-tipo", "tipo"], ["mq-forma", "forma"], ["mq-resolucion", "resolucion"]]) {
    $(id).addEventListener("change", (e) => { est.maniqui[campo] = e.target.value; guardar(); });
  }
  $("mq-holgura").addEventListener("input", (e) => { est.maniqui.holgura = parseFloat(e.target.value) || 0; guardar(); });
  $("mq-armar").addEventListener("click", armarManiqui);
  $("mq-corpino").addEventListener("click", costurasCorpino);
}

async function armarManiqui() {
  $("mq-armar").disabled = true;
  $("mq-informe").textContent = "Armando el maniquí y midiéndolo… (unos segundos)";
  await new Promise((r) => setTimeout(r, 40));
  try {
    const d = JSON.parse(api.mallar_maniqui(JSON.stringify(est.maniqui)));
    est.maniqui.niveles = d.informe.niveles;
    ponerModelo(d, "maniqui", "Maniquí", "y", true);
    encuadrar([0, 0.1, 1]);
    const inf = d.informe, fmt = (v) => String(v).replace(".", ",");
    $("mq-informe").innerHTML = ["busto", "cintura", "cadera"].map((k) =>
      `${k[0].toUpperCase() + k.slice(1)}: ${fmt(inf[k].medido)} cm ${Math.abs(inf[k].medido - inf[k].pedido) <= 0.5 ? "✔" : `(pediste ${fmt(inf[k].pedido)})`}`).join(" · ") +
      ` · alto ${fmt(inf.alto)} cm` + (inf.holgura ? ` · con ${fmt(inf.holgura)} cm de holgura en todo el contorno` : "");
    guardar();
  } catch (e) {
    $("mq-informe").textContent = "Error: " + String(e.message || e).split("\n").filter(Boolean).pop();
  }
  $("mq-armar").disabled = false;
}

// costuras de un corpiño básico sobre el maniquí (centro, costados, hombros, escote, sisas y cintura)
function costurasCorpino() {
  if (!modelo || modelo.fuente !== "maniqui" || !est.maniqui.niveles) { aviso("Primero armá el maniquí.", "error"); return; }
  const N = est.maniqui.niveles, med = est.maniqui.medidas;
  const P = modelo.pos;
  let zmax = -Infinity, zmin = Infinity;
  const yb = N.y_busto;
  for (let i = 0; i < topo.nV; i++) if (Math.abs(P[i * 3 + 1] - yb) < 2 && Math.abs(P[i * 3]) < 3) { zmax = Math.max(zmax, P[i * 3 + 2]); zmin = Math.min(zmin, P[i * 3 + 2]); }
  const zl = (zmax + zmin) / 2; // plano del costado
  const ancho = (med.hombros || 39) / 2;
  const L = [];
  const plano = (punto, normal, anclas, espejo = false) => L.push({ tipo: "plano", punto, normal, anclas, espejo });
  // escote, cintura y sisas
  plano([0, N.y_nuca + 1.5, 0], [0, 1, 0], [[0, N.y_nuca + 1.5, zmax + 10], [0, N.y_nuca + 1.5, zmin - 10]]);
  plano([0, N.y_cintura, 0], [0, 1, 0], [[0, N.y_cintura, zmax + 20], [0, N.y_cintura, zmin - 20]]);
  const yh = N.y_hombro ?? N.y_nuca - 0.025 * med.altura;
  // sisa: plano vertical que pasa por la punta del hombro y por la axila
  const hom = [(N.x_hombro ?? ancho - 2) - 0.8, yh + 1, zl];
  const ax = [(N.x_axila ?? ancho - 5) + 0.3, (N.y_axila ?? yh - 10) - 1.5, zl];
  let nx = hom[1] - ax[1], ny = -(hom[0] - ax[0]);
  const ln = Math.hypot(nx, ny) || 1;
  nx /= ln; ny /= ln;
  if (nx < 0) { nx = -nx; ny = -ny; }
  const ym = (ax[1] + hom[1]) / 2, xm = ax[0] + (-ny / nx) * (ym - ax[1]);
  plano(ax, [nx, ny, 0], [[hom[0], hom[1] + 6, zl], [xm, ym, zl + 10], [xm, ym, zl - 10]], true);
  // centro delantero y espalda
  plano([0, 0, 0], [1, 0, 0], [[0, yb, zmax + 10], [0, yb, zmin - 10]]);
  // costados y hombros: un plano frontal
  plano([0, 0, zl], [0, 0, 1], [[ancho, yb - 6, zl], [-ancho, yb - 6, zl], [ancho * 0.6, yh + 8, zl], [-ancho * 0.6, yh + 8, zl]]);
  // armar con espejos
  const nuevas = L.flatMap((c) => {
    const a = { tipo: c.tipo, punto: c.punto, normal: c.normal, anclas: c.anclas, id: siguienteId++ };
    if (!c.espejo) return [a];
    const b = { tipo: c.tipo, punto: M(c.punto), normal: [-c.normal[0], c.normal[1], c.normal[2]], anclas: c.anclas.map(M), id: siguienteId++, par: a.id };
    a.par = b.id;
    return [a, b];
  });
  est.costuras.maniqui = nuevas;
  // fuera del molde: cabeza/cuello, brazos y de la cintura para abajo
  est.descartes.maniqui = [[0, N.y_nuca + 6, 0], [0, N.y_cintura - 8, zmax + 5]];
  resolver();
  // sacar también los brazos (cualquier pieza que no sea delantero/espalda)
  for (const pz of res.piezas) {
    if (!pz.descartada && !/^(Delantero|Espalda)/.test(pz.nombre)) {
      est.descartes.maniqui.push(centroCara(pz.caras[Math.floor(pz.caras.length / 2)]));
    }
  }
  guardar();
  irAPaso("costuras");
  resolver();
  aviso("Costuras de corpiño básico listas: centro, costados, hombros, escote, sisas y cintura. Podés sumar pinzas con «Trazar».");
}

// ------------------------------------------------------------------ archivo
function leerObj(texto) {
  const V = [], caras = [], gc = [], grupos = [];
  let g = 0;
  const grupo = (n) => { let i = grupos.indexOf(n); if (i < 0) { grupos.push(n); i = grupos.length - 1; } return i; };
  grupo("Pieza");
  for (const linea of texto.split(/\r?\n/)) {
    const p = linea.trim().split(/\s+/);
    if (p[0] === "v") V.push(+p[1], +p[2], +p[3]);
    else if (p[0] === "g" || p[0] === "o") g = grupo(p.slice(1).join(" ") || "Pieza");
    else if (p[0] === "f") {
      const idx = p.slice(1).map((s) => { const i = parseInt(s.split("/")[0], 10); return i > 0 ? i - 1 : V.length / 3 + i; });
      for (let k = 1; k < idx.length - 1; k++) { caras.push(idx[0], idx[k], idx[k + 1]); gc.push(g); }
    }
  }
  if (!caras.length) throw new Error("el archivo no tiene caras");
  // soldar vértices repetidos (bordes de grupos)
  let lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < V.length; i += 3) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], V[i + k]); hi[k] = Math.max(hi[k], V[i + k]); }
  const q = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) * 1e-6 || 1e-9;
  const mapa = new Map(), nuevo = new Int32Array(V.length / 3), pos = [];
  for (let i = 0; i < V.length / 3; i++) {
    const k = `${Math.round(V[i * 3] / q)},${Math.round(V[i * 3 + 1] / q)},${Math.round(V[i * 3 + 2] / q)}`;
    if (!mapa.has(k)) { mapa.set(k, pos.length / 3); pos.push(V[i * 3], V[i * 3 + 1], V[i * 3 + 2]); }
    nuevo[i] = mapa.get(k);
  }
  const usados = grupos.filter((_, i) => gc.includes(i));
  const remap = grupos.map((n) => usados.indexOf(n));
  return { posiciones: pos, caras: caras.map((i) => nuevo[i]), grupos: usados, grupo_cara: gc.map((i) => remap[i]), alto: 0 };
}

function cargarArchivo(nombre, texto, eje = "y") {
  const mismo = est.archivo && est.archivo.nombre === nombre && est.archivo.texto.length === texto.length;
  est.archivo = { nombre, texto, eje };
  const d = leerObj(texto);
  if (!mismo || !est.tocadas.archivo) { est.costuras.archivo = []; est.descartes.archivo = []; est.tocadas.archivo = false; }
  ponerModelo(d, "archivo", nombre, eje, false);
  // costuras iniciales: los bordes entre grupos del archivo
  if (!est.tocadas.archivo) {
    const ar = [];
    for (const [k, fs] of topo.aristas) {
      if (fs.length === 2 && modelo.grupoCara[fs[0]] !== modelo.grupoCara[fs[1]]) ar.push([deA(k), deB(k)]);
    }
    est.costuras.archivo = ar.length ? [{ tipo: "aristas", aristas: ar, id: siguienteId++ }] : [];
    est.descartes.archivo = [];
    est.tocadas.archivo = false;
    resolver();
  }
  encuadrar([0, 0.15, 1]);
  $("obj-nombre").textContent = `Modelo: ${nombre} · ${d.grupos.length} ${d.grupos.length === 1 ? "grupo" : "grupos"}`;
  $("eje").value = eje;
  guardar();
}

// ------------------------------------------------------------------ pasos y fuentes
function irAPaso(p) {
  est.paso = p;
  document.querySelectorAll("[data-paso]").forEach((b) => b.classList.toggle("activa", b.dataset.paso === p));
  for (const id of ["modelo", "costuras", "molde"]) $("tl-paso-" + id).classList.toggle("oculto", id !== p);
  $("tl-herr").classList.toggle("oculto", p !== "costuras");
  dibujarAyudantes();
  marcar(null);
  if (p !== "costuras") { trazo = null; cuchillo = null; dibujarPrevia(); }
  if (p === "costuras") { elegirHerramienta(est.herramienta); programarAnalisis(50); }
  if (p === "molde") prepararMolde();
  guardar();
}

function elegirFuente(f, { cargar = true } = {}) {
  est.fuente = f;
  document.querySelectorAll("[data-fuente]").forEach((b) => b.classList.toggle("activa", b.dataset.fuente === f));
  for (const id of ["formas", "maniqui", "archivo"]) $("tl-fuente-" + id).classList.toggle("oculto", id !== f);
  analisis = {};
  if (!cargar) return;
  if (f === "formas") { pintarFormas(); mallarFormas(); }
  else if (f === "archivo" && est.archivo) cargarArchivo(est.archivo.nombre, est.archivo.texto, est.archivo.eje);
  else if (f === "maniqui") { pintarManiqui(); if (est.maniqui.niveles) armarManiqui(); }
  dibujarAyudantes();
  guardar();
}

function prepararMolde() {
  const real = modelo && modelo.real;
  const nombre = modelo ? modelo.nombre : "";
  $("tl-molde-info").textContent = !modelo ? "Primero armá o cargá un modelo."
    : real ? `${nombre}: tamaño real (${String(modelo.alto).replace(".", ",")} cm de alto). Podés cambiar la altura para agrandarlo o achicarlo.`
      : `${nombre}: elegí la altura final del peluche.`;
  if (real && modelo.alto) $("altura").value = modelo.alto;
  const original = est.fuente === "archivo" && !est.tocadas.archivo;
  $("tl-modo-fila").classList.toggle("oculto", !original);
  $("tl-eje-fila").classList.toggle("oculto", est.fuente !== "archivo");
  actualizarBotones();
}

function actualizarBotones() {
  const b = $("btn-peluche");
  if (b) b.disabled = !(api && modelo && res && res.piezas.some((p) => !p.descartada));
}

export function hayModelo() { return !!(modelo && res && res.piezas.some((p) => !p.descartada)); }

function generarMolde() {
  if (!modelo) return;
  const original = est.fuente === "archivo" && !est.tocadas.archivo;
  const texto = original ? est.archivo.texto : objPiezas();
  const modo = original ? $("modo").value : "editor";
  const nombre = (modelo.nombre || "peluche").replace(/\.obj$/i, "");
  // Python escala según la altura de las piezas que recibe: si se sacaron piezas
  // (cabeza, piernas…), se pasa la altura proporcional para conservar la escala.
  const ieje = { x: 0, y: 1, z: 2 }[est.fuente === "archivo" ? $("eje").value : "y"];
  let lo = Infinity, hi = -Infinity, loU = Infinity, hiU = -Infinity;
  const P = modelo.pos, F = modelo.caras;
  for (const pz of res.piezas) {
    for (const f of pz.caras) {
      for (let k = 0; k < 3; k++) {
        const y = P[F[f * 3 + k] * 3 + ieje];
        lo = Math.min(lo, y); hi = Math.max(hi, y);
        if (!pz.descartada) { loU = Math.min(loU, y); hiU = Math.max(hiU, y); }
      }
    }
  }
  const pedida = parseFloat($("altura").value);
  const altura = original ? pedida : pedida * ((hiU - loU) / ((hi - lo) || 1));
  const opciones = {
    altura,
    eje: est.fuente === "archivo" ? $("eje").value : "y",
    modo, margen: parseFloat($("pel-margen").value), hoja: $("pel-hoja").value,
    titulo: (est.fuente === "maniqui" ? "Molde sobre maniquí: " : "Peluche: ") + nombre,
  };
  generar(() => api.generar_peluche(texto, JSON.stringify(opciones)), nombre.toLowerCase().replace(/\s+/g, "_"));
}

function descargar(nombre, texto, tipo) {
  const u = URL.createObjectURL(new Blob([texto], { type: tipo }));
  const a = document.createElement("a");
  a.href = u; a.download = nombre;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 2000);
}

function conectarGeneral() {
  document.querySelectorAll("[data-paso]").forEach((b) => b.addEventListener("click", () => irAPaso(b.dataset.paso)));
  document.querySelectorAll("[data-fuente]").forEach((b) => b.addEventListener("click", () => elegirFuente(b.dataset.fuente)));
  document.querySelectorAll("[data-ir]").forEach((b) => b.addEventListener("click", () => irAPaso(b.dataset.ir)));
  document.querySelectorAll("[data-herramienta]").forEach((b) => b.addEventListener("click", () => elegirHerramienta(b.dataset.herramienta)));
  document.querySelectorAll("[data-vista]").forEach((b) => b.addEventListener("click", () => {
    const v = { frente: [0, 0.05, 1], lado: [1, 0.05, 0], atras: [0, 0.05, -1], arriba: [0, 1, 0.02] }[b.dataset.vista];
    encuadrar(v);
  }));
  $("tl-ajustar").addEventListener("click", () => encuadrar());
  $("tl-simetria").checked = est.simetria;
  $("tl-simetria").addEventListener("change", (e) => { est.simetria = e.target.checked; guardar(); });
  $("tl-ver-estado").checked = est.verEstado;
  $("tl-ver-estado").addEventListener("change", (e) => { est.verEstado = e.target.checked; if (res) dibujarModelo(); guardar(); });
  $("tl-auto").addEventListener("change", () => programarAnalisis(50));
  $("tl-revisar").addEventListener("click", analizar);
  $("tl-borrar-todas").addEventListener("click", () => {
    if (!est.costuras[est.fuente].length || !confirm("¿Borrar todas las costuras de este modelo?")) return;
    est.costuras[est.fuente] = []; est.descartes[est.fuente] = [];
    if (est.fuente === "archivo") est.tocadas.archivo = true;
    guardar(); resolver();
  });
  $("tl-piezas").addEventListener("change", (e) => { const i = e.target.dataset.incluir; if (i !== undefined) alternarDescarte(+i); });
  $("tl-piezas").addEventListener("mouseover", (e) => { const li = e.target.closest("[data-pieza]"); const i = li ? +li.dataset.pieza : -1; if (i !== resaltada) { resaltada = i; dibujarModelo(); } });
  $("tl-piezas").addEventListener("mouseleave", () => { resaltada = -1; if (res) dibujarModelo(); });
  $("btn-peluche").addEventListener("click", generarMolde);
  $("obj").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try { cargarArchivo(f.name, await f.text(), $("eje").value); } catch (err) { aviso("No pude leer el .obj: " + err.message, "error"); }
  });
  $("btn-ejemplo").addEventListener("click", async () => {
    const r = await fetch("ejemplos/rana.obj");
    est.tocadas.archivo = false;
    cargarArchivo("rana.obj", await r.text(), "y");
  });
  $("eje").addEventListener("change", (e) => { if (est.archivo) { est.archivo.eje = e.target.value; cargarArchivo(est.archivo.nombre, est.archivo.texto, e.target.value); } });
  $("tl-bajar-obj").addEventListener("click", () => { if (modelo) descargar((modelo.nombre || "modelo").replace(/\.obj$/i, "") + "_piezas.obj", objPiezas(), "text/plain"); });
  $("tl-exportar").addEventListener("click", () => {
    descargar("proyecto_peluche.json", JSON.stringify({ formato: "moldes-taller", version: 1, ...est }, null, 1), "application/json");
  });
  $("tl-importar").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try {
      const d = JSON.parse(await f.text());
      if (d.formato === "moldes-formas") { est.formas = d; est.costuras.formas = []; elegirFuente("formas"); return; }
      if (d.formato !== "moldes-taller") throw new Error("no es un proyecto de Moldes");
      Object.assign(est, d);
      reiniciarIds();
      elegirFuente(est.fuente);
      irAPaso("modelo");
    } catch (err) { aviso("No pude abrir el proyecto: " + err.message, "error"); }
  });
}

function reiniciarIds() {
  let m = 0;
  for (const l of Object.values(est.costuras)) for (const c of l) m = Math.max(m, c.id || 0);
  siguienteId = m + 1;
}

// ------------------------------------------------------------------ arranque
export async function iniciarTaller(apiPython, fnGenerar, fnAviso) {
  api = apiPython; generar = fnGenerar; aviso = fnAviso;
  ESQ = JSON.parse(api.esquema_taller());
  const g = leerGuardado();
  if (g && g.formas) Object.assign(est, g);
  est.maniqui = est.maniqui || { medidas: {}, tipo: "completo", forma: "femenina", holgura: 0, resolucion: "media", talle: "mujer_m" };
  for (const d of ESQ.maniqui.medidas) if (est.maniqui.medidas[d.id] == null) est.maniqui.medidas[d.id] = d.valor;
  for (const k of ["formas", "maniqui", "archivo"]) { est.costuras[k] = est.costuras[k] || []; est.descartes[k] = est.descartes[k] || []; }
  reiniciarIds();
  iniciarEscena();
  conectarFormas();
  conectarManiqui();
  conectarGeneral();
  pintarManiqui();
  if (!est.formas) {
    est.formas = { formas: [] };
    elegirFuente("formas", { cargar: false });
    await cargarOsito();
  } else {
    elegirFuente(est.fuente === "archivo" && !est.archivo ? "formas" : est.fuente);
  }
  irAPaso(est.paso || "modelo");
  modoGizmo("translate");
  // para inspeccionar desde la consola del navegador
  window.moldesTaller = { est, get res() { return res; }, get modelo() { return modelo; }, get analisis() { return analisis; }, resolver, objPiezas };
}
