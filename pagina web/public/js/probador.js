// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Probador con la cámara, en el navegador: MediaPipe Pose Landmarker (versión web)
// detecta el cuerpo, la prenda se deforma con la malla (malla.js) y se recorta a la
// silueta. Nada de la cámara sale de la compu: no se suben imágenes al servidor.
// ==========================================================

import { FilesetResolver, PoseLandmarker } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs";

const { api, precio, stockDe, cliente, aviso } = Comun;
const $ = (sel) => document.querySelector(sel);
const video = $("#video");
// Modo demostración: probador.html?foto=imagen.jpg usa una foto en lugar de la cámara
// (sirve para mostrarlo en una presentación o probarlo sin cámara).
const fotoDemo = new URLSearchParams(location.search).get("foto");
let fuente = video;
const lienzo = $("#lienzo");
const ctx = lienzo.getContext("2d");
const capaPrenda = document.createElement("canvas");
const ctxPrenda = capaPrenda.getContext("2d");
const capaSilueta = document.createElement("canvas");
const ctxSilueta = capaSilueta.getContext("2d");
const siluetaChica = document.createElement("canvas");
const ctxSiluetaChica = siluetaChica.getContext("2d");

const estado = {
  prendas: [], ventas: false, indice: 0, color: null, talle: "M", ajuste: 1.0, silueta: true,
  imagenes: new Map(), detector: null, puntos: null, hayPersona: false, inicioPrenda: performance.now(),
  pruebaGuardada: new Set(), ultimaCompra: 0, ultimoTiempoVideo: -1,
};

// ---------------------------------------------------------------- filtro One Euro
// Quita el temblor de los puntos sin atrasar los movimientos rápidos (el mismo
// filtro que usa el probador de escritorio).
class FiltroOneEuro {
  constructor(minCorte = 1.2, beta = 0.02, corteDerivada = 1.0) {
    Object.assign(this, { minCorte, beta, corteDerivada, x: null, dx: 0, t: null });
  }
  static alfa(corte, dt) { const tau = 1 / (2 * Math.PI * corte); return 1 / (1 + tau / dt); }
  filtrar(valor, t) {
    if (this.x === null) { this.x = valor; this.t = t; return valor; }
    const dt = Math.max(1e-3, (t - this.t) / 1000);
    this.t = t;
    const dx = (valor - this.x) / dt;
    this.dx += FiltroOneEuro.alfa(this.corteDerivada, dt) * (dx - this.dx);
    const corte = this.minCorte + this.beta * Math.abs(this.dx);
    this.x += FiltroOneEuro.alfa(corte, dt) * (valor - this.x);
    return this.x;
  }
}
const filtros = new Map();
function suavizar(nombre, p, t) {
  if (!filtros.has(nombre)) filtros.set(nombre, [new FiltroOneEuro(), new FiltroOneEuro()]);
  const [fx, fy] = filtros.get(nombre);
  return [fx.filtrar(p[0], t), fy.filtrar(p[1], t)];
}

// Índices de MediaPipe Pose
const PUNTOS = {
  nose: 0, ear_left: 7, ear_right: 8, mouth_left: 9, mouth_right: 10,
  sh_left: 11, sh_right: 12, elb_left: 13, elb_right: 14, wri_left: 15, wri_right: 16, hip_left: 23, hip_right: 24,
};

// ---------------------------------------------------------------- prenda actual
const prenda = () => estado.prendas[estado.indice];

function imagenDe(p, color) {
  const ruta = p.imagenes[color] || Object.values(p.imagenes)[0];
  if (!estado.imagenes.has(ruta)) {
    const img = new Image();
    img.src = ruta;
    estado.imagenes.set(ruta, img);
  }
  return estado.imagenes.get(ruta);
}

function elegirPrenda(indice, color, talle) {
  registrarPrueba();  // la prenda anterior queda registrada como probada
  estado.indice = (indice + estado.prendas.length) % estado.prendas.length;
  const p = prenda();
  estado.color = p.colores.some(c => c.nombre === color) ? color : p.colores[0].nombre;
  const c = cliente();
  estado.talle = p.talles.includes(talle) ? talle
    : (c && p.talles.includes(c.talle_preferido) ? c.talle_preferido : (p.talles.includes("M") ? "M" : p.talles[0]));
  estado.inicioPrenda = performance.now();
  $("#elegir-prenda").value = String(estado.indice);
  $("#elegir-color").innerHTML = p.colores.map(c => `<option>${Comun.escapar(c.nombre)}</option>`).join("");
  $("#elegir-color").value = estado.color;
  dibujarTalles();
  $("#nombre-prenda").textContent = p.nombre;
  $("#precio-prenda").textContent = precio(p.precio);
  imagenDe(p, estado.color);
  actualizarVolver();
}

function dibujarTalles() {
  const p = prenda();
  $("#elegir-talle").innerHTML = p.talles.map(t => {
    const hay = !estado.ventas || stockDe(p, estado.color, t) > 0;
    return `<option value="${Comun.escapar(t)}">${Comun.escapar(t)}${hay ? "" : " (sin stock)"}</option>`;
  }).join("");
  $("#elegir-talle").value = estado.talle;
}

function actualizarVolver() {
  const p = prenda();
  const url = `./?prenda=${encodeURIComponent(p.codigo)}&color=${encodeURIComponent(estado.color)}&talle=${encodeURIComponent(estado.talle)}`;
  $("#volver").href = url;
  $("#volver-tienda").href = url;
}

// ---------------------------------------------------------------- base de datos
// Igual que el programa de escritorio: se guarda QUÉ se probó y cuánto tiempo (nunca imágenes)
function registrarPrueba() {
  const p = prenda();
  if (!p || !estado.ventas || !p.id_prenda || estado.pruebaGuardada.has(p.codigo)) return;
  const segundos = (performance.now() - estado.inicioPrenda) / 1000;
  if (segundos < 3) return;
  estado.pruebaGuardada.add(p.codigo);
  const c = cliente();
  const datos = JSON.stringify({ id_prenda: p.id_prenda, color: estado.color, talle: estado.talle,
    segundos, id_cliente: c ? c.id_cliente : null });
  navigator.sendBeacon("/api/pruebas", new Blob([datos], { type: "application/json" }));
}

async function comprar() {
  const p = prenda();
  if (!estado.ventas || !p.id_prenda) {
    aviso("La tienda está en modo vidriera: todavía no se puede comprar.", "error");
    return;
  }
  if (performance.now() - estado.ultimaCompra < 2000) return;  // un doble toque no compra dos veces
  estado.ultimaCompra = performance.now();
  const c = cliente();
  $("#comprar").disabled = true;
  try {
    const { id_prueba } = await api("pruebas", {
      id_prenda: p.id_prenda, color: estado.color, talle: estado.talle,
      segundos: (performance.now() - estado.inicioPrenda) / 1000, id_cliente: c ? c.id_cliente : null,
    });
    estado.pruebaGuardada.add(p.codigo);
    const r = await api("compras", {
      items: [{ id_prenda: p.id_prenda, color: estado.color, talle: estado.talle, cantidad: 1 }],
      id_cliente: c ? c.id_cliente : null, id_prueba,
    });
    if (r.cliente) Comun.guardarCliente(r.cliente);
    const clave = `${estado.color}|${estado.talle}`;
    p.stock[clave] = Math.max(0, (p.stock[clave] || 1) - 1);
    dibujarTalles();
    aviso(`Compra #${r.id_compra} registrada: ${p.nombre} ${estado.talle} por ${precio(r.detalle.total)}`
      + (c ? "" : " (como invitada/o)"), "ok");
  } catch (error) {
    aviso(error.message, "error");
  } finally {
    $("#comprar").disabled = false;
  }
}

// ---------------------------------------------------------------- cámara y MediaPipe
async function iniciarCamara() {
  if (fotoDemo) {
    fuente = new Image();
    fuente.src = fotoDemo;
    await fuente.decode();
    for (const c of [lienzo, capaPrenda, capaSilueta]) { c.width = fuente.naturalWidth; c.height = fuente.naturalHeight; }
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("Este navegador no permite usar la cámara (hace falta https).");
  }
  const flujo = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
  });
  video.srcObject = flujo;
  await video.play();
  for (const c of [lienzo, capaPrenda, capaSilueta]) { c.width = video.videoWidth; c.height = video.videoHeight; }
}

async function iniciarDetector() {
  const archivos = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  const opciones = (delegado) => ({
    baseOptions: { modelAssetPath: "modelos/pose_landmarker_lite.task", delegate: delegado },
    runningMode: "VIDEO", numPoses: 1, outputSegmentationMasks: true,
    minPoseDetectionConfidence: 0.5, minPosePresenceConfidence: 0.5, minTrackingConfidence: 0.5,
  });
  try {
    estado.detector = await PoseLandmarker.createFromOptions(archivos, opciones("GPU"));
  } catch (e) {
    estado.detector = await PoseLandmarker.createFromOptions(archivos, opciones("CPU"));
  }
}

// La silueta de MediaPipe (0 a 1 por píxel) pasa a una capa con borde suave y espejada
function actualizarSilueta(mascara) {
  const ancho = mascara.width, alto = mascara.height;
  const valores = mascara.getAsFloat32Array();
  if (siluetaChica.width !== ancho || siluetaChica.height !== alto) { siluetaChica.width = ancho; siluetaChica.height = alto; }
  const datos = ctxSiluetaChica.createImageData(ancho, alto);
  const px = datos.data;
  for (let i = 0, j = 3; i < valores.length; i++, j += 4) px[j] = valores[i] > 0.35 ? 255 : valores[i] * 728;
  ctxSiluetaChica.putImageData(datos, 0, 0);
  ctxSilueta.save();
  ctxSilueta.clearRect(0, 0, capaSilueta.width, capaSilueta.height);
  ctxSilueta.setTransform(-1, 0, 0, 1, capaSilueta.width, 0);
  ctxSilueta.filter = `blur(${Math.max(2, Math.round(capaSilueta.width / 320))}px)`;
  ctxSilueta.drawImage(siluetaChica, 0, 0, capaSilueta.width, capaSilueta.height);
  ctxSilueta.restore();
}

function detectar(ahora) {
  if (!estado.detector || (!fotoDemo && video.currentTime === estado.ultimoTiempoVideo)) return;
  estado.ultimoTiempoVideo = video.currentTime;
  const resultado = estado.detector.detectForVideo(fuente, ahora);
  try {
    const lms = resultado.landmarks && resultado.landmarks[0];
    if (!lms) { estado.hayPersona = false; return; }
    const W = lienzo.width, H = lienzo.height;
    const pts = {}, vis = {};
    for (const [nombre, i] of Object.entries(PUNTOS)) {
      // Imagen espejada: x de la pantalla = 1 - x de la cámara
      pts[nombre] = suavizar(nombre, [(1 - lms[i].x) * W, lms[i].y * H], ahora);
      vis[nombre] = lms[i].visibility ?? 1;
    }
    estado.puntos = { pts, vis };
    estado.hayPersona = vis.sh_left > 0.5 && vis.sh_right > 0.5;
    if (resultado.segmentationMasks && resultado.segmentationMasks[0]) actualizarSilueta(resultado.segmentationMasks[0]);
  } finally {
    if (resultado.close) resultado.close();
  }
}

function dibujarPrenda() {
  const p = prenda();
  const img = imagenDe(p, estado.color);
  if (!img.complete || !img.naturalWidth || !estado.puntos) return;
  const W = lienzo.width, H = lienzo.height;
  const g = Malla.geometriaCorporal(estado.puntos.pts, estado.puntos.vis, W, H);
  const dst = Malla.puntosDestino(g, p, estado.talle, estado.ajuste);
  if (fotoDemo) document.body.dataset.malla = JSON.stringify({ dst, g });  // para revisar la malla en el modo foto
  ctxPrenda.setTransform(1, 0, 0, 1, 0, 0);
  ctxPrenda.globalCompositeOperation = "source-over";
  ctxPrenda.clearRect(0, 0, W, H);
  Malla.dibujarMalla(ctxPrenda, img, p.puntos, dst, p.tiene_mangas);
  // Prenda pegada al cuerpo: lo que cae fuera de la silueta (más un borde suave) se borra
  if (estado.silueta) {
    ctxPrenda.globalCompositeOperation = "destination-in";
    ctxPrenda.drawImage(capaSilueta, 0, 0);
  }
  // La prenda nunca tapa la cara
  if (g.medioCara && g.menton && g.nariz) {
    ctxPrenda.globalCompositeOperation = "destination-out";
    const alto = Math.hypot(g.menton[0] - g.nariz[0], g.menton[1] - g.nariz[1]) * 1.25;
    ctxPrenda.beginPath();
    ctxPrenda.ellipse(g.nariz[0], g.nariz[1], g.medioCara, alto, Math.atan2(g.uSh[1], g.uSh[0]), 0, Math.PI * 2);
    ctxPrenda.fill();
  }
  ctxPrenda.globalCompositeOperation = "source-over";
  // Sombra suave bajo la tela: la prenda parece apoyada sobre el cuerpo
  ctx.save();
  ctx.shadowColor = "rgba(0, 0, 0, 0.28)";
  ctx.shadowBlur = Math.max(4, g.distSh * 0.04);
  ctx.shadowOffsetY = Math.max(1, g.distSh * 0.015);
  ctx.drawImage(capaPrenda, 0, 0);
  ctx.restore();
  return g;
}

// Con la cámara se dibuja al ritmo de la pantalla. En el modo foto se usa un reloj
// común, que sigue andando aunque la pestaña no esté a la vista.
function siguienteCuadro() {
  if (fotoDemo) setTimeout(() => cuadro(performance.now()), 66);
  else requestAnimationFrame(cuadro);
}

function cuadro(ahora) {
  if (fotoDemo || video.readyState >= 2) {
    detectar(ahora);
    const W = lienzo.width, H = lienzo.height;
    ctx.setTransform(-1, 0, 0, 1, W, 0);  // espejo, como un probador de verdad
    ctx.drawImage(fuente, 0, 0, W, H);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    let g = null;
    if (estado.hayPersona) g = dibujarPrenda();
    const mensaje = !estado.hayPersona ? "Parate frente a la cámara, a unos 2 metros"
      : (g && !g.caderasVisibles ? "Alejate un poco: que se vea hasta tu cadera" : "");
    $("#mensaje").textContent = mensaje;
    $("#mensaje").classList.toggle("oculto", !mensaje);
  }
  siguienteCuadro();
}

// ---------------------------------------------------------------- controles
function conectarControles() {
  $("#elegir-prenda").innerHTML = estado.prendas.map((p, i) => `<option value="${i}">${Comun.escapar(p.nombre)}</option>`).join("");
  $("#elegir-prenda").onchange = (e) => elegirPrenda(Number(e.target.value), null, estado.talle);
  $("#anterior").onclick = () => elegirPrenda(estado.indice - 1, null, estado.talle);
  $("#siguiente").onclick = () => elegirPrenda(estado.indice + 1, null, estado.talle);
  $("#elegir-color").onchange = (e) => { estado.color = e.target.value; dibujarTalles(); actualizarVolver(); };
  $("#elegir-talle").onchange = (e) => { estado.talle = e.target.value; actualizarVolver(); };
  $("#menos").onclick = () => { estado.ajuste = Math.max(0.8, estado.ajuste - 0.04); };
  $("#mas").onclick = () => { estado.ajuste = Math.min(1.3, estado.ajuste + 0.04); };
  $("#silueta").onclick = (e) => {
    estado.silueta = !estado.silueta;
    e.target.setAttribute("aria-pressed", String(estado.silueta));
  };
  $("#foto").onclick = () => lienzo.toBlob((blob) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `probador-${prenda().codigo}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }, "image/png");
  $("#comprar").onclick = comprar;
  window.addEventListener("pagehide", registrarPrueba);
  window.addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT") return;
    const k = e.key.toLowerCase();
    if (k === "n" || e.key === "ArrowRight") elegirPrenda(estado.indice + 1, null, estado.talle);
    else if (k === "p" || e.key === "ArrowLeft") elegirPrenda(estado.indice - 1, null, estado.talle);
    else if (k === "b") comprar();
    else if (k === "c") $("#foto").click();
    else if (k === "+") $("#mas").click();
    else if (k === "-") $("#menos").click();
  });
}

// ---------------------------------------------------------------- arranque
(async () => {
  try {
    const r = await Comun.cargarCatalogo();
    estado.prendas = r.prendas;
    estado.ventas = r.ventas;
    if (!estado.prendas.length) throw new Error("El catálogo está vacío.");
    conectarControles();
    const q = new URLSearchParams(location.search);
    const i = Math.max(0, estado.prendas.findIndex(p => p.codigo === q.get("prenda")));
    elegirPrenda(i, q.get("color"), q.get("talle"));
    if (!estado.ventas) $("#comprar").title = "Modo vidriera: sin base de datos";
  } catch (error) {
    $("#mensaje").textContent = "No se pudo cargar el catálogo.";
    return;
  }
  try {
    $("#mensaje").textContent = "Pedimos permiso para usar la cámara…";
    await iniciarCamara();
    $("#mensaje").textContent = "Cargando el detector del cuerpo…";
    await iniciarDetector();
    siguienteCuadro();
  } catch (error) {
    console.error(error);
    $("#mensaje").textContent = error.name === "NotAllowedError"
      ? "Sin permiso para la cámara. Habilitala en el navegador (ícono del candado) y recargá la página."
      : `No se pudo iniciar el probador: ${error.message}`;
  }
})();
