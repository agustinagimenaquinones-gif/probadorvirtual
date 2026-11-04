// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Integra la prenda con la cámara, para que no parezca un recorte pegado encima:
//   1. Pliegues: pasa a la tela las luces y sombras finas que la cámara ve sobre la ropa
//      de la persona (se mueven con ella). Es un filtro de paso alto: sólo pasan los
//      cambios locales, no los colores ni los dibujos grandes.
//   2. Luz: la tela toma la luz del lugar, su brillo general y su tono.
//   3. Cámara: la prenda recibe la misma suavidad y un poco de grano de una webcam.
//   4. Bordes: la tela se oscurece hacia el contorno, donde da la vuelta al cuerpo.
// Todo se hace en el navegador: la imagen de la cámara no sale del dispositivo.
// ==========================================================

const Realismo = (() => {
  const INTENSIDAD_PLIEGUES = 0.65;
  const CONTRASTE_PLIEGUES = 2.2;
  const INTENSIDAD_LUZ = 0.55;
  const INTENSIDAD_GRANO = 0.07;
  // En una tela clara, el mismo oscurecimiento del contorno se nota mucho más
  const INTENSIDAD_BORDE_OSCURA = 0.40;
  const INTENSIDAD_BORDE_CLARA = 0.16;
  const CUADROS_POR_MEDICION = 15;   // el brillo del lugar cambia lento: no hace falta medirlo siempre

  const nuevo = (w = 1, h = 1) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
  const copia = nuevo(), chica = nuevo(), pliegues = nuevo(), luz = nuevo(), borde = nuevo();
  const medidor = nuevo(8, 8);
  const ctxMedidor = medidor.getContext("2d", { willReadFrequently: true });
  const hayFiltros = typeof ctxMedidor.filter === "string";
  const estado = { W: 0, H: 0, cuadro: 0, media: 128, tinte: "rgb(255,255,255)", exposicion: 1, grano: null };

  function preparar(W, H) {
    if (estado.W === W && estado.H === H) return;
    Object.assign(estado, { W, H });
    copia.width = W; copia.height = H;
    for (const c of [chica, pliegues]) { c.width = Math.ceil(W / 4); c.height = Math.ceil(H / 4); }
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
    const escala = g.distSh / 4;

    if (hayFiltros) {
      // Paso alto: (detalle + negativo del desenfoque) / 2 da gris parejo donde no hay pliegues
      const xp = pliegues.getContext("2d");
      xp.globalAlpha = 1;
      xp.filter = `grayscale(1) blur(${Math.max(0.4, escala * 0.012)}px)`;
      xp.drawImage(chica, 0, 0);
      xp.globalAlpha = 0.5;
      xp.filter = `grayscale(1) invert(1) blur(${Math.max(2, escala * 0.11)}px)`;
      xp.drawImage(chica, 0, 0);
      xp.filter = "none";
      xp.globalAlpha = 1;
      const xl = luz.getContext("2d");
      xl.filter = "grayscale(1) blur(2px)";
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
      estado.exposicion = Math.min(1, Math.max(0.72, estado.media / 110));
      const canal = (c) => Math.round(255 * estado.exposicion * (0.70 + 0.30 * c / maximo));
      estado.tinte = `rgb(${canal(r)},${canal(v)},${canal(a)})`;
    }
  }

  /** Integra la capa de la prenda (ctx/capa, ya recortada) con lo que ve la cámara. */
  function integrar(ctx, capa, fuente, g, claridad = 128) {
    const W = capa.width, H = capa.height;
    preparar(W, H);
    if (!estado.grano) estado.grano = crearGrano(ctx);
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
      ctx.globalCompositeOperation = "hard-light";
      ctx.globalAlpha = INTENSIDAD_PLIEGUES;
      ctx.filter = `contrast(${CONTRASTE_PLIEGUES})`;
      ctx.drawImage(pliegues, 0, 0, W, H);
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

  /** Filtro para dibujar la prenda con la suavidad de la cámara ("none" si no hay filtros). */
  function suavidad(W) {
    return hayFiltros ? `blur(${(0.55 * W / 1280).toFixed(2)}px)` : "none";
  }

  return { integrar, suavidad };
})();
