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
    let visElL = vis.elb_left, visElR = vis.elb_right;
    // El hombro de la izquierda de la pantalla es el de menor X
    if (shR[0] <= shL[0]) {
      [shL, shR, elL, elR, wrL, wrR, hiL, hiR] = [shR, shL, elR, elL, wrR, wrL, hiR, hiL];
      [visElL, visElR] = [visElR, visElL];
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
      shL, shR, elL, elR, wrL, wrR, cuello, distSh, distTorso, uSh, uUp, uDown, uTorso, uHip,
      uArmL, uArmR, uCuffL, uCuffR, caderasVisibles, medioCuello, medioCara, menton, nariz: pts.nose,
      brazoArribaL: elevacion(shL, elL), brazoArribaR: elevacion(shR, elR),
    };
  }

  // Prendas sin mangas: UNA sola transformación que respeta su forma (tiras, escote)
  function parteAltaComoLaPrenda(dst, src, uLat, uTorso) {
    if (!src.armpit_l || !src.armpit_r || !src.hem_mid) return;
    const anchoSrc = Math.abs(src.armpit_r[0] - src.armpit_l[0]);
    const yAxilas = (src.armpit_l[1] + src.armpit_r[1]) * 0.5;
    const largoSrc = src.hem_mid[1] - yAxilas;
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
    const medio = { pecho: dSh * 0.56 * Math.max(1, extraCalce), cintura: dSh * 0.44 * k, ruedo: dSh * 0.449 * k };
    medio.bajoBusto = (medio.pecho + medio.cintura) / 2;
    medio.caderaAlta = (medio.cintura + medio.ruedo) / 2;
    const hombroExtra = dSh * 0.10;
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
      armpit_l: S(nivel(0.33), por(uLat, -medio.pecho), por(uUp, g.brazoArribaL * dTorso * 0.10)),
      armpit_r: S(nivel(0.33), por(uLat, medio.pecho), por(uUp, g.brazoArribaR * dTorso * 0.10)),
      chest_mid: nivel(0.36),
      torso_mid: nivel(0.68),
      underbust_l: S(nivel(0.50), por(lateral(0.2), -medio.bajoBusto), por(uUp, g.brazoArribaL * dTorso * 0.04)),
      underbust_r: S(nivel(0.50), por(lateral(0.2), medio.bajoBusto), por(uUp, g.brazoArribaR * dTorso * 0.04)),
      waist_l: sum(nivel(0.68), por(lateral(0.5), -medio.cintura)),
      waist_r: sum(nivel(0.68), por(lateral(0.5), medio.cintura)),
      high_hip_l: S(nivel(0.86), por(lateral(0.8), -medio.caderaAlta), por(uTorso, -subeRuedo * 0.6)),
      high_hip_r: S(nivel(0.86), por(lateral(0.8), medio.caderaAlta), por(uTorso, -subeRuedo * 0.6)),
      hem_l: S(nivel(1.05), por(lateral(1), -medio.ruedo), por(uTorso, -subeRuedo)),
      hem_mid: sum(nivel(1.06), por(uTorso, -subeRuedo)),
      hem_r: S(nivel(1.05), por(lateral(1), medio.ruedo), por(uTorso, -subeRuedo)),
    };
    if (!prenda.tiene_mangas) {
      parteAltaComoLaPrenda(dst, prenda.puntos, uLat, uTorso);
      for (const lado of ["l", "r"]) {
        dst[`sleeve_top_${lado}`] = dst[`shoulder_${lado}`];
        for (const k of ["sleeve_cuff_out", "sleeve_cuff_in", "bicep_out", "bicep_in"]) dst[`${k}_${lado}`] = dst[`armpit_${lado}`];
      }
    } else {
      escoteComoLaPrenda(dst, prenda.puntos, cuello, uSh, uTorso, anchoCuello, alturaCuello, g.distTorso);
    }
    return dst;
  }

  // Dibuja la imagen deformada: cada triángulo de la foto va a su triángulo en la cámara
  function dibujarMalla(ctx, imagen, src, dst, tieneMangas) {
    // Primero las mangas y encima el torso: de frente, la parte de la manga que cae
    // junto al cuerpo queda detrás de la tela del pecho (no tapa el estampado)
    const triangulos = tieneMangas ? TRIANGULOS_MANGAS.concat(TRIANGULOS_TORSO) : TRIANGULOS_TORSO;
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

  return { geometriaCorporal, puntosDestino, dibujarMalla };
})();
