// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Integra la prenda con la cámara, para que no parezca un recorte pegado encima:
//   1. Cobertura: la tela es opaca. De la ropa de abajo no pasa ningún detalle, y el torso
//      queda cubierto aunque la silueta de la cámara falle en alguna zona.
//   2. Luz: la tela toma la luz del lugar (muy desenfocada), su brillo general y su tono.
//   3. Cámara: la prenda recibe la misma suavidad y un poco de grano de una webcam.
//   4. Bordes: la tela se oscurece hacia el contorno, donde da la vuelta al cuerpo.
//   5. Pliegues y caída: se generan según la pose (nada viene de la ropa de la persona).
//      Es una aproximación visual, no una simulación física de la tela.
//   6. Movimiento: el ruedo y los puños siguen al cuerpo con un pequeño resorte, y se
//      ignoran los saltos bruscos de la detección.
//   7. Partes de la persona (partes_worker.js): el pelo, la cara y el cuello quedan por
//      delante de la prenda, y la ropa propia que asoma cerca se pinta del color de la tela.
// Todo se hace en el navegador: la imagen de la cámara no sale del dispositivo.
// ==========================================================

const Realismo = (() => {
  const INTENSIDAD_LUZ = 0.22;
  const PASADAS_OPACIDAD = 5;        // cada pasada acerca a 1 el alfa de la tela, sin endurecer el borde
  const MARGEN_TORSO = 0.94;         // la zona que se cubre siempre, un poco adentro del contorno
  const INTENSIDAD_PLIEGUES = 0.42;
  const RIGIDEZ_RESORTE = 170, FRENO_RESORTE = 20;
  const CUADROS_DE_SALTO = 6;        // un cambio que dura más que esto es real, no un error
  const MS_LENTO = 45;               // más que esto entre cuadros: se pasa al modo liviano
  const MS_ENTRE_PARTES = 180;       // cada cuánto se vuelve a separar a la persona en partes
  const MS_PARTES_VIEJAS = 1500;     // con una separación más vieja que esto, no se usa
  const LADO_PARTES = 384;
  const PELO = 1, PIEL = 2, CARA = 3, ROPA = 4;
  const INTENSIDAD_GRANO = 0.05;
  const SATURACION = 1.28;           // la luz y la suavidad apagan el color: se le devuelve
  // En una tela clara, el mismo oscurecimiento del contorno se nota mucho más
  const INTENSIDAD_BORDE_OSCURA = 0.40;
  const INTENSIDAD_BORDE_CLARA = 0.16;
  const CUADROS_POR_MEDICION = 15;   // el brillo del lugar cambia lento: no hace falta medirlo siempre

  const nuevo = (w = 1, h = 1) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  const redondeo = nuevo(), persona = nuevo();
  const plano = nuevo();
  const copia = nuevo(), entera = nuevo(), chica = nuevo(), luz = nuevo(), borde = nuevo(), pliegues = nuevo(), plieguesSuaves = nuevo();
  const medidor = nuevo(8, 8);
  const ctxMedidor = medidor.getContext("2d", { willReadFrequently: true });
  const hayFiltros = typeof ctxMedidor.filter === "string";
  const estado = { W: 0, H: 0, cuadro: 0, media: 128, tinte: "rgb(255,255,255)", exposicion: 1, grano: null,
    pose: null, rechazos: 0, resortes: new Map(), tiempo: 0, ultimoCuadro: 0, msCuadro: 16, liviano: false,
    trabajador: null, ocupado: false, envio: 0, partes: null, sinPartes: false, colorTela: "#808080", colorCuadro: -999 };
  const capasPartes = { [PELO]: nuevo(), [PIEL]: nuevo(), [CARA]: nuevo(), [ROPA]: nuevo() };
  const pintura = nuevo();

  function preparar(W, H) {
    if (estado.W === W && estado.H === H) return;
    Object.assign(estado, { W, H });
    for (const c of [copia, entera]) { c.width = W; c.height = H; }
    chica.width = Math.ceil(W / 4); chica.height = Math.ceil(H / 4);
    luz.width = Math.ceil(W / 16); luz.height = Math.ceil(H / 16);
    for (const c of [borde, pliegues, plieguesSuaves]) { c.width = Math.ceil(W / 2); c.height = Math.ceil(H / 2); }
  }

  function crearGrano(ctx) {
    const c = nuevo(128, 128), x = c.getContext("2d"), datos = x.createImageData(128, 128);
    for (let i = 0; i < datos.data.length; i += 4) {
      const v = 128 + (Math.random() - 0.5) * 110;
      datos.data[i] = datos.data[i + 1] = datos.data[i + 2] = v;
      datos.data[i + 3] = 255;
    }
    x.putImageData(datos, 0, 0);
    return ctx.createPattern(c, "repeat");
  }

  // Lo que ve la cámara, espejado como la imagen de la pantalla y a un cuarto del tamaño
  function actualizarCamara(fuente, g) {
    const xc = chica.getContext("2d");
    xc.setTransform(-1, 0, 0, 1, chica.width, 0);
    xc.drawImage(fuente, 0, 0, chica.width, chica.height);
    xc.setTransform(1, 0, 0, 1, 0, 0);
    const escala = g.distSh / 16;

    if (hayFiltros) {
      // Sólo la luz general: tan desenfocada que no pasa ningún dibujo de la ropa de abajo
      const xl = luz.getContext("2d");
      // (el brillo se ajusta acá, en chico: en la pantalla completa ese filtro es muy caro)
      xl.filter = `grayscale(1) blur(${Math.max(3, escala * 0.16)}px) brightness(${Math.min(1.8, Math.max(0.6, 128 / estado.media)).toFixed(2)})`;
      xl.drawImage(chica, 0, 0, luz.width, luz.height);
      xl.filter = "none";
    }

    if (estado.cuadro % CUADROS_POR_MEDICION === 0) {
      // Brillo y tono de la zona del cuerpo
      const lado = g.distSh / 4;
      const cx = g.cuello[0] / 4, cy = (g.cuello[1] + g.uTorso[1] * g.distTorso * 0.5) / 4;
      ctxMedidor.drawImage(chica, cx - lado * 0.8, cy - lado * 0.8, lado * 1.6, lado * 1.6, 0, 0, 8, 8);
      const px = ctxMedidor.getImageData(0, 0, 8, 8).data;
      let r = 0, v = 0, a = 0;
      for (let i = 0; i < px.length; i += 4) { r += px[i]; v += px[i + 1]; a += px[i + 2]; }
      const n = px.length / 4;
      r /= n; v /= n; a /= n;
      const maximo = Math.max(r, v, a, 1);
      estado.media = Math.max(20, 0.3 * r + 0.59 * v + 0.11 * a);
      estado.exposicion = Math.min(1, Math.max(0.86, estado.media / 110));
      const canal = (c) => Math.round(255 * estado.exposicion * (0.86 + 0.14 * c / maximo));
      estado.tinte = `rgb(${canal(r)},${canal(v)},${canal(a)})`;
    }
  }

  /** Guarda la separación en partes: una capa por parte, con alfa donde está. */
  function actualizarPartes(categorias, ancho, alto, cuello = null, W = 0) {
    for (const parte of [PELO, PIEL, CARA, ROPA]) {
      const c = capasPartes[parte];
      if (c.width !== ancho || c.height !== alto) { c.width = ancho; c.height = alto; }
      const x = c.getContext("2d");
      const datos = x.createImageData(ancho, alto);
      for (let i = 0, j = 3; i < categorias.length; i++, j += 4) datos.data[j] = categorias[i] === parte ? 255 : 0;
      x.putImageData(datos, 0, 0);
    }
    estado.partes = { cuando: performance.now(), cuello, W, cat: categorias, ancho, alto };
  }

  /**
   * Base real del cuello, medida en la separación en partes: bajando desde el mentón, la piel
   * del cuello es una columna angosta; donde se ensancha (hombros) o se termina (ropa) está la
   * base. Devuelve { base: [x, y], medio } en la pantalla, o null si no se puede medir.
   */
  function medirCuello(g) {
    const p = estado.partes;
    if (!p || !p.cat || !p.W || !p.cuello || performance.now() - p.cuando > MS_PARTES_VIEJAS) return null;
    const { cat, ancho, alto, W } = p;
    const sx = W / ancho, sy = sx;
    const dx = g.cuello[0] - p.cuello[0], dy = g.cuello[1] - p.cuello[1];
    const columna = (x) => Math.round((W + dx - x) / sx);
    const fila = (y) => Math.round((y - dy) / sy);
    const desde = g.menton || [g.cuello[0], g.cuello[1] - g.distSh * 0.55];
    const j0 = Math.max(0, fila(desde[1])), j1 = Math.min(alto - 1, fila(g.cuello[1] + g.distSh * 0.10));
    let ic = columna(desde[0]);
    if (ic < 1 || ic >= ancho - 1 || j1 - j0 < 4) return null;
    const filas = [];
    for (let j = j0; j <= j1; j++) {
      const o = j * ancho;
      let c = -1;
      for (const d of [0, -1, 1, -2, 2, -3, 3, -4, 4]) if (cat[o + ic + d] === PIEL) { c = ic + d; break; }
      if (c < 0) { filas.push({ j, w: 0 }); continue; }
      let a = c, b = c;
      while (a > 0 && cat[o + a - 1] === PIEL) a--;
      while (b < ancho - 1 && cat[o + b + 1] === PIEL) b++;
      filas.push({ j, w: (b - a + 1) * sx, c: (a + b) / 2 });
      ic = Math.round((a + b) / 2);
    }
    const conPiel = filas.filter(f => f.w > 0);
    if (conPiel.length < 4) return null;
    const anchos = conPiel.slice(0, Math.max(3, Math.ceil(conPiel.length / 2))).map(f => f.w).sort((x, y) => x - y);
    const anchoCuello = anchos[Math.floor(anchos.length / 2)];
    let baseJ = null, visto = 0;
    const centros = [];
    for (const f of filas) {
      if (f.w > 0 && f.w < anchoCuello * 1.6) { visto++; centros.push(f.c); continue; }
      if (visto >= 3) { baseJ = f.j; break; }
    }
    if (baseJ === null) return null;
    centros.sort((x, y) => x - y);
    const base = [W + dx - centros[Math.floor(centros.length / 2)] * sx, baseJ * sy + dy];
    const medio = anchoCuello / 2;
    if (medio < g.distSh * 0.08 || medio > g.distSh * 0.32) return null;
    if (base[1] < g.cuello[1] - g.distSh * 0.45 || base[1] > g.cuello[1] + g.distSh * 0.12) return null;
    if (Math.abs(base[0] - g.cuello[0]) > g.distSh * 0.3) return null;
    return { base, medio };
  }

  // La medida del cuello cambia suave entre cuadros (y se olvida si deja de medirse un rato)
  function cuelloSuave(g) {
    const m = medirCuello(g);
    const u = estado.cuelloReal;
    if (!m) {
      if (u && performance.now() - u.cuando < 600) return u;
      estado.cuelloReal = null;
      return null;
    }
    if (u) {
      m.base = [u.base[0] + (m.base[0] - u.base[0]) * 0.35, u.base[1] + (m.base[1] - u.base[1]) * 0.35];
      m.medio = u.medio + (m.medio - u.medio) * 0.35;
    }
    m.cuando = performance.now();
    estado.cuelloReal = m;
    return m;
  }

  function escucharTrabajador() {
    estado.trabajador = new Worker("js/partes_worker.js");
    estado.trabajador.onmessage = ({ data }) => {
      if (data.listo) return;
      if (data.id !== undefined) estado.ocupado = false;
      if (data.error) { console.info("Partes de la persona:", data.error); return; }
      if (data.categorias) actualizarPartes(data.categorias, data.ancho, data.alto, estado.cuelloEnviado, estado.W);
    };
    // Sin este modelo el probador funciona igual: sólo no separa el pelo y el cuello
    estado.trabajador.onerror = (e) => { console.info("Partes de la persona:", e.message); estado.sinPartes = true; };
  }

  /** Manda el cuadro al proceso aparte, si está libre y ya pasó un rato. No espera el resultado. */
  function enviarCuadro(fuente, g) {
    const ahora = performance.now();
    if (estado.sinPartes || estado.liviano || estado.ocupado || ahora - estado.envio < MS_ENTRE_PARTES) return;
    if (!estado.trabajador) {
      try { escucharTrabajador(); } catch (e) { estado.sinPartes = true; return; }
    }
    const w = fuente.videoWidth || fuente.naturalWidth || fuente.width;
    const h = fuente.videoHeight || fuente.naturalHeight || fuente.height;
    if (!w || !h || !window.createImageBitmap) return;
    estado.ocupado = true;
    estado.envio = ahora;
    estado.cuelloEnviado = g.cuello.slice();
    createImageBitmap(fuente, { resizeWidth: LADO_PARTES, resizeHeight: Math.round(LADO_PARTES * h / w), resizeQuality: "low" })
      .then((imagen) => estado.trabajador.postMessage({ imagen, id: ahora }, [imagen]))
      .catch(() => { estado.ocupado = false; });
  }

  // Dibuja una capa de partes espejada, corrida lo que se movió el cuello desde que se calculó
  function dibujarParte(ctx, parte, W, H, dx, dy) {
    ctx.save();
    ctx.setTransform(-1, 0, 0, 1, W + dx, dy);
    ctx.drawImage(capasPartes[parte], 0, 0, W, H);
    ctx.restore();
  }

  function medirColorTela() {
    if (estado.cuadro - estado.colorCuadro < 30) return;
    estado.colorCuadro = estado.cuadro;
    ctxMedidor.clearRect(0, 0, 8, 8);
    ctxMedidor.drawImage(copia, 0, 0, 8, 8);
    const px = ctxMedidor.getImageData(0, 0, 8, 8).data;
    let r = 0, v = 0, a = 0, n = 0;
    for (let i = 0; i < px.length; i += 4) {
      if (px[i + 3] > 40) { r += px[i]; v += px[i + 1]; a += px[i + 2]; n++; }
    }
    if (n) {
      estado.colorTela = `rgb(${Math.round(r / n)},${Math.round(v / n)},${Math.round(a / n)})`;
      // El revés de la tela, por dentro del cuello: el mismo color, en sombra
      estado.colorInterior = `rgb(${Math.round(r / n * 0.5)},${Math.round(v / n * 0.5)},${Math.round(a / n * 0.5)})`;
    }
  }

  // La curva del escote: va de un costado del cuello al otro y pasa por el punto más bajo
  function curvaEscote(c, dst) {
    const l = dst.collar_tip_l, r = dst.collar_tip_r, v = dst.neck_v;
    const dx = (v[0] - (l[0] + r[0]) / 2) * 4 / 3, dy = (v[1] - (l[1] + r[1]) / 2) * 4 / 3;
    c.moveTo(l[0], l[1]);
    c.bezierCurveTo(l[0] + dx, l[1] + dy, r[0] + dx, r[1] + dy, r[0], r[1]);
  }

  // La zona del cuello: del escote hacia arriba, hasta el borde de la imagen
  function zonaDelCuello(c, dst, g) {
    const m = g.distSh * 0.04;
    curvaEscote(c, dst);
    c.lineTo(dst.collar_tip_r[0] + m, 0);
    c.lineTo(dst.collar_tip_l[0] - m, 0);
    c.closePath();
  }

  // Abre el escote en la tela y le da el borde de un cuello tejido
  function abrirEscote(ctx, dst, g) {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath();
    zonaDelCuello(ctx, dst, g);
    ctx.fill();
    ctx.globalCompositeOperation = "source-atop";
    ctx.lineCap = "round";
    ctx.beginPath();
    curvaEscote(ctx, dst);
    ctx.strokeStyle = "rgba(0,0,0,0.30)";
    ctx.lineWidth = g.distSh * 0.05;
    ctx.stroke();
    ctx.translate(g.uDown[0] * g.distSh * 0.032, g.uDown[1] * g.distSh * 0.032);
    ctx.beginPath();
    curvaEscote(ctx, dst);
    ctx.strokeStyle = "rgba(255,255,255,0.10)";
    ctx.lineWidth = g.distSh * 0.012;
    ctx.stroke();
    ctx.restore();
  }

  // La parte de atrás de la prenda, vista por dentro del escote: el revés de la tela, en sombra,
  // hasta el borde de atrás del cuello (más alto que el de adelante). Después se recortan el
  // cuello, el pelo y la cara, que quedan por delante.
  function cuelloDeAtras(ctx, dst, g) {
    const l = dst.collar_tip_l, r = dst.collar_tip_r, v = dst.neck_v;
    const sube = g.distSh * 0.08;
    const cx = (l[0] + r[0]) / 2 + g.uUp[0] * sube, cy = (l[1] + r[1]) / 2 + g.uUp[1] * sube;
    const dx = (v[0] - (l[0] + r[0]) / 2) * 4 / 3, dy = (v[1] - (l[1] + r[1]) / 2) * 4 / 3;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    ctx.beginPath();
    ctx.moveTo(l[0], l[1]);
    ctx.quadraticCurveTo(cx, cy, r[0], r[1]);
    ctx.bezierCurveTo(r[0] + dx, r[1] + dy, l[0] + dx, l[1] + dy, l[0], l[1]);
    ctx.closePath();
    ctx.fillStyle = estado.colorInterior || "rgba(0,0,0,0.6)";
    ctx.fill();
    // El borde de atrás, con un poco de relieve
    ctx.beginPath();
    ctx.moveTo(l[0], l[1]);
    ctx.quadraticCurveTo(cx, cy, r[0], r[1]);
    ctx.lineWidth = g.distSh * 0.03;
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.stroke();
    ctx.restore();
  }

  // La tela no queda en el aire: fuera de la persona (pelo, piel, cara o ropa) se borra.
  // El centro del torso se conserva siempre, por si la separación tiene huecos.
  function recortarAlFondo(ctx, W, H, dx, dy, dst) {
    const w = Math.ceil(W / 2), h = Math.ceil(H / 2);
    if (persona.width !== w || persona.height !== h) { persona.width = w; persona.height = h; }
    const x = persona.getContext("2d");
    x.setTransform(1, 0, 0, 1, 0, 0);
    x.globalCompositeOperation = "copy";
    x.fillStyle = "rgba(0,0,0,0)";
    x.fillRect(0, 0, w, h);
    x.globalCompositeOperation = "source-over";
    x.setTransform(-0.5, 0, 0, 0.5, (W + dx) / 2, dy / 2);
    for (const parte of [PELO, PIEL, CARA, ROPA]) x.drawImage(capasPartes[parte], 0, 0, W, H);
    const claves = ["armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l", "hem_mid",
      "hem_r", "high_hip_r", "waist_r", "underbust_r", "armpit_r", "neck_v"];
    if (claves.every(k => dst[k])) {
      const cx = (dst.armpit_l[0] + dst.armpit_r[0]) * 0.5, cy = (dst.neck_v[1] + dst.hem_mid[1]) * 0.5;
      x.setTransform(0.5, 0, 0, 0.5, 0, 0);
      x.beginPath();
      claves.forEach((k, i) => {
        const px = cx + (dst[k][0] - cx) * 0.85, py = cy + (dst[k][1] - cy) * 0.85;
        if (i === 0) x.moveTo(px, py); else x.lineTo(px, py);
      });
      x.closePath();
      x.fillStyle = "#fff";
      x.fill();
    }
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "destination-in";
    ctx.filter = "blur(1.5px)";
    ctx.drawImage(persona, 0, 0, W, H);
    ctx.restore();
  }

  // Volumen de las mangas largas: cada tramo del brazo es un tubo, más oscuro a los costados
  function volumenMangas(ctx, g, dst) {
    const m = g.distSh * 0.17;
    // (no sobre el torso: ahí la sombra de la manga dejaba un borde recto)
    ctx.save();
    if (dst && dst.hem_mid && dst.collar_tip_l && ["armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l", "armpit_r", "underbust_r", "waist_r", "high_hip_r", "hem_r"].every(k => dst[k])) {
      ctx.beginPath();
      ctx.rect(0, 0, ctx.canvas.width, ctx.canvas.height);
      caminoTorso(ctx, dst, Math.min(dst.collar_tip_l[1], dst.collar_tip_r[1]), g.distSh * 0.05);
      ctx.clip("evenodd");
    }
    const tramos = [[g.shL, g.elL, g.visElL], [g.elL, g.wrL, g.visWrL], [g.shR, g.elR, g.visElR], [g.elR, g.wrR, g.visWrR]];
    for (const [a, b, vis] of tramos) {
      if (!a || !b || vis < 0.3) continue;
      const largoT = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (largoT < 10) continue;
      const ux = (b[0] - a[0]) / largoT, uy = (b[1] - a[1]) / largoT, nx = -uy, ny = ux;
      const gr = ctx.createLinearGradient(a[0] - nx * m, a[1] - ny * m, a[0] + nx * m, a[1] + ny * m);
      gr.addColorStop(0, "rgba(0,0,0,0)");
      gr.addColorStop(0.12, "rgba(0,0,0,0.28)");
      gr.addColorStop(0.35, "rgba(0,0,0,0.05)");
      gr.addColorStop(0.5, "rgba(255,255,255,0.05)");
      gr.addColorStop(0.65, "rgba(0,0,0,0.05)");
      gr.addColorStop(0.88, "rgba(0,0,0,0.28)");
      gr.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = gr;
      ctx.beginPath();
      ctx.moveTo(a[0] - nx * m, a[1] - ny * m);
      ctx.lineTo(b[0] - nx * m + ux * m * 0.3, b[1] - ny * m + uy * m * 0.3);
      ctx.lineTo(b[0] + nx * m + ux * m * 0.3, b[1] + ny * m + uy * m * 0.3);
      ctx.lineTo(a[0] + nx * m, a[1] + ny * m);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  // Pinta una parte de la persona del color de la tela, debajo de la tela, dentro de la zona dada
  function pintarDebajo(ctx, parte, W, H, dx, dy, zona) {
    const xp = pintura.getContext("2d");
    if (pintura.width !== W || pintura.height !== H) { pintura.width = W; pintura.height = H; }
    xp.globalCompositeOperation = "copy";
    dibujarParte(xp, parte, W, H, dx, dy);
    xp.globalCompositeOperation = "source-in";
    xp.fillStyle = estado.colorTela;
    xp.fillRect(0, 0, W, H);
    ctx.save();
    ctx.beginPath();
    zona();
    ctx.clip("evenodd");
    ctx.globalCompositeOperation = "destination-over";
    ctx.drawImage(pintura, 0, 0);
    ctx.restore();
  }

  /**
   * Va después de integrar la tela. El pelo y la cara quedan adelante; con mangas, también el
   * cuello. La ropa propia que asoma (cuello de una camisa, hombros, el espacio junto a una
   * manga larga) se pinta debajo de la tela, con su color.
   */
  function protegerPersona(ctx, capa, fuente, g, dst, tieneMangas, mangaLarga) {
    enviarCuadro(fuente, g);
    if (mangaLarga) abrirEscote(ctx, dst, g);
    const p = estado.partes;
    if (!p || performance.now() - p.cuando > MS_PARTES_VIEJAS) return;
    const W = capa.width, H = capa.height;
    const dx = p.cuello ? g.cuello[0] - p.cuello[0] : 0, dy = p.cuello ? g.cuello[1] - p.cuello[1] : 0;
    medirColorTela();
    if (mangaLarga) cuelloDeAtras(ctx, dst, g);
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "destination-out";
    dibujarParte(ctx, PELO, W, H, dx, dy);
    dibujarParte(ctx, CARA, W, H, dx, dy);
    const yEscote = dst.neck_v ? dst.neck_v[1] : g.cuello[1];
    if (tieneMangas) {
      // El cuello: sólo dentro del escote, para que la tela siga tapando el resto de la piel
      ctx.save();
      ctx.beginPath();
      zonaDelCuello(ctx, dst, g);
      ctx.clip();
      dibujarParte(ctx, PIEL, W, H, dx, dy);
      ctx.restore();

      const hasta = mangaLarga && dst.hem_mid ? dst.hem_mid[1] : (dst.armpit_l ? dst.armpit_l[1] : yEscote);
      const ancho = g.distSh * (mangaLarga ? 2.2 : 1.05);
      // Dentro del escote se ve la ropa propia tal cual, sin pintarla del color de la tela
      pintarDebajo(ctx, ROPA, W, H, dx, dy, () => {
        ctx.rect(g.cuello[0] - ancho, 0, ancho * 2, hasta);
        zonaDelCuello(ctx, dst, g);
      });
      if (mangaLarga) {
        // Manga larga: la piel de los hombros, el pecho y los brazos queda tapada por la tela.
        // Quedan a la vista el cuello (dentro del escote) y las manos.
        // (también un brazo levantado; la cabeza queda afuera)
        pintarDebajo(ctx, PIEL, W, H, dx, dy, () => {
          ctx.rect(g.cuello[0] - ancho, 0, ancho * 2, hasta);
          zonaDelCuello(ctx, dst, g);
          if (g.nariz) {
            const rc = (g.medioCara || g.distSh * 0.25) * 1.5;
            ctx.moveTo(g.nariz[0] + rc, g.nariz[1]);
            ctx.arc(g.nariz[0], g.nariz[1], rc, 0, Math.PI * 2);
          }
          for (const [mu, co, vis] of [[g.wrL, g.elL, g.visWrL], [g.wrR, g.elR, g.visWrR]]) {
            if (!mu || vis < 0.3) continue;
            const largoAnte = Math.hypot(mu[0] - co[0], mu[1] - co[1]) || 1;
            const k = g.distSh * 0.10 / largoAnte;
            const cm = [mu[0] + (mu[0] - co[0]) * k, mu[1] + (mu[1] - co[1]) * k];
            ctx.moveTo(cm[0] + g.distSh * 0.2, cm[1]);
            ctx.arc(cm[0], cm[1], g.distSh * 0.2, 0, Math.PI * 2);
          }
        });
      }
    }
    if (!estado.liviano) recortarAlFondo(ctx, W, H, dx, dy, dst);
    ctx.restore();
  }

  /** Ignora un salto brusco de la detección (hombros que cambian de golpe en un solo cuadro). */
  function poseEstable(g) {
    const u = estado.pose;
    if (u) {
      const cambio = Math.abs(g.distSh - u.distSh) / u.distSh;
      const mover = Math.hypot(g.cuello[0] - u.cuello[0], g.cuello[1] - u.cuello[1]);
      if ((cambio > 0.30 || mover > u.distSh * 0.5) && estado.rechazos < CUADROS_DE_SALTO) {
        estado.rechazos++;
        u.cuelloReal = cuelloSuave(u);
        return u;
      }
    }
    estado.rechazos = 0;
    estado.pose = g;
    g.cuelloReal = cuelloSuave(g);
    return g;
  }

  /** El ruedo y los puños van un poco atrasados, como una tela con peso. Cambia dst. */
  function inercia(dst, g, tieneMangas) {
    const ahora = performance.now() / 1000;
    const dt = Math.min(0.05, Math.max(0.001, ahora - estado.tiempo));
    estado.tiempo = ahora;
    const limite = g.distSh * 0.07;
    const claves = ["hem_l", "hem_mid", "hem_r", "high_hip_l", "high_hip_r"];
    if (tieneMangas) claves.push("sleeve_cuff_out_l", "sleeve_cuff_in_l", "sleeve_cuff_out_r", "sleeve_cuff_in_r");
    for (const k of claves) {
      if (!dst[k]) continue;
      let r = estado.resortes.get(k);
      const [x, y] = dst[k];
      if (!r || Math.hypot(r.x - x, r.y - y) > g.distSh) { r = { x, y, vx: 0, vy: 0 }; estado.resortes.set(k, r); }
      r.vx += (RIGIDEZ_RESORTE * (x - r.x) - FRENO_RESORTE * r.vx) * dt;
      r.vy += (RIGIDEZ_RESORTE * (y - r.y) - FRENO_RESORTE * r.vy) * dt;
      r.x += r.vx * dt; r.y += r.vy * dt;
      const dx = r.x - x, dy = r.y - y, d = Math.hypot(dx, dy);
      if (d > limite) { r.x = x + dx / d * limite; r.y = y + dy / d * limite; }
      dst[k] = [r.x, r.y];
    }
  }

  // Curva de a hasta b, con una panza lateral
  function trazo(x, a, b, comba) {
    const nx = -(b[1] - a[1]), ny = b[0] - a[0], l = Math.hypot(nx, ny) || 1;
    x.moveTo(a[0], a[1]);
    x.quadraticCurveTo((a[0] + b[0]) / 2 + nx / l * comba, (a[1] + b[1]) / 2 + ny / l * comba, b[0], b[1]);
  }

  // La tela tira desde la axila, se junta en la cintura, cae por la gravedad y se arruga en el codo
  function dibujarPliegues(dst, g, mangaLarga) {
    const x = pliegues.getContext("2d");
    x.setTransform(1, 0, 0, 1, 0, 0);
    x.fillStyle = "#808080";
    x.fillRect(0, 0, pliegues.width, pliegues.height);
    const s = 0.5, d = g.distSh * s;
    const P = (k) => [dst[k][0] * s, dst[k][1] * s];
    const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const lista = [];
    for (const [lado, signo] of [["l", 1], ["r", -1]]) {
      const axila = P(`armpit_${lado}`), cintura = P(`waist_${lado}`);
      const pecho = P("chest_mid"), medio = P("torso_mid");
      const hacia = mix(axila, pecho, 0.62);
      lista.push([axila, [hacia[0], hacia[1] + d * 0.05], signo * d * 0.03, 1]);
      lista.push([mix(axila, cintura, 0.3), mix(axila, medio, 0.55), signo * d * 0.03, 0.75]);
      // (sólo cerca del costado: si cruzan el torso, parecen abdominales)
      lista.push([cintura, mix(cintura, medio, 0.22), -signo * d * 0.015, 0.5]);
    }
    for (const [t, peso] of [[0.2, 0.7], [0.42, 0.5], [0.63, 0.6], [0.82, 0.7]]) {
      const arriba = mix(P("waist_l"), P("waist_r"), t), abajo = mix(P("hem_l"), P("hem_r"), t);
      lista.push([mix(arriba, abajo, 0.45), mix(arriba, abajo, 0.98), (t - 0.5) * d * 0.06, peso]);
    }
    if (mangaLarga) {
      for (const lado of ["l", "r"]) {
        const fuera = P(`bicep_out_${lado}`), dentro = P(`bicep_in_${lado}`);
        const codo = mix(fuera, dentro, 0.5), puno = mix(P(`sleeve_cuff_out_${lado}`), P(`sleeve_cuff_in_${lado}`), 0.5);
        const eje = [(puno[0] - codo[0]) * 0.16, (puno[1] - codo[1]) * 0.16];
        const mover = (p, k) => [p[0] + eje[0] * k, p[1] + eje[1] * k];
        lista.push([mix(fuera, dentro, 0.08), mix(fuera, dentro, 0.92), d * 0.025, 1]);
        lista.push([mover(mix(fuera, dentro, 0.15), 1), mover(mix(fuera, dentro, 0.85), 1), d * 0.02, 0.65]);
        lista.push([mover(mix(fuera, dentro, 0.15), -1), mover(mix(fuera, dentro, 0.85), -1), -d * 0.02, 0.65]);
        lista.push([mix(P(`shoulder_${lado}`), P(`armpit_${lado}`), 0.25), P(`armpit_${lado}`), d * 0.02, 0.7]);
      }
    }
    x.lineWidth = Math.max(2, d * 0.045);
    x.lineCap = "round";
    const dx = Math.max(1, d * 0.045), dy = Math.max(1, d * 0.02);
    for (const [a, b, comba, peso] of lista) {
      x.strokeStyle = `rgba(200,200,200,${(peso * 0.45).toFixed(2)})`;
      x.beginPath();
      trazo(x, [a[0] + dx, a[1] + dy], [b[0] + dx, b[1] + dy], comba);
      x.stroke();
      x.strokeStyle = `rgba(40,40,40,${(peso * 0.8).toFixed(2)})`;
      x.beginPath();
      trazo(x, a, b, comba);
      x.stroke();
    }
  }

  /** Guarda la prenda recién dibujada, antes de recortarla a la silueta. */
  function guardarEntera(capa) {
    preparar(capa.width, capa.height);
    const x = entera.getContext("2d");
    x.globalCompositeOperation = "copy";
    x.drawImage(capa, 0, 0);
  }

  /**
   * La silueta de la cámara puede tener huecos sobre la ropa (sobre todo con poca luz o ropa
   * parecida al fondo). Adentro del torso, la tela se vuelve a poner: ahí no puede faltar.
   */
  function cubrirTorso(ctx, dst) {
    // Del pecho para abajo: los hombros y el cuello los decide la silueta (si no, la tela
    // queda flotando en el aire, afuera del cuerpo)
    const claves = ["armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l", "hem_mid",
      "hem_r", "high_hip_r", "waist_r", "underbust_r", "armpit_r", "neck_v"];
    if (claves.some(k => !dst[k])) return;
    const cx = (dst.armpit_l[0] + dst.armpit_r[0]) * 0.5, cy = (dst.neck_v[1] + dst.hem_mid[1]) * 0.5;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    ctx.beginPath();
    claves.forEach((k, i) => {
      const x = cx + (dst[k][0] - cx) * MARGEN_TORSO, y = cy + (dst[k][1] - cy) * MARGEN_TORSO;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.clip();
    ctx.drawImage(entera, 0, 0);
    ctx.restore();
  }

  // Umbral para el contorno: lo desenfocado que pasa de la mitad queda sólido, el resto se va
  let hayUmbral = false;
  function prepararUmbral() {
    if (hayUmbral || !document.body) return hayUmbral;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "0");
    svg.setAttribute("height", "0");
    svg.style.position = "absolute";
    svg.innerHTML = '<filter id="umbralTela" color-interpolation-filters="sRGB"><feComponentTransfer>'
      + '<feFuncA type="linear" slope="6" intercept="-2.4"/></feComponentTransfer></filter>';
    document.body.appendChild(svg);
    hayUmbral = true;
    return true;
  }

  /** Redondea el contorno de la prenda: sin las puntas de los triángulos de la malla. */
  function redondearContorno(ctx, capa, g) {
    if (!hayFiltros || estado.liviano || !prepararUmbral()) return;
    const w = Math.ceil(capa.width / 2), h = Math.ceil(capa.height / 2);
    if (redondeo.width !== w || redondeo.height !== h) { redondeo.width = w; redondeo.height = h; }
    const x = redondeo.getContext("2d");
    x.globalCompositeOperation = "copy";
    x.filter = `blur(${Math.max(2, g.distSh * 0.03).toFixed(1)}px) url(#umbralTela)`;
    x.drawImage(capa, 0, 0, w, h);
    x.filter = "none";
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(redondeo, 0, 0, capa.width, capa.height);
    ctx.restore();
  }

  /**
   * El torso es redondo: la tela se envuelve como en un cilindro. Del pecho para abajo, cada
   * franja vertical se comprime hacia los costados y se abre en el centro (el contorno queda
   * igual, cambia cómo se reparte la textura).
   */
  // El contorno del torso (sin las mangas), desde la altura y0 hasta el ruedo
  function caminoTorso(c, dst, y0, bajar) {
    const lado = ["armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l"];
    const otro = ["hem_r", "high_hip_r", "waist_r", "underbust_r", "armpit_r"];
    c.moveTo(dst.armpit_l[0], y0);
    for (const k of lado) c.lineTo(dst[k][0], dst[k][1] + (k.startsWith("hem") ? bajar : 0));
    c.lineTo(dst.hem_mid[0], dst.hem_mid[1] + bajar);
    for (const k of otro) c.lineTo(dst[k][0], dst[k][1] + (k.startsWith("hem") ? bajar : 0));
    c.lineTo(dst.armpit_r[0], y0);
    c.closePath();
  }

  function envolverTorso(ctx, capa, g, dst) {
    const claves = ["armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l", "armpit_r", "underbust_r", "waist_r", "high_hip_r", "hem_r"];
    if (!dst.neck_v || !dst.hem_mid || claves.some(k => !dst[k])) return;
    const W = capa.width, H = capa.height;
    const cx = (dst.armpit_l[0] + dst.armpit_r[0]) / 2;
    const R = Math.max(...claves.map(k => Math.abs(dst[k][0] - cx))) * 1.02;
    const y0 = Math.max(0, dst.neck_v[1] + g.distSh * 0.04);
    const y1 = Math.min(H, Math.max(dst.hem_l[1], dst.hem_r[1], dst.hem_mid[1]) + g.distSh * 0.05);
    if (R < 10 || y1 - y0 < 10) return;
    if (plano.width !== W || plano.height !== H) { plano.width = W; plano.height = H; }
    const xp = plano.getContext("2d");
    xp.globalCompositeOperation = "copy";
    xp.drawImage(capa, 0, 0);
    const k = 0.62, den = Math.sin(k * Math.PI / 2);
    const f = (u) => Math.sin(u * k * Math.PI / 2) / den;
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    // Sólo el torso: las mangas quedan como estaban
    ctx.beginPath();
    caminoTorso(ctx, dst, y0, g.distSh * 0.05);
    ctx.clip();
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillRect(cx - R, y0, 2 * R, y1 - y0);
    ctx.globalCompositeOperation = "source-over";
    const N = 28;
    for (let i = 0; i < N; i++) {
      const u0 = -1 + 2 * i / N, u1 = u0 + 2 / N;
      const s0 = cx + R * u0, s1 = cx + R * u1;
      const d0 = cx + R * f(u0), d1 = cx + R * f(u1);
      ctx.drawImage(plano, s0, y0, s1 - s0, y1 - y0, d0 - 0.4, y0, d1 - d0 + 0.8, y1 - y0);
    }
    ctx.restore();
  }

  // Luz de un cuerpo redondo sobre el torso: los costados en sombra y un brillo suave al centro
  function volumenTorso(ctx, dst, g) {
    const claves = ["armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l", "armpit_r", "underbust_r", "waist_r", "high_hip_r", "hem_r"];
    if (!dst.hem_mid || !dst.collar_tip_l || claves.some(k => !dst[k])) return;
    const cx = (dst.armpit_l[0] + dst.armpit_r[0]) / 2;
    const R = Math.max(...claves.map(k => Math.abs(dst[k][0] - cx)));
    const gr = ctx.createLinearGradient(cx - R, 0, cx + R, 0);
    gr.addColorStop(0, "rgba(0,0,0,0.26)");
    gr.addColorStop(0.2, "rgba(0,0,0,0.08)");
    gr.addColorStop(0.45, "rgba(255,255,255,0.06)");
    gr.addColorStop(0.55, "rgba(255,255,255,0.06)");
    gr.addColorStop(0.8, "rgba(0,0,0,0.08)");
    gr.addColorStop(1, "rgba(0,0,0,0.26)");
    ctx.save();
    ctx.beginPath();
    caminoTorso(ctx, dst, Math.min(dst.collar_tip_l[1], dst.collar_tip_r[1]), g.distSh * 0.05);
    ctx.clip();
    ctx.fillStyle = gr;
    ctx.fillRect(cx - R, 0, 2 * R, ctx.canvas.height);
    ctx.restore();
  }

  /** Integra la capa de la prenda (ctx/capa, ya recortada) con lo que ve la cámara. */
  function integrar(ctx, capa, fuente, g, claridad = 128, dst = null, mangaLarga = false) {
    const W = capa.width, H = capa.height;
    preparar(W, H);
    if (!estado.grano) estado.grano = crearGrano(ctx);
    // Fluidez primero: si la compu no llega, se dejan de lado los detalles más caros
    const ahora = performance.now();
    if (estado.ultimoCuadro) estado.msCuadro += (Math.min(250, ahora - estado.ultimoCuadro) - estado.msCuadro) * 0.08;
    estado.ultimoCuadro = ahora;
    estado.liviano = estado.msCuadro > MS_LENTO;
    // Tela opaca: donde la silueta de la cámara es dudosa, la prenda queda semitransparente.
    // Dibujarla sobre sí misma la vuelve sólida y deja suave sólo el borde.
    // (los pliegues de la cámara se sacaron: hacían pasar los dibujos de la ropa de abajo)
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    for (let i = 0; i < PASADAS_OPACIDAD; i++) ctx.drawImage(capa, 0, 0);
    ctx.restore();
    if (mangaLarga && dst && !estado.liviano) envolverTorso(ctx, capa, g, dst);
    redondearContorno(ctx, capa, g);
    // Los filtros pintan también fuera de la tela: al final se recorta con esta copia
    const xCopia = copia.getContext("2d");
    xCopia.globalCompositeOperation = "copy";
    xCopia.drawImage(capa, 0, 0);
    if (estado.cuadro % 2 === 0) actualizarCamara(fuente, g);
    estado.cuadro++;

    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (hayFiltros) {
      ctx.globalCompositeOperation = "soft-light";
      ctx.globalAlpha = INTENSIDAD_LUZ;
      ctx.drawImage(luz, 0, 0, W, H);
      if (dst && dst.armpit_l && dst.waist_l && dst.hem_l && dst.chest_mid && dst.torso_mid) {
        // Se trazan y se desenfocan en chico; un cuadro de atraso no se nota
        if (estado.cuadro % (estado.liviano ? 4 : 2) === 0) {
          dibujarPliegues(dst, g, mangaLarga);
          const xs = plieguesSuaves.getContext("2d");
          xs.filter = `blur(${Math.max(1.5, g.distSh * 0.028).toFixed(1)}px)`;
          xs.drawImage(pliegues, 0, 0);
          xs.filter = "none";
        }
        ctx.globalCompositeOperation = "hard-light";
        ctx.globalAlpha = INTENSIDAD_PLIEGUES * (claridad < 90 ? 1 : 0.5);   // en tela clara se notan mucho más
        ctx.drawImage(plieguesSuaves, 0, 0, W, H);
      }
    }
    if (mangaLarga) {
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = "source-atop";
      volumenMangas(ctx, g, dst);
      if (dst) volumenTorso(ctx, dst, g);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "multiply";
    ctx.fillStyle = estado.tinte;
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "overlay";
    ctx.globalAlpha = INTENSIDAD_GRANO;
    ctx.fillStyle = estado.grano;
    ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "destination-in";
    ctx.drawImage(copia, 0, 0);

    if (hayFiltros && !estado.liviano) {
      // Contorno: negro donde el desenfoque de la tela pierde fuerza, sólo sobre la tela
      const xb = borde.getContext("2d");
      xb.globalCompositeOperation = "copy";
      xb.fillStyle = "#000";
      xb.fillRect(0, 0, borde.width, borde.height);
      xb.globalCompositeOperation = "destination-out";
      xb.filter = `blur(${Math.max(2, g.distSh * 0.018)}px)`;
      xb.drawImage(copia, 0, 0, borde.width, borde.height);
      xb.filter = "none";
      ctx.globalCompositeOperation = "source-atop";
      ctx.globalAlpha = claridad < 90 ? INTENSIDAD_BORDE_OSCURA : INTENSIDAD_BORDE_CLARA;
      ctx.drawImage(borde, 0, 0, W, H);
    }
    ctx.restore();
  }

  /** Filtro para dibujar la prenda: color intenso y la suavidad de la cámara ("none" si no hay filtros). */
  function suavidad(W) {
    if (!hayFiltros) return "none";
    return estado.liviano ? `saturate(${SATURACION})` : `saturate(${SATURACION}) blur(${(0.45 * W / 1280).toFixed(2)}px)`;
  }

  return { poseEstable, inercia, guardarEntera, cubrirTorso, integrar, protegerPersona, actualizarPartes, suavidad, zonaDelCuello };
})();
