// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Integra la prenda con la cámara, para que no parezca un recorte pegado encima:
//   1. Cobertura: la tela es opaca. De la ropa de abajo no pasa ningún detalle, y el torso
//      queda cubierto aunque la silueta de la cámara falle en alguna zona.
//   2. Luz: la tela toma la luz del lugar (muy desenfocada), su brillo general y su tono.
//   3. Cámara: la prenda recibe la misma suavidad y un poco de grano de una webcam.
//   4. Bordes: la tela se oscurece hacia el contorno, donde da la vuelta al cuerpo.
// Todo se hace en el navegador: la imagen de la cámara no sale del dispositivo.
// ==========================================================

const Realismo = (() => {
  const INTENSIDAD_LUZ = 0.22;
  const PASADAS_OPACIDAD = 5;        // cada pasada acerca a 1 el alfa de la tela, sin endurecer el borde
  const MARGEN_TORSO = 0.94;         // la zona que se cubre siempre, un poco adentro del contorno
  const INTENSIDAD_GRANO = 0.05;
  const SATURACION = 1.28;           // la luz y la suavidad apagan el color: se le devuelve
  // En una tela clara, el mismo oscurecimiento del contorno se nota mucho más
  const INTENSIDAD_BORDE_OSCURA = 0.40;
  const INTENSIDAD_BORDE_CLARA = 0.16;
  const CUADROS_POR_MEDICION = 15;   // el brillo del lugar cambia lento: no hace falta medirlo siempre

  const nuevo = (w = 1, h = 1) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  const copia = nuevo(), entera = nuevo(), chica = nuevo(), luz = nuevo(), borde = nuevo();
  const medidor = nuevo(8, 8);
  const ctxMedidor = medidor.getContext("2d", { willReadFrequently: true });
  const hayFiltros = typeof ctxMedidor.filter === "string";
  const estado = { W: 0, H: 0, cuadro: 0, media: 128, tinte: "rgb(255,255,255)", exposicion: 1, grano: null };

  function preparar(W, H) {
    if (estado.W === W && estado.H === H) return;
    Object.assign(estado, { W, H });
    for (const c of [copia, entera]) { c.width = W; c.height = H; }
    chica.width = Math.ceil(W / 4); chica.height = Math.ceil(H / 4);
    luz.width = Math.ceil(W / 16); luz.height = Math.ceil(H / 16);
    borde.width = Math.ceil(W / 2); borde.height = Math.ceil(H / 2);
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
  function integrar(ctx, capa, fuente, g, claridad = 128) {
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

  return { guardarEntera, cubrirTorso, integrar, suavidad };
})();
