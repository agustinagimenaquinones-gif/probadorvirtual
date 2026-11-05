// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Malla de la prenda: la misma geometría del probador de escritorio (pose_tracker.py
// y clothing_geometry.py) pasada a JavaScript.
//   1. geometriaCorporal(): hombros, torso, brazos y cuello a partir de MediaPipe.
//   2. puntosDestino(): dónde va cada uno de los 23 puntos de la prenda en la cámara.
//   3. dibujarMalla(): deforma la foto de la prenda triángulo por triángulo.
// ==========================================================

const Malla = (() => {
  const TRIANGULOS_TORSO = [
    ["collar_top_mid", "collar_top_l", "collar_tip_l"], ["collar_top_mid", "collar_top_r", "collar_tip_r"],
    ["collar_top_mid", "collar_tip_l", "neck_v"], ["collar_top_mid", "collar_tip_r", "neck_v"],
    ["collar_top_l", "shoulder_l", "collar_tip_l"], ["collar_top_r", "shoulder_r", "collar_tip_r"],
    ["collar_tip_l", "shoulder_l", "chest_mid"], ["collar_tip_r", "shoulder_r", "chest_mid"],
    ["collar_tip_l", "neck_v", "chest_mid"], ["collar_tip_r", "neck_v", "chest_mid"],
    ["shoulder_l", "armpit_l", "chest_mid"], ["shoulder_r", "armpit_r", "chest_mid"],
    ["armpit_l", "underbust_l", "chest_mid"], ["armpit_r", "underbust_r", "chest_mid"],
    ["underbust_l", "waist_l", "chest_mid"], ["underbust_r", "waist_r", "chest_mid"],
    ["chest_mid", "waist_l", "torso_mid"], ["chest_mid", "waist_r", "torso_mid"],
    ["waist_l", "high_hip_l", "torso_mid"], ["waist_r", "high_hip_r", "torso_mid"],
    ["high_hip_l", "hem_l", "torso_mid"], ["high_hip_r", "hem_r", "torso_mid"],
    ["torso_mid", "hem_l", "hem_mid"], ["torso_mid", "hem_r", "hem_mid"],
  ];
  const TRIANGULOS_MANGAS = [
    ["shoulder_l", "sleeve_top_l", "bicep_out_l"], ["shoulder_l", "bicep_out_l", "bicep_in_l"],
    ["shoulder_l", "bicep_in_l", "armpit_l"], ["bicep_out_l", "sleeve_cuff_out_l", "bicep_in_l"],
    ["bicep_in_l", "sleeve_cuff_out_l", "sleeve_cuff_in_l"],
    ["shoulder_r", "sleeve_top_r", "bicep_out_r"], ["shoulder_r", "bicep_out_r", "bicep_in_r"],
    ["shoulder_r", "bicep_in_r", "armpit_r"], ["bicep_out_r", "sleeve_cuff_out_r", "bicep_in_r"],
    ["bicep_in_r", "sleeve_cuff_out_r", "sleeve_cuff_in_r"],
  ];
  const HOLGURA_TALLES = { XS: 0.95, S: 1.00, M: 1.05, L: 1.11, XL: 1.18, XXL: 1.25 };
  const CONFIANZA_CADERAS = 0.5;
  const INCLINACION_MAXIMA_TORSO = 20 * Math.PI / 180;

  // ---- vectores 2D
  const sum = (a, b) => [a[0] + b[0], a[1] + b[1]];
  const res = (a, b) => [a[0] - b[0], a[1] - b[1]];
  const por = (a, k) => [a[0] * k, a[1] * k];
  const pto = (a, b) => a[0] * b[0] + a[1] * b[1];
  const largo = (a) => Math.hypot(a[0], a[1]);
  const unit = (a) => { const l = largo(a) || 1; return [a[0] / l, a[1] / l]; };
  const clip = (v, a, b) => Math.min(b, Math.max(a, v));
  /** suma de varios términos */
  const S = (...v) => v.reduce(sum, [0, 0]);

  /**
   * pts: puntos en píxeles de la imagen ESPEJADA {sh_left, sh_right, elb_*, wri_*, hip_*,
   * nose, ear_*, mouth_*}; vis: visibilidad de cada uno (0 a 1).
   */
  function geometriaCorporal(pts, vis, ancho, alto) {
    let [shL, shR, elL, elR, wrL, wrR, hiL, hiR] =
      [pts.sh_left, pts.sh_right, pts.elb_left, pts.elb_right, pts.wri_left, pts.wri_right, pts.hip_left, pts.hip_right];
    let visElL = vis.elb_left, visElR = vis.elb_right, visWrL = vis.wri_left, visWrR = vis.wri_right;
    // El hombro de la izquierda de la pantalla es el de menor X
    if (shR[0] <= shL[0]) {
      [shL, shR, elL, elR, wrL, wrR, hiL, hiR] = [shR, shL, elR, elL, wrR, wrL, hiR, hiL];
      [visElL, visElR, visWrL, visWrR] = [visElR, visElL, visWrR, visWrL];
    }
    const vSh = res(shR, shL);
    const distSh = Math.max(15, largo(vSh));
    const uSh = por(vSh, 1 / distSh);
    let uUp = [uSh[1], -uSh[0]];
    if (uUp[1] > 0) uUp = por(uUp, -1);
    const uDown = por(uUp, -1);
    const cuello = por(sum(shL, shR), 0.5);

    // Caderas: sólo si se ven con confianza y dentro del cuadro (si no, se estiman)
    let hipMid = por(sum(hiL, hiR), 0.5);
    const vTorso = res(hipMid, cuello);
    let distTorso = largo(vTorso);
    const enCuadro = [hiL, hiR].every(p => p[0] >= -ancho * 0.05 && p[0] <= ancho * 1.05 && p[1] <= alto * 1.02);
    let uTorso;
    let caderasVisibles = true;
    if (distTorso < 25 || vTorso[1] <= 0 || !enCuadro || vis.hip_left < CONFIANZA_CADERAS || vis.hip_right < CONFIANZA_CADERAS) {
      caderasVisibles = false;
      distTorso = distSh * 1.35;
      uTorso = uDown;
    } else {
      uTorso = por(vTorso, 1 / distTorso);
      const angulo = Math.atan2(uDown[0] * uTorso[1] - uDown[1] * uTorso[0], pto(uDown, uTorso));
      if (Math.abs(angulo) > INCLINACION_MAXIMA_TORSO) {
        const a = Math.sign(angulo) * INCLINACION_MAXIMA_TORSO;
        uTorso = [Math.cos(a) * uDown[0] - Math.sin(a) * uDown[1], Math.sin(a) * uDown[0] + Math.cos(a) * uDown[1]];
      }
    }

    function brazo(sh, el, visEl, lado) {
      const v = res(el, sh);
      const d = largo(v);
      return d > 15 && visEl > 0.25 ? por(v, 1 / d) : unit(S(por(uSh, 0.35 * lado), por(uDown, 0.94)));
    }
    const uArmL = brazo(shL, elL, visElL, -1);
    const uArmR = brazo(shR, elR, visElR, 1);
    let uCuffL = [uArmL[1], -uArmL[0]];
    if (pto(uCuffL, uSh) < 0) uCuffL = por(uCuffL, -1);
    let uCuffR = [uArmR[1], -uArmR[0]];
    if (pto(uCuffR, uSh) > 0) uCuffR = por(uCuffR, -1);

    let uHip = uSh;
    const vHip = res(hiR, hiL);
    if (caderasVisibles && largo(vHip) > distSh * 0.25) {
      uHip = unit(vHip);
      if (pto(uHip, uSh) < 0) uHip = por(uHip, -1);
    }

    const elevacion = (sh, el) => clip(pto(res(el, sh), uUp) / (distSh * 0.45) + 0.15, 0, 1);
    let medioCuello = distSh * 0.20, medioCara = null, menton = null;
    if (pts.ear_left && pts.ear_right) {
      const dOrejas = largo(res(pts.ear_left, pts.ear_right));
      medioCuello = clip(dOrejas * 0.36, distSh * 0.13, distSh * 0.30);
      medioCara = dOrejas * 0.58;
    }
    if (pts.mouth_left && pts.mouth_right && pts.nose) {
      const boca = por(sum(pts.mouth_left, pts.mouth_right), 0.5);
      menton = sum(boca, por(res(boca, pts.nose), 1.7));
    }
    return {
      shL, shR, elL, elR, wrL, wrR, visElL, visElR, visWrL, visWrR, cuello, distSh, distTorso, uSh, uUp, uDown, uTorso, uHip,
      uArmL, uArmR, uCuffL, uCuffR, caderasVisibles, medioCuello, medioCara, menton, nariz: pts.nose,
      brazoArribaL: elevacion(shL, elL), brazoArribaR: elevacion(shR, elR),
    };
  }

  // Prendas sin mangas: UNA sola transformación que respeta su forma (tiras, escote)
  function parteAltaComoLaPrenda(dst, src, uLat, uTorso) {
    if (!src.armpit_l || !src.armpit_r || !src.hem_mid) return;
    const anchoSrc = Math.abs(src.armpit_r[0] - src.armpit_l[0]);
    const yAxilas = (src.armpit_l[1] + src.armpit_r[1]) * 0.5;
    // Lo que cae más abajo del ruedo (un pañuelo) no cuenta para el largo
    const largoSrc = (src.ruedo_cuerpo || src.hem_mid)[1] - yAxilas;
    const axilas = por(sum(dst.armpit_l, dst.armpit_r), 0.5);
    const anchoDst = largo(res(dst.armpit_r, dst.armpit_l));
    const largoDst = pto(res(dst.hem_mid, axilas), uTorso);
    if (anchoSrc < 1 || largoSrc < 1 || largoDst < 1) return;
    const ex = anchoDst / anchoSrc, ey = largoDst / largoSrc;
    const cx = (src.armpit_l[0] + src.armpit_r[0]) * 0.5;
    for (const [k, [x, y]] of Object.entries(src)) {
      if (dst[k]) dst[k] = S(axilas, por(uLat, (x - cx) * ex), por(uTorso, (y - yAxilas) * ey));
    }
  }

  // Manga larga: el puño cae bastante más abajo que la mitad entre el hombro y el ruedo
  function esMangaLarga(src) {
    if (!src || !src.shoulder_l || !src.sleeve_cuff_out_l || !src.hem_mid) return false;
    return src.sleeve_cuff_out_l[1] - src.shoulder_l[1] > (src.hem_mid[1] - src.shoulder_l[1]) * 0.60;
  }

  // La manga sigue al brazo hasta la muñeca y se dobla en el codo
  function mangasHastaLaMuneca(dst, g, holgura) {
    const radio = g.distSh * 0.11 * 1.25 * holgura / 1.05;
    for (const [lado, sh, el, wr, uCuff] of [["l", g.shL, g.elL, g.wrL, g.uCuffL], ["r", g.shR, g.elR, g.wrR, g.uCuffR]]) {
      const ante = res(wr, el);
      let nAnte = unit([ante[1], -ante[0]]);
      if (pto(nAnte, uCuff) < 0) nAnte = por(nAnte, -1);
      const nCodo = unit(sum(uCuff, nAnte));
      dst[`shoulder_${lado}`] = S(sh, por(g.uUp, g.distSh * 0.11), por(uCuff, -g.distSh * 0.03));
      dst[`sleeve_top_${lado}`] = S(sh, por(res(el, sh), 0.12), por(uCuff, -radio * 1.25));
      dst[`bicep_out_${lado}`] = sum(el, por(nCodo, -radio));
      // Hacia el cuerpo, la manga se pasa: es mejor que se superponga a que quede un hueco
      dst[`bicep_in_${lado}`] = sum(el, por(nCodo, radio * 1.6));
      dst[`sleeve_cuff_out_${lado}`] = sum(wr, por(nAnte, -radio * 0.8));
      dst[`sleeve_cuff_in_${lado}`] = sum(wr, por(nAnte, radio));
    }
  }

  // Buzo con el cuello abierto en la foto: el hueco abraza el cuello de la persona. A los costados
  // sube hasta la base del cuello, adelante baja apenas y los hombros caen desde ahí, como en una
  // prenda puesta. El resto (una capucha, el borde de adelante) conserva su forma.
  function cuelloAbierto(dst, src, g, anchoCuello, alturaCuello) {
    const anchoSrc = Math.abs(src.armpit_r[0] - src.armpit_l[0]);
    if (anchoSrc < 1) return;
    const escala = largo(res(dst.armpit_r, dst.armpit_l)) / anchoSrc;
    const yPuntas = (src.collar_tip_l[1] + src.collar_tip_r[1]) * 0.5;
    const base = sum(g.cuello, por(g.uUp, g.distSh * 0.14));
    for (const [lado, signo] of [["l", -1], ["r", 1]]) {
      const punta = sum(base, por(g.uSh, signo * anchoCuello * 1.05));
      dst[`collar_tip_${lado}`] = punta;
      // (acotado: si no, una capucha abierta forma puntas que salen de los hombros)
      const dx = Math.min(anchoCuello * 0.7, Math.abs(src[`collar_top_${lado}`][0] - src[`collar_tip_${lado}`][0]) * escala);
      const dy = Math.min(alturaCuello * 0.6, (src[`collar_tip_${lado}`][1] - src[`collar_top_${lado}`][1]) * escala);
      dst[`collar_top_${lado}`] = S(punta, por(g.uSh, signo * dx), por(g.uUp, dy));
      // (la tela llega hasta arriba del hombro: si no, se ve la piel entre el hombro y el cuello)
      dst[`shoulder_${lado}`] = sum(dst[`shoulder_${lado}`], por(g.uUp, g.distSh * 0.02));
    }
    // Adelante el cuello redondo queda alto, en la base del cuello (no deja ver la ropa de abajo)
    const bajada = clip((src.neck_v[1] - yPuntas) * escala, g.distSh * 0.09, g.distSh * 0.13);
    dst.neck_v = sum(base, por(g.uUp, -bajada));
    dst.collar_top_mid = sum(base, por(g.uUp, (yPuntas - src.collar_top_mid[1]) * escala));
  }

  // Top halter: arriba, la tela es mucho más angosta que el pecho (una tira que rodea el cuello)
  function esCuelloHalter(src) {
    if (!src.collar_top_l || !src.collar_top_r || !src.armpit_l || !src.armpit_r) return false;
    const pecho = Math.abs(src.armpit_r[0] - src.armpit_l[0]);
    return pecho > 1 && Math.abs(src.collar_top_r[0] - src.collar_top_l[0]) / pecho < 0.60;
  }

  // La tira toma el ancho y la posición del cuello, y esa corrección se apaga hasta la axila:
  // la tela sigue siendo una sola. Llega hasta poco antes del mentón.
  function anclarCuelloHalter(dst, src, g, uLat, anchoCuello, alturaCuello) {
    const yArriba = src.collar_top_mid[1];
    const yAxila = (src.armpit_l[1] + src.armpit_r[1]) * 0.5;
    const medioSrc = Math.abs(src.collar_top_r[0] - src.collar_top_l[0]) * 0.5;
    const anchoSrc = Math.abs(src.armpit_r[0] - src.armpit_l[0]);
    if (yAxila - yArriba < 1 || medioSrc < 1 || anchoSrc < 1) return;
    const escalaTorso = largo(res(dst.armpit_r, dst.armpit_l)) / anchoSrc;
    const escalaCuello = anchoCuello / medioSrc;
    const menton = g.menton || (g.nariz ? sum(g.nariz, por(res(g.cuello, g.nariz), 0.55)) : null);
    const hastaMenton = menton ? pto(res(menton, g.cuello), g.uUp) : alturaCuello * 1.35;
    const destino = sum(g.cuello, por(g.uUp, Math.min(alturaCuello * 1.35, Math.max(alturaCuello * 0.5, hastaMenton * 0.92))));
    const corrimiento = res(destino, dst.collar_top_mid);
    for (const k of ["collar_top_mid", "collar_top_l", "collar_top_r", "collar_tip_l", "collar_tip_r", "neck_v",
      "shoulder_l", "shoulder_r", "chest_mid"]) {
      if (!src[k] || !dst[k]) continue;
      let t = clip((yAxila - src[k][1]) / (yAxila - yArriba), 0, 1);
      t = t * t * (3 - 2 * t);
      dst[k] = S(dst[k], por(corrimiento, t), por(uLat, (src[k][0] - src.collar_top_mid[0]) * (escalaCuello - escalaTorso) * t));
    }
  }

  // Altura de cada medición (0 = base del cuello, 1 = caderas) y límites del medio ancho,
  // en relación con los hombros: lo que se sale del rango es ruido de la silueta
  const NIVELES_MEDICION = {
    pecho: [0.30, 0.28, 0.72], bajoBusto: [0.46, 0.24, 0.74], cintura: [0.62, 0.22, 0.80],
    caderaAlta: [0.82, 0.24, 0.90], cadera: [1.00, 0.26, 0.95],
  };

  function distanciaASegmento(p, a, b) {
    const ab = res(b, a), l2 = pto(ab, ab);
    if (l2 < 1e-6) return largo(res(p, a));
    const t = clip(pto(res(p, a), ab) / l2, 0, 1);
    return largo(res(p, sum(a, por(ab, t))));
  }

  // Camina desde el centro hasta salir de la silueta o tocar un brazo: con los brazos al
  // costado la silueta une brazo y torso, y si no se mediría "torso + brazo"
  function escanearBorde(mascara, escala, origen, dir, largoMax, brazos, radioBrazo) {
    const paso = Math.max(1.5, largoMax / 120);
    let fuera = 0;
    for (let t = 0; t < largoMax; t += paso) {
      const p = sum(origen, por(dir, t));
      // La silueta está sin espejar y los puntos, espejados
      const x = mascara.ancho - 1 - Math.round(p[0] * escala[0]), y = Math.round(p[1] * escala[1]);
      const adentro = x >= 0 && x < mascara.ancho && y >= 0 && y < mascara.alto
        && mascara.valores[y * mascara.ancho + x] > 0.5
        && !brazos.some(([a, b]) => distanciaASegmento(p, a, b) < radioBrazo);
      if (adentro) { fuera = 0; continue; }
      if (t === 0) return null;  // el centro del torso no está en la silueta
      if (++fuera >= 2) return t - paso;
    }
    return null;  // no se encontró el borde: la medida no es confiable
  }

  /**
   * Tramos de los brazos que se pueden usar. Se descarta lo que MediaPipe no ve bien y lo que
   * cae sobre el centro del torso: ahí un punto mal ubicado borraría la tela del pecho.
   * (Por eso, con los brazos cruzados, en la web la tela queda por delante.)
   */
  function tramosDeBrazos(g) {
    const lat = latDelTorso(g);
    const afuera = (p) => Math.abs(pto(res(p, g.cuello), lat)) >= g.distSh * 0.38;
    const tramos = [];
    for (const [sh, el, wr, visEl, visWr] of [[g.shL, g.elL, g.wrL, g.visElL, g.visWrL], [g.shR, g.elR, g.wrR, g.visElR, g.visWrR]]) {
      if (visEl < 0.5 || !afuera(el)) continue;
      tramos.push([sh, el]);
      if (visWr >= 0.5 && afuera(wr)) tramos.push([el, wr]);
    }
    return tramos;
  }

  /** Medios anchos del cuerpo (izquierda y derecha de la pantalla) según la silueta de MediaPipe. */
  function medirSilueta(g, mascara, W, H) {
    const escala = [mascara.ancho / W, mascara.alto / H];
    const lat = latDelTorso(g);
    const brazos = tramosDeBrazos(g);
    const medidas = {};
    for (const [nombre, [f, min, max]] of Object.entries(NIVELES_MEDICION)) {
      if (nombre === "cadera" && !g.caderasVisibles) continue;
      const centro = sum(g.cuello, por(g.uTorso, g.distTorso * f));
      medidas[nombre] = [-1, 1].map((lado) => {
        const d = escanearBorde(mascara, escala, centro, por(lat, lado), g.distSh * 1.3, brazos, g.distSh * 0.09);
        return d === null ? null : clip(d, min * g.distSh, max * g.distSh);
      });
    }
    return medidas;
  }

  const latDelTorso = (g) => {
    const lat = [-g.uTorso[1], g.uTorso[0]];
    return pto(lat, g.uSh) < 0 ? por(lat, -1) : lat;
  };

  // De las medidas del cuerpo a los medios anchos de la prenda, según el talle y el calce
  function mediosDesdeSilueta(medidas, holgura, calce, distSh) {
    const r = { pecho: [0, 0], bajoBusto: [0, 0], cintura: [0, 0], caderaAlta: [0, 0], ruedo: [0, 0] };
    const de = (nombre, i) => {
      const par = medidas[nombre];
      return par ? (par[i] ?? par[1 - i]) : null;
    };
    for (const i of [0, 1]) {
      const pecho = de("pecho", i) ?? distSh * 0.44;
      const cintura = de("cintura", i) ?? pecho * 0.92;
      const cadera = de("cadera", i);
      let cinturaPrenda = cintura, holguraPecho = holgura;
      if (calce === "holgado") {
        cinturaPrenda = Math.max(cintura, pecho, (cadera ?? 0) * 0.98);
        holguraPecho = holgura * 1.04;
      } else if (calce === "regular") {
        cinturaPrenda = Math.max(cintura, 0.5 * (pecho + (cadera ?? pecho)) * 0.93);
      }
      const baseRuedo = Math.max(cinturaPrenda, cadera ?? cinturaPrenda * 1.04);
      const bajoBusto = de("bajoBusto", i) ?? 0.5 * (pecho + cintura);
      const caderaAlta = de("caderaAlta", i) ?? 0.5 * (cintura + (cadera ?? cintura));
      r.pecho[i] = pecho * holguraPecho;
      r.cintura[i] = cinturaPrenda * holgura;
      r.ruedo[i] = baseRuedo * holgura * 1.03;
      if (calce === "entallado") {
        r.bajoBusto[i] = bajoBusto * holgura;
        r.caderaAlta[i] = Math.min(Math.max(caderaAlta, cinturaPrenda) * holgura, r.ruedo[i]);
      } else {
        r.bajoBusto[i] = Math.max(bajoBusto, 0.5 * (pecho * holguraPecho / holgura + cinturaPrenda)) * holgura;
        r.caderaAlta[i] = Math.min(Math.max(caderaAlta, 0.5 * (cinturaPrenda + baseRuedo)) * holgura, r.ruedo[i]);
      }
    }
    return r;
  }

  // El cuello de la prenda abraza el cuello y conserva su forma (redondo, en V, chomba)
  function escoteComoLaPrenda(dst, src, cuello, uSh, uTorso, anchoCuello, alturaCuello, dTorso) {
    const claves = ["shoulder_l", "shoulder_r", "collar_top_l", "collar_top_r", "collar_tip_l", "collar_tip_r", "neck_v"];
    if (claves.some(k => !src[k])) return;
    const anchoSrc = Math.abs(src.shoulder_r[0] - src.shoulder_l[0]);
    const anchoDst = largo(res(dst.shoulder_r, dst.shoulder_l));
    const anchoCuelloSrc = Math.abs(src.collar_top_r[0] - src.collar_top_l[0]);
    if (anchoSrc < 1 || anchoCuelloSrc < 1) return;
    const escala = anchoDst / anchoSrc;
    const ex = clip(2 * anchoCuello / anchoCuelloSrc, escala * 0.6, escala * 1.6);
    const cx = (src.collar_top_l[0] + src.collar_top_r[0]) * 0.5;
    const yCuello = (src.collar_top_l[1] + src.collar_top_r[1]) * 0.5;
    const baseY = alturaCuello * 0.90;
    const ubicar = (k, min, max) => S(cuello, por(uSh, (src[k][0] - cx) * ex),
      por(uTorso, clip((src[k][1] - yCuello) * escala - baseY, min, max)));
    dst.collar_tip_l = ubicar("collar_tip_l", -alturaCuello * 0.6, dTorso * 0.30);
    dst.collar_tip_r = ubicar("collar_tip_r", -alturaCuello * 0.6, dTorso * 0.30);
    dst.neck_v = ubicar("neck_v", dTorso * 0.03, dTorso * 0.40);
  }

  function puntosDestino(g, prenda, talle, ajuste = 1.0) {
    const holguraTalle = HOLGURA_TALLES[talle] || 1.05;
    const holgura = holguraTalle * ajuste;
    const largoTalle = 1 + (holguraTalle - 1.05) * 0.6;
    const dSh = g.distSh * ajuste;
    const dTorso = g.distTorso * ajuste * largoTalle;
    const calce = prenda.calce || "regular";
    const extraCalce = calce === "holgado" ? 1.08 : calce === "entallado" ? 0.94 : 1.0;
    let uLat = [-g.uTorso[1], g.uTorso[0]];
    if (pto(uLat, g.uSh) < 0) uLat = por(uLat, -1);

    const anchoCuello = clip(g.medioCuello * 1.10, g.distSh * 0.12, g.distSh * 0.32);
    const alturaCuello = g.distSh * 0.20;
    const largoManga = dSh * 0.52;
    const anchoManga = dSh * 0.26 * holgura / 1.05;
    const salidaManga = dSh * 0.08;
    const k = holgura / 1.05 * extraCalce;
    const ambos = (v) => [v, v];
    let medio = { pecho: ambos(dSh * 0.56 * Math.max(1, extraCalce)), cintura: ambos(dSh * 0.44 * k), ruedo: ambos(dSh * 0.449 * k) };
    medio.bajoBusto = ambos((medio.pecho[0] + medio.cintura[0]) / 2);
    medio.caderaAlta = ambos((medio.cintura[0] + medio.ruedo[0]) / 2);
    let hombroExtra = dSh * 0.10;
    if (g.medidas && g.medidas.pecho) {
      medio = mediosDesdeSilueta(g.medidas, holgura, calce, g.distSh);
      hombroExtra = g.distSh * (0.10 + (holgura - 1.05) * 0.5);
    }
    if (!prenda.tiene_mangas) {
      // Sin mangas se ve todo el contorno: se redondean las esquinas entre niveles
      const orden = ["pecho", "bajoBusto", "cintura", "caderaAlta", "ruedo"];
      const previo = orden.map(n => medio[n].slice());
      for (let n = 1; n < orden.length - 1; n++) {
        for (const i of [0, 1]) medio[orden[n]][i] = 0.25 * previo[n - 1][i] + 0.5 * previo[n][i] + 0.25 * previo[n + 1][i];
      }
    }
    const subeRuedo = Math.max(g.brazoArribaL, g.brazoArribaR) * dTorso * 0.05;
    const lateral = (m) => unit(S(por(uLat, 1 - m), por(g.uHip, m)));
    const nivel = (f) => sum(g.cuello, por(g.uTorso, dTorso * f));
    const { shL, shR, uSh, uUp, uTorso, uArmL, uArmR, uCuffL, uCuffR, cuello } = g;

    const dst = {
      collar_top_mid: sum(cuello, por(uUp, alturaCuello * 1.10)),
      collar_top_l: S(cuello, por(uSh, -anchoCuello), por(uUp, alturaCuello * 0.90)),
      collar_top_r: S(cuello, por(uSh, anchoCuello), por(uUp, alturaCuello * 0.90)),
      collar_tip_l: S(cuello, por(uSh, -anchoCuello * 0.65), por(uUp, -alturaCuello * 0.25)),
      collar_tip_r: S(cuello, por(uSh, anchoCuello * 0.65), por(uUp, -alturaCuello * 0.25)),
      neck_v: sum(cuello, por(uTorso, g.distTorso * 0.18)),
      shoulder_l: S(shL, por(uSh, -hombroExtra), por(uUp, g.distSh * 0.09)),
      shoulder_r: S(shR, por(uSh, hombroExtra), por(uUp, g.distSh * 0.09)),
      sleeve_top_l: S(shL, por(uSh, -hombroExtra * 2), por(uArmL, largoManga * 0.45)),
      sleeve_top_r: S(shR, por(uSh, hombroExtra * 2), por(uArmR, largoManga * 0.45)),
      sleeve_cuff_out_l: S(shL, por(uArmL, largoManga), por(uCuffL, -salidaManga)),
      sleeve_cuff_out_r: S(shR, por(uArmR, largoManga), por(uCuffR, -salidaManga)),
      sleeve_cuff_in_l: S(shL, por(uArmL, largoManga * 0.95), por(uCuffL, anchoManga)),
      sleeve_cuff_in_r: S(shR, por(uArmR, largoManga * 0.95), por(uCuffR, anchoManga)),
      bicep_out_l: S(shL, por(uArmL, largoManga * 0.62), por(uCuffL, -salidaManga * 1.05)),
      bicep_out_r: S(shR, por(uArmR, largoManga * 0.62), por(uCuffR, -salidaManga * 1.05)),
      bicep_in_l: S(shL, por(uArmL, largoManga * 0.60), por(uCuffL, anchoManga * 1.05)),
      bicep_in_r: S(shR, por(uArmR, largoManga * 0.60), por(uCuffR, anchoManga * 1.05)),
      armpit_l: S(nivel(0.33), por(uLat, -medio.pecho[0]), por(uUp, g.brazoArribaL * dTorso * 0.10)),
      armpit_r: S(nivel(0.33), por(uLat, medio.pecho[1]), por(uUp, g.brazoArribaR * dTorso * 0.10)),
      chest_mid: nivel(0.36),
      torso_mid: nivel(0.68),
      underbust_l: S(nivel(0.50), por(lateral(0.2), -medio.bajoBusto[0]), por(uUp, g.brazoArribaL * dTorso * 0.04)),
      underbust_r: S(nivel(0.50), por(lateral(0.2), medio.bajoBusto[1]), por(uUp, g.brazoArribaR * dTorso * 0.04)),
      waist_l: sum(nivel(0.68), por(lateral(0.5), -medio.cintura[0])),
      waist_r: sum(nivel(0.68), por(lateral(0.5), medio.cintura[1])),
      high_hip_l: S(nivel(0.86), por(lateral(0.8), -medio.caderaAlta[0]), por(uTorso, -subeRuedo * 0.6)),
      high_hip_r: S(nivel(0.86), por(lateral(0.8), medio.caderaAlta[1]), por(uTorso, -subeRuedo * 0.6)),
      hem_l: S(nivel(1.05), por(lateral(1), -medio.ruedo[0]), por(uTorso, -subeRuedo)),
      hem_mid: sum(nivel(1.06), por(uTorso, -subeRuedo)),
      hem_r: S(nivel(1.05), por(lateral(1), medio.ruedo[1]), por(uTorso, -subeRuedo)),
    };
    if (!prenda.tiene_mangas) {
      // La prenda se ubica entera, pero sus costados siguen en el ancho medido del cuerpo
      const costados = ["underbust", "waist", "high_hip", "hem"].flatMap(n => [`${n}_l`, `${n}_r`]);
      const medidos = Object.fromEntries(costados.map(k => [k, dst[k]]));
      parteAltaComoLaPrenda(dst, prenda.puntos, uLat, uTorso);
      const axilas = por(sum(dst.armpit_l, dst.armpit_r), 0.5);
      for (const k of costados) {
        dst[k] = S(axilas, por(uTorso, pto(res(dst[k], axilas), uTorso)), por(uLat, pto(res(medidos[k], axilas), uLat)));
      }
      if (esCuelloHalter(prenda.puntos)) anclarCuelloHalter(dst, prenda.puntos, g, uLat, anchoCuello, alturaCuello);
      for (const lado of ["l", "r"]) {
        dst[`sleeve_top_${lado}`] = dst[`shoulder_${lado}`];
        for (const k of ["sleeve_cuff_out", "sleeve_cuff_in", "bicep_out", "bicep_in"]) dst[`${k}_${lado}`] = dst[`armpit_${lado}`];
      }
    } else {
      escoteComoLaPrenda(dst, prenda.puntos, cuello, uSh, uTorso, anchoCuello, alturaCuello, g.distTorso);
      if (esMangaLarga(prenda.puntos)) {
        mangasHastaLaMuneca(dst, g, holgura);
        cuelloAbierto(dst, prenda.puntos, g, anchoCuello, alturaCuello);
        // El puño del ruedo junta la tela abajo: el cuerpo queda suelto y cae sobre él
        for (const lado of ["l", "r"]) dst[`hem_${lado}`] = sum(dst[`hem_${lado}`], por(res(dst.hem_mid, dst[`hem_${lado}`]), 0.06));
      }
    }
    // El ruedo se ve curvo, como un aro alrededor del cuerpo: los costados suben un poco
    for (const k of ["hem_l", "hem_r"]) dst[k] = sum(dst[k], por(uTorso, -g.distSh * 0.035));
    return dst;
  }

  // Dibuja la imagen deformada: cada triángulo de la foto va a su triángulo en la cámara
  function dibujarMalla(ctx, imagen, src, dst, tieneMangas) {
    // Primero las mangas y encima el torso: de frente, la parte de la manga que cae
    // junto al cuerpo queda detrás de la tela del pecho (no tapa el estampado)
    // Con manga larga es al revés: los brazos van por delante del cuerpo
    const triangulos = !tieneMangas ? TRIANGULOS_TORSO
      : esMangaLarga(src) ? TRIANGULOS_TORSO.concat(TRIANGULOS_MANGAS) : TRIANGULOS_MANGAS.concat(TRIANGULOS_TORSO);
    for (const [a, b, c] of triangulos) {
      const s0 = src[a], s1 = src[b], s2 = src[c];
      const d0 = dst[a], d1 = dst[b], d2 = dst[c];
      if (!s0 || !s1 || !s2 || !d0 || !d1 || !d2) continue;
      const sx1 = s1[0] - s0[0], sy1 = s1[1] - s0[1], sx2 = s2[0] - s0[0], sy2 = s2[1] - s0[1];
      const det = sx1 * sy2 - sx2 * sy1;
      if (Math.abs(det) < 1e-6) continue;
      const dx1 = d1[0] - d0[0], dy1 = d1[1] - d0[1], dx2 = d2[0] - d0[0], dy2 = d2[1] - d0[1];
      const ma = (dx1 * sy2 - dx2 * sy1) / det, mb = (dy1 * sy2 - dy2 * sy1) / det;
      const mc = (dx2 * sx1 - dx1 * sx2) / det, md = (dy2 * sx1 - dy1 * sx2) / det;
      const me = d0[0] - ma * s0[0] - mc * s0[1], mf = d0[1] - mb * s0[0] - md * s0[1];
      // El triángulo se agranda medio píxel desde su centro: así no se ven las uniones
      const cx = (d0[0] + d1[0] + d2[0]) / 3, cy = (d0[1] + d1[1] + d2[1]) / 3;
      const afuera = (p) => { const v = [p[0] - cx, p[1] - cy]; const l = Math.hypot(v[0], v[1]) || 1; return [p[0] + v[0] / l * 0.8, p[1] + v[1] / l * 0.8]; };
      const [e0, e1, e2] = [afuera(d0), afuera(d1), afuera(d2)];
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(e0[0], e0[1]); ctx.lineTo(e1[0], e1[1]); ctx.lineTo(e2[0], e2[1]);
      ctx.closePath();
      ctx.clip();
      ctx.setTransform(ma, mb, mc, md, me, mf);
      ctx.drawImage(imagen, 0, 0);
      ctx.restore();
    }
  }

  return { geometriaCorporal, medirSilueta, tramosDeBrazos, latDelTorso, esMangaLarga, puntosDestino, dibujarMalla };
})();
