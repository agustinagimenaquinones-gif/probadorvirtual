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
// Todo se hace en el navegador: la imagen de la cámara no sale del dispositivo.
// ==========================================================

const Realismo = (() => {
  const INTENSIDAD_LUZ = 0.22;
  const PASADAS_OPACIDAD = 5;        // cada pasada acerca a 1 el alfa de la tela, sin endurecer el borde
  const MARGEN_TORSO = 0.94;         // la zona que se cubre siempre, un poco adentro del contorno
  const INTENSIDAD_PLIEGUES = 0.55;
  const RIGIDEZ_RESORTE = 170, FRENO_RESORTE = 20;
  const CUADROS_DE_SALTO = 6;        // un cambio que dura más que esto es real, no un error
  const INTENSIDAD_GRANO = 0.05;
  const SATURACION = 1.28;           // la luz y la suavidad apagan el color: se le devuelve
  // En una tela clara, el mismo oscurecimiento del contorno se nota mucho más
  const INTENSIDAD_BORDE_OSCURA = 0.40;
  const INTENSIDAD_BORDE_CLARA = 0.16;
  const CUADROS_POR_MEDICION = 15;   // el brillo del lugar cambia lento: no hace falta medirlo siempre

  const nuevo = (w = 1, h = 1) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  const copia = nuevo(), entera = nuevo(), chica = nuevo(), luz = nuevo(), borde = nuevo(), pliegues = nuevo();
  const medidor = nuevo(8, 8);
  const ctxMedidor = medidor.getContext("2d", { willReadFrequently: true });
  const hayFiltros = typeof ctxMedidor.filter === "string";
  const estado = { W: 0, H: 0, cuadro: 0, media: 128, tinte: "rgb(255,255,255)", exposicion: 1, grano: null,
    pose: null, rechazos: 0, resortes: new Map(), tiempo: 0 };

  function preparar(W, H) {
    if (estado.W === W && estado.H === H) return;
    Object.assign(estado, { W, H });
    for (const c of [copia, entera]) { c.width = W; c.height = H; }
    chica.width = Math.ceil(W / 4); chica.height = Math.ceil(H / 4);
    luz.width = Math.ceil(W / 16); luz.height = Math.ceil(H / 16);
    for (const c of [borde, pliegues]) { c.width = Math.ceil(W / 2); c.height = Math.ceil(H / 2); }
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
      xl.filter = `grayscale(1) blur(${Math.max(3, escala * 0.16)}px)`;
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

  /** Ignora un salto brusco de la detección (hombros que cambian de golpe en un solo cuadro). */
  function poseEstable(g) {
    const u = estado.pose;
    if (u) {
      const cambio = Math.abs(g.distSh - u.distSh) / u.distSh;
      const mover = Math.hypot(g.cuello[0] - u.cuello[0], g.cuello[1] - u.cuello[1]);
      if ((cambio > 0.30 || mover > u.distSh * 0.5) && estado.rechazos < CUADROS_DE_SALTO) {
        estado.rechazos++;
        return u;
      }
    }
    estado.rechazos = 0;
    estado.pose = g;
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
      const axila = P(`armpit_${lado}`), cintura = P(`waist_${lado}`), cadera = P(`high_hip_${lado}`);
      const pecho = P("chest_mid"), medio = P("torso_mid");
      const hacia = mix(axila, pecho, 0.62);
      lista.push([axila, [hacia[0], hacia[1] + d * 0.05], signo * d * 0.03, 1]);
      lista.push([mix(axila, cintura, 0.3), mix(axila, medio, 0.55), signo * d * 0.03, 0.75]);
      lista.push([cintura, mix(cintura, medio, 0.5), -signo * d * 0.02, 0.85]);
      lista.push([mix(cintura, cadera, 0.45), mix(cadera, medio, 0.42), signo * d * 0.02, 0.6]);
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
    x.lineWidth = Math.max(1, d * 0.014);
    x.lineCap = "round";
    const dx = Math.max(1, d * 0.026), dy = Math.max(1, d * 0.012);
    for (const [a, b, comba, peso] of lista) {
      x.strokeStyle = `rgba(232,232,232,${(peso * 0.75).toFixed(2)})`;
      x.beginPath();
      trazo(x, [a[0] + dx, a[1] + dy], [b[0] + dx, b[1] + dy], comba);
      x.stroke();
      x.strokeStyle = `rgba(24,24,24,${peso.toFixed(2)})`;
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
    const claves = ["collar_tip_l", "shoulder_l", "armpit_l", "underbust_l", "waist_l", "high_hip_l", "hem_l", "hem_mid",
      "hem_r", "high_hip_r", "waist_r", "underbust_r", "armpit_r", "shoulder_r", "collar_tip_r", "neck_v"];
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

  /** Integra la capa de la prenda (ctx/capa, ya recortada) con lo que ve la cámara. */
  function integrar(ctx, capa, fuente, g, claridad = 128, dst = null, mangaLarga = false) {
    const W = capa.width, H = capa.height;
    preparar(W, H);
    if (!estado.grano) estado.grano = crearGrano(ctx);
    // Tela opaca: donde la silueta de la cámara es dudosa, la prenda queda semitransparente.
    // Dibujarla sobre sí misma la vuelve sólida y deja suave sólo el borde.
    // (los pliegues de la cámara se sacaron: hacían pasar los dibujos de la ropa de abajo)
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    for (let i = 0; i < PASADAS_OPACIDAD; i++) ctx.drawImage(capa, 0, 0);
    ctx.restore();
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
      ctx.filter = `brightness(${Math.min(1.8, Math.max(0.6, 128 / estado.media))})`;
      ctx.drawImage(luz, 0, 0, W, H);
      ctx.filter = "none";
      if (dst && dst.armpit_l && dst.waist_l && dst.hem_l && dst.chest_mid && dst.torso_mid) {
        dibujarPliegues(dst, g, mangaLarga);
        ctx.globalCompositeOperation = "hard-light";
        ctx.globalAlpha = INTENSIDAD_PLIEGUES;
        ctx.filter = `blur(${Math.max(0.8, g.distSh * 0.012).toFixed(1)}px)`;
        ctx.drawImage(pliegues, 0, 0, W, H);
        ctx.filter = "none";
      }
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

    if (hayFiltros) {
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
    return hayFiltros ? `saturate(${SATURACION}) blur(${(0.45 * W / 1280).toFixed(2)}px)` : "none";
  }

  return { poseEstable, inercia, guardarEntera, cubrirTorso, integrar, suavidad };
})();
