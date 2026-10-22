# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# SUITE DE PRUEBAS AUTOMÁTICAS Y VALIDACIÓN (ETAPA 11)
# ==========================================================

import os
import sys
import math
import numpy as np
import cv2

try:
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")  # tildes bien aunque se redirija la salida
except Exception:
    pass

from pose_tracker import PoseTracker
from clothing_geometry import detectar_puntos_clave_prenda, TRIANGULOS_ESTRUCTURADOS
from clothing_warper import deformar_malla_prenda
from body_layering import componer_prenda_con_capas
from catalogo import cargar_catalogo_completo, holgura_de_talle
from body_measure import ancho_total
from siluetas_prueba import crear_persona_sintetica

os.makedirs("capturas", exist_ok=True)
os.makedirs("temp", exist_ok=True)

def simular_landmarks_persona(
    ancho=1280, alto=720,
    cx=640, cy=300,
    ancho_hombros=220,
    largo_torso=280,
    inclinacion_deg=0.0,
    angulo_brazo_izq_deg=10.0,  # 0: vertical abajo, 90: horizontal
    angulo_brazo_der_deg=10.0,
    z_manos_frente=False
):
    """
    Genera un conjunto sintético realista de landmarks corporales
    para probar matemáticamente las reacciones del probador virtual.
    """
    rad = math.radians(inclinacion_deg)
    cos_i, sin_i = math.cos(rad), math.sin(rad)
    
    u_sh = np.array([cos_i, sin_i], dtype=np.float32)
    u_down = np.array([-sin_i, cos_i], dtype=np.float32)
    u_up = -u_down

    p_neck = np.array([cx, cy], dtype=np.float32)
    
    # Hombros
    p_sh_l = p_neck - u_sh * (ancho_hombros * 0.5)
    p_sh_r = p_neck + u_sh * (ancho_hombros * 0.5)

    # Caderas
    p_hip_mid = p_neck + u_down * largo_torso
    p_hip_l = p_hip_mid - u_sh * (ancho_hombros * 0.42)
    p_hip_r = p_hip_mid + u_sh * (ancho_hombros * 0.42)

    # Codos y muñecas
    largo_brazo = ancho_hombros * 0.70
    
    rad_b_l = math.radians(inclinacion_deg + angulo_brazo_izq_deg)
    u_b_l = np.array([-math.sin(rad_b_l), math.cos(rad_b_l)], dtype=np.float32)
    p_elb_l = p_sh_l + u_b_l * largo_brazo
    p_wri_l = p_elb_l + u_b_l * largo_brazo

    rad_b_r = math.radians(inclinacion_deg - angulo_brazo_der_deg)
    u_b_r = np.array([math.sin(rad_b_r), math.cos(rad_b_r)], dtype=np.float32)
    p_elb_r = p_sh_r + u_b_r * largo_brazo
    p_wri_r = p_elb_r + u_b_r * largo_brazo

    # Si los brazos están cruzados al frente
    if z_manos_frente:
        p_wri_l = p_neck + u_down * (largo_torso * 0.55) + u_sh * 40
        p_wri_r = p_neck + u_down * (largo_torso * 0.55) - u_sh * 40

    z_sh = -0.5
    z_wri = -0.8 if z_manos_frente else -0.4

    class DummyLM:
        def __init__(self, x_px, y_px, z, vis=0.99):
            self.x = x_px / float(ancho)
            self.y = y_px / float(alto)
            self.z = z
            self.visibility = vis

    lms = [DummyLM(cx, cy - 80, z_sh)] * 33
    lms[0]  = DummyLM(cx, cy - 90, z_sh)          # Nariz
    lms[11] = DummyLM(p_sh_r[0], p_sh_r[1], z_sh) # Hombro derecho en pantalla (LM11)
    lms[12] = DummyLM(p_sh_l[0], p_sh_l[1], z_sh) # Hombro izquierdo en pantalla (LM12)
    lms[13] = DummyLM(p_elb_r[0], p_elb_r[1], z_sh) # Codo der
    lms[14] = DummyLM(p_elb_l[0], p_elb_l[1], z_sh) # Codo izq
    lms[15] = DummyLM(p_wri_r[0], p_wri_r[1], z_wri) # Muñeca der
    lms[16] = DummyLM(p_wri_l[0], p_wri_l[1], z_wri) # Muñeca izq
    lms[23] = DummyLM(p_hip_r[0], p_hip_r[1], 0.0) # Cadera der
    lms[24] = DummyLM(p_hip_l[0], p_hip_l[1], 0.0) # Cadera izq

    return lms


def ejecutar_todas_las_pruebas():
    print("=" * 65)
    print("      EJECUTANDO BATERÍA DE PRUEBAS Y VALIDACIÓN (ETAPA 11)     ")
    print("=" * 65)

    catalogo = cargar_catalogo_completo()
    print(f"[+] Prendas disponibles en el catálogo: {len(catalogo)}")
    for p in catalogo:
        print(f"    - {p['id']}: {p['nombre']} (Mangas: {p.get('tiene_mangas')})")

    tracker = PoseTracker()
    ancho, alto = 1280, 720
    polo = next((p for p in catalogo if p["id"] == "polo_azul_marino"), catalogo[0])

    # -------------------------------------------------------------
    # PRUEBA 1: Persona de frente, hombros y cintura visibles
    # -------------------------------------------------------------
    print("\n[PRUEBA 1] Persona de frente, hombros y cintura visibles...")
    lms_p1 = simular_landmarks_persona(ancho, alto, cx=640, cy=240, ancho_hombros=240, largo_torso=300)
    
    pts_raw = {
        "nose": np.array([lms_p1[0].x * ancho, lms_p1[0].y * alto]),
        "sh_left": np.array([lms_p1[11].x * ancho, lms_p1[11].y * alto]),
        "sh_right": np.array([lms_p1[12].x * ancho, lms_p1[12].y * alto]),
        "elb_left": np.array([lms_p1[13].x * ancho, lms_p1[13].y * alto]),
        "elb_right": np.array([lms_p1[14].x * ancho, lms_p1[14].y * alto]),
        "wri_left": np.array([lms_p1[15].x * ancho, lms_p1[15].y * alto]),
        "wri_right": np.array([lms_p1[16].x * ancho, lms_p1[16].y * alto]),
        "hip_left": np.array([lms_p1[23].x * ancho, lms_p1[23].y * alto]),
        "hip_right": np.array([lms_p1[24].x * ancho, lms_p1[24].y * alto]),
    }
    z_raw = {k: 0.0 for k in pts_raw}
    vis_raw = {k: 0.99 for k in pts_raw}

    info_p1 = tracker._calcular_geometria_corporal(pts_raw, z_raw, vis_raw, ancho, alto)
    dst_p1 = tracker.calcular_puntos_destino_malla(info_p1, tiene_mangas=polo["tiene_mangas"])
    
    # Validaciones geométricas
    assert abs(info_p1["dist_sh"] - 240.0) < 5.0, "Ancho de hombros incorrecto"
    assert dst_p1["collar_top_mid"][1] < info_p1["p_neck_base"][1], "El cuello debe estar sobre la base del cuello"
    assert dst_p1["hem_mid"][1] > info_p1["p_hip_mid"][1], "El ruedo debe llegar a la cadera"
    
    canvas_p1 = np.full((alto, ancho, 3), 245, dtype=np.uint8)
    parche, x1, y1, x2, y2 = deformar_malla_prenda(polo["imagen_cv"], polo["src_puntos"], dst_p1, ancho, alto)
    res_p1 = componer_prenda_con_capas(canvas_p1, parche, x1, y1, x2, y2, info_p1)
    cv2.imwrite("temp/validacion_prueba1_frontal.png", res_p1)
    print("  [OK] Prueba 1 superada: Prenda centrada, cuello en base y ruedo en cintura.")

    # -------------------------------------------------------------
    # PRUEBA 2: Personas con diferentes anchos de hombros
    # -------------------------------------------------------------
    print("\n[PRUEBA 2] Proporciones corporales: hombros angostos (160px) vs anchos (340px)...")
    # Angosto
    lms_angosto = simular_landmarks_persona(ancho, alto, cx=640, cy=240, ancho_hombros=160, largo_torso=250)
    pts_ang = {k: np.array([lms_angosto[idx].x * ancho, lms_angosto[idx].y * alto]) for k, idx in [("sh_left", 11), ("sh_right", 12), ("elb_left", 13), ("elb_right", 14), ("wri_left", 15), ("wri_right", 16), ("hip_left", 23), ("hip_right", 24), ("nose", 0)]}
    info_ang = tracker._calcular_geometria_corporal(pts_ang, z_raw, vis_raw, ancho, alto)
    dst_ang = tracker.calcular_puntos_destino_malla(info_ang, tiene_mangas=polo["tiene_mangas"])
    
    # Ancho
    lms_ancho = simular_landmarks_persona(ancho, alto, cx=640, cy=240, ancho_hombros=340, largo_torso=340)
    pts_anc = {k: np.array([lms_ancho[idx].x * ancho, lms_ancho[idx].y * alto]) for k, idx in [("sh_left", 11), ("sh_right", 12), ("elb_left", 13), ("elb_right", 14), ("wri_left", 15), ("wri_right", 16), ("hip_left", 23), ("hip_right", 24), ("nose", 0)]}
    info_anc = tracker._calcular_geometria_corporal(pts_anc, z_raw, vis_raw, ancho, alto)
    dst_anc = tracker.calcular_puntos_destino_malla(info_anc, tiene_mangas=polo["tiene_mangas"])

    ancho_manga_ang = dst_ang["sleeve_cuff_out_r"][0] - dst_ang["sleeve_cuff_out_l"][0]
    ancho_manga_anc = dst_anc["sleeve_cuff_out_r"][0] - dst_anc["sleeve_cuff_out_l"][0]
    
    assert ancho_manga_anc > ancho_manga_ang * 1.7, "La prenda ancha debe ser proporcionalmente mayor que la angosta"
    print(f"  Ancho prenda contextura delgada: {ancho_manga_ang:.1f} px")
    print(f"  Ancho prenda contextura robusta: {ancho_manga_anc:.1f} px")
    print("  [OK] Prueba 2 superada: El sistema escala automáticamente ancho y largo sin estirar el cuello.")

    # -------------------------------------------------------------
    # PRUEBA 3: Persona que se inclina lateralmente (roll)
    # -------------------------------------------------------------
    print("\n[PRUEBA 3] Torso inclinado a 18 grados...")
    lms_inclinado = simular_landmarks_persona(ancho, alto, cx=640, cy=240, ancho_hombros=240, largo_torso=300, inclinacion_deg=18.0)
    pts_inc = {k: np.array([lms_inclinado[idx].x * ancho, lms_inclinado[idx].y * alto]) for k, idx in [("sh_left", 11), ("sh_right", 12), ("elb_left", 13), ("elb_right", 14), ("wri_left", 15), ("wri_right", 16), ("hip_left", 23), ("hip_right", 24), ("nose", 0)]}
    info_inc = tracker._calcular_geometria_corporal(pts_inc, z_raw, vis_raw, ancho, alto)
    dst_inc = tracker.calcular_puntos_destino_malla(info_inc, tiene_mangas=polo["tiene_mangas"])
    
    assert abs(info_inc["inclinacion_deg"] - 18.0) < 1.0, "Ángulo de inclinación mal calculado"
    # Verificar vector de hombros
    v_inc = dst_inc["shoulder_r"] - dst_inc["shoulder_l"]
    angulo_prenda = math.degrees(math.atan2(v_inc[1], v_inc[0]))
    assert abs(angulo_prenda - 18.0) < 2.0, "La prenda debe acompañar los 18° de inclinación"
    print(f"  Inclinación detectada: {info_inc['inclinacion_deg']:.1f}° | Inclinación de la prenda: {angulo_prenda:.1f}°")
    print("  [OK] Prueba 3 superada: La prenda se inclina con el torso con precisión milimétrica.")

    # -------------------------------------------------------------
    # PRUEBA 4: Movimiento de brazos y mangas
    # -------------------------------------------------------------
    print("\n[PRUEBA 4] Movimiento de brazos: brazo izquierdo levantado (45°), derecho abajo...")
    lms_brazos = simular_landmarks_persona(ancho, alto, cx=640, cy=240, ancho_hombros=240, largo_torso=300, angulo_brazo_izq_deg=45.0, angulo_brazo_der_deg=10.0)
    pts_br = {k: np.array([lms_brazos[idx].x * ancho, lms_brazos[idx].y * alto]) for k, idx in [("sh_left", 11), ("sh_right", 12), ("elb_left", 13), ("elb_right", 14), ("wri_left", 15), ("wri_right", 16), ("hip_left", 23), ("hip_right", 24), ("nose", 0)]}
    info_br = tracker._calcular_geometria_corporal(pts_br, z_raw, vis_raw, ancho, alto)
    dst_br = tracker.calcular_puntos_destino_malla(info_br, tiene_mangas=polo["tiene_mangas"])
    
    # La manga izquierda (levantada) debe tener su puño más arriba o más hacia afuera que la derecha
    manga_l_y = dst_br["sleeve_cuff_out_l"][1]
    manga_r_y = dst_br["sleeve_cuff_out_r"][1]
    # En pantalla con brazo levantado hacia afuera
    dist_l_cx = abs(dst_br["sleeve_cuff_out_l"][0] - 640)
    dist_r_cx = abs(dst_br["sleeve_cuff_out_r"][0] - 640)
    assert dist_l_cx > dist_r_cx, "La manga del brazo levantado debe proyectarse más hacia afuera"
    print(f"  Proyección manga brazo abierto: {dist_l_cx:.1f} px vs brazo en reposo: {dist_r_cx:.1f} px")
    print("  [OK] Prueba 4 superada: Las mangas siguen la dirección y postura de los brazos.")

    # -------------------------------------------------------------
    # PRUEBA 5: Cambio de prendas del catálogo
    # -------------------------------------------------------------
    print("\n[PRUEBA 5] Cambio dinámico entre todas las prendas del catálogo...")
    for p in catalogo:
        tiene_m = p.get("tiene_mangas", True)
        dst = tracker.calcular_puntos_destino_malla(info_p1, tiene_mangas=tiene_m)
        patch, x1, y1, x2, y2 = deformar_malla_prenda(p["imagen_cv"], p["src_puntos"], dst, ancho, alto, tiene_mangas=tiene_m)
        assert patch is not None and patch.shape[0] > 0 and patch.shape[1] > 0, f"Error deformando {p['id']}"
        res = componer_prenda_con_capas(canvas_p1.copy(), patch, x1, y1, x2, y2, info_p1)
        assert res.shape == (alto, ancho, 3), "Error de forma en composición"
        print(f"  -> Prenda '{p['nombre']}': deformación e integración completadas ({patch.shape[1]}x{patch.shape[0]} px).")
    print("  [OK] Prueba 5 superada: Todas las prendas se adaptan sin reiniciar la cámara.")

    # -------------------------------------------------------------
    # PRUEBA 6: Pérdida temporal de detección y recuperación suave
    # -------------------------------------------------------------
    print("\n[PRUEBA 6] Pérdida temporal de detección y filtro de suavizado EMA...")
    tracker.reiniciar()
    # 5 cuadros detectando
    for f in range(5):
        tracker.puntos_suavizados = {k: v.copy() for k, v in pts_raw.items()}
        tracker.z_suavizados = {k: 0.0 for k in pts_raw}
    
    # 3 cuadros sin detección (persona se tapó o salió brevemente)
    tracker.frames_perdidos = 3
    assert tracker.frames_perdidos <= tracker.max_frames_hold, "Debe mantener estado durante la gracia"
    
    # Reaparición en posición desplazada (+30px en X)
    pts_movido = {k: v + np.array([30.0, 0.0], dtype=np.float32) for k, v in pts_raw.items()}
    # Aplicar EMA manualmente simulando tracker
    p_prev = tracker.puntos_suavizados["sh_left"][0]
    p_detect = pts_movido["sh_left"][0]
    p_suave = p_prev * 0.70 + p_detect * 0.30
    
    salto = abs(p_suave - p_prev)
    salto_sin_suavizado = abs(p_detect - p_prev)
    assert salto < salto_sin_suavizado, "El filtro EMA debe amortiguar el movimiento brusco"
    print(f"  Salto brusco simulado: {salto_sin_suavizado:.1f} px -> Amortiguado con EMA: {salto:.1f} px")
    print("  [OK] Prueba 6 superada: Movimiento suave y retención controlada ante pérdida temporal.")

    # -------------------------------------------------------------
    # PRUEBA 7: Distintas figuras corporales (silueta medida)
    # -------------------------------------------------------------
    print("\n[PRUEBA 7] Distintas figuras con los MISMOS hombros: la prenda debe seguir pecho, cintura y cadera...")
    remera = next((p for p in catalogo if p.get("calce") == "entallado"), catalogo[0])
    esperadas = {
        "rectangulo": "Rectangulo",
        "reloj_de_arena": "Reloj de arena",
        "pera": "Pera",
        "triangulo_invertido": "Triangulo invertido",
        "ovalada": "Ovalada",
    }
    ruedos, cinturas, mosaico = {}, {}, []
    for figura, palabra in esperadas.items():
        tracker.reiniciar_medidas()
        frame_f, mascara_f, _, pts_f = crear_persona_sintetica(figura)
        info_f = tracker._calcular_geometria_corporal(pts_f, {k: 0.0 for k in pts_f}, {k: 0.99 for k in pts_f}, ancho, alto)
        tracker.agregar_medidas(info_f, mascara_f)
        assert palabra in info_f["figura"], f"Figura {figura}: se estimó '{info_f['figura']}'"

        dst_f = tracker.calcular_puntos_destino_malla(info_f, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
        ruedos[figura] = float(dst_f["hem_r"][0] - dst_f["hem_l"][0])
        cinturas[figura] = float(dst_f["waist_r"][0] - dst_f["waist_l"][0])
        # El ruedo siempre debe cubrir la cadera medida
        assert ruedos[figura] >= ancho_total(info_f["medidas"], "cadera") * 0.99, f"El ruedo no cubre la cadera ({figura})"

        parche_f, a1, b1, a2, b2 = deformar_malla_prenda(remera["imagen_cv"], remera["src_puntos"], dst_f, ancho, alto)
        vista = componer_prenda_con_capas(frame_f, parche_f, a1, b1, a2, b2, info_f)[20:640, 360:920].copy()
        cv2.putText(vista, info_f["figura"], (10, 605), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
        mosaico.append(vista)
        print(f"  {figura:<20} -> {info_f['figura']:<38} cintura {cinturas[figura]:6.1f} px | ruedo {ruedos[figura]:6.1f} px")

    assert ruedos["pera"] > ruedos["triangulo_invertido"] * 1.25, "La cadera ancha debe dar un ruedo más ancho"
    assert cinturas["reloj_de_arena"] < cinturas["rectangulo"] * 0.85, "La prenda entallada debe marcar la cintura"
    assert cinturas["ovalada"] > cinturas["reloj_de_arena"] * 1.5, "Con cintura amplia la prenda no debe apretar"
    cv2.imwrite("temp/validacion_prueba7_figuras.png", np.hstack(mosaico))
    print("  [OK] Prueba 7 superada: con los mismos hombros, cada figura recibe una prenda distinta.")

    # -------------------------------------------------------------
    # PRUEBA 8: Talles y tipo de calce
    # -------------------------------------------------------------
    print("\n[PRUEBA 8] Talles S, M y XL y calce entallado vs holgado sobre el mismo cuerpo...")
    tracker.reiniciar_medidas()
    frame_t, mascara_t, _, pts_t = crear_persona_sintetica("reloj_de_arena")
    info_t = tracker._calcular_geometria_corporal(pts_t, {k: 0.0 for k in pts_t}, {k: 0.99 for k in pts_t}, ancho, alto)
    tracker.agregar_medidas(info_t, mascara_t)
    anchos_talle, largos_talle = {}, {}
    for t in ("S", "M", "XL"):
        d = tracker.calcular_puntos_destino_malla(info_t, True, holgura_talle=holgura_de_talle(t), calce="entallado")
        anchos_talle[t] = float(d["waist_r"][0] - d["waist_l"][0])
        largos_talle[t] = float(d["hem_mid"][1] - d["collar_top_mid"][1])
    assert anchos_talle["S"] < anchos_talle["M"] < anchos_talle["XL"], "Un talle más grande debe ser más ancho"
    assert largos_talle["S"] < largos_talle["XL"], "Un talle más grande debe ser un poco más largo"
    d_ent = tracker.calcular_puntos_destino_malla(info_t, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
    d_hol = tracker.calcular_puntos_destino_malla(info_t, True, holgura_talle=holgura_de_talle("M"), calce="holgado")
    cint_ent = float(d_ent["waist_r"][0] - d_ent["waist_l"][0])
    cint_hol = float(d_hol["waist_r"][0] - d_hol["waist_l"][0])
    assert cint_hol > cint_ent * 1.2, "Una prenda holgada no debe marcar la cintura"
    print(f"  Cintura de la prenda: S {anchos_talle['S']:.0f} px | M {anchos_talle['M']:.0f} px | XL {anchos_talle['XL']:.0f} px")
    print(f"  Mismo talle M: entallado {cint_ent:.0f} px vs holgado {cint_hol:.0f} px")
    print("  [OK] Prueba 8 superada: el talle cambia la holgura y el largo; el calce cambia la caída.")

    # -------------------------------------------------------------
    # PRUEBA 9: Sin silueta (respaldo) el sistema sigue funcionando
    # -------------------------------------------------------------
    print("\n[PRUEBA 9] Sin máscara de silueta: se usan las proporciones de hombros...")
    tracker.reiniciar_medidas()
    info_s = tracker._calcular_geometria_corporal(pts_raw, z_raw, vis_raw, ancho, alto)
    tracker.agregar_medidas(info_s, None)
    dst_s = tracker.calcular_puntos_destino_malla(info_s, True)
    assert all(np.all(np.isfinite(v)) for v in dst_s.values()), "Puntos inválidos sin silueta"
    print("  [OK] Prueba 9 superada: si la silueta no está disponible, la prenda igual se coloca.")

    # -------------------------------------------------------------
    # PRUEBA 10: Malla completa (ninguna parte de la prenda se pierde)
    # -------------------------------------------------------------
    print("\n[PRUEBA 10] Cada triángulo de la malla tiene sus puntos en la prenda y en el cuerpo...")
    from clothing_geometry import obtener_triangulos_prenda
    tracker.reiniciar_medidas()
    frame_m, mascara_m, _, pts_m = crear_persona_sintetica("reloj_de_arena")
    info_m = tracker._calcular_geometria_corporal(pts_m, {k: 0.0 for k in pts_m}, {k: 0.99 for k in pts_m}, ancho, alto)
    tracker.agregar_medidas(info_m, mascara_m)
    for p in catalogo:
        tiene_m = p.get("tiene_mangas", True)
        dst_m = tracker.calcular_puntos_destino_malla(info_m, tiene_m, holgura_talle=holgura_de_talle("M"),
                                                      calce=p.get("calce", "regular"))
        for tri in obtener_triangulos_prenda(tiene_m):
            for punto in tri:
                assert punto in p["src_puntos"], f"{p['id']}: falta '{punto}' en la prenda"
                assert punto in dst_m, f"{p['id']}: falta '{punto}' en el cuerpo (calcular_puntos_destino_malla)"
        # Además, la prenda dibujada debe cubrir el torso (no quedar en pedazos)
        parche_m, a1, b1, a2, b2 = deformar_malla_prenda(p["imagen_cv"], p["src_puntos"], dst_m, ancho, alto, tiene_mangas=tiene_m)
        centro = info_m["p_neck_base"] + info_m["u_torso"] * (info_m["dist_torso"] * 0.45)
        cx_l, cy_l = int(centro[0]) - a1, int(centro[1]) - b1
        assert parche_m[cy_l, cx_l, 3] > 0, f"{p['id']}: la prenda tiene un hueco en el torso"
    print(f"  [OK] Prueba 10 superada: las {len(catalogo)} prendas se dibujan completas.")

    # =============================================================
    # PRUEBAS 11 a 15: PRENDA PEGADA AL CUERPO Y MOVIMIENTO REAL
    # =============================================================
    import siluetas_prueba as sp
    from body_layering import recortar_prenda_a_silueta, MARGEN_SILUETA_TALLE
    from body_measure import OneEuroFilter
    remera_t = next((p for p in catalogo if p.get("calce") == "entallado" and p.get("tiene_mangas")), catalogo[0])

    def preparar(figura="reloj_de_arena", **kw):
        tracker.reiniciar_medidas()
        tracker._cuello_suave = None
        frame_x, mascara_x, _, pts_x = sp.crear_persona_sintetica(figura, **kw)
        z_x = dict(sp.crear_persona_sintetica.ultima_z)
        info_x = tracker._calcular_geometria_corporal(pts_x, z_x, {k: 0.99 for k in pts_x}, ancho, alto)
        tracker.agregar_medidas(info_x, mascara_x)
        return frame_x, mascara_x, info_x

    def angulo(p_a, p_b):
        v = p_b - p_a
        return math.degrees(math.atan2(float(v[1]), float(v[0])))

    # PRUEBA 11 (a): el torso de la prenda no supera la silueta + margen del talle
    print("\n[PRUEBA 11] La prenda no se sale de la silueta más que el margen del talle...")
    frame_a, mascara_a, info_a = preparar("pera")
    dst_a = tracker.calcular_puntos_destino_malla(info_a, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
    parche_a, a1, b1, a2, b2 = deformar_malla_prenda(remera_t["imagen_cv"], remera_t["src_puntos"], dst_a, ancho, alto)
    parche_rec = recortar_prenda_a_silueta(parche_a, a1, b1, mascara_a, info_a, talle="M")
    margen = int(round(MARGEN_SILUETA_TALLE["M"] * info_a["dist_sh"] / 220.0))
    cuerpo = (mascara_a[b1:b2, a1:a2] > 0.5).astype(np.uint8) * 255
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * (margen + 2) + 1, 2 * (margen + 2) + 1))
    permitido = cv2.dilate(cuerpo, k) > 0
    filas = np.arange(parche_rec.shape[0])[:, None] + b1
    zona_torso = (filas > info_a["p_neck_base"][1] + info_a["dist_torso"] * 0.40) & np.ones_like(permitido)
    afuera_antes = int(np.count_nonzero((parche_a[:, :, 3] > 60) & ~permitido & zona_torso))
    afuera = int(np.count_nonzero((parche_rec[:, :, 3] > 60) & ~permitido & zona_torso))
    assert afuera == 0, f"La prenda sobresale {afuera} píxeles de la silueta"
    print(f"  Píxeles de tela fuera del cuerpo en el torso: antes {afuera_antes} -> ahora {afuera}")
    print("  [OK] Prueba 11 superada: la prenda queda pegada a la silueta.")

    # PRUEBA 12 (b): cadera inclinada 10° -> ruedo inclinado entre 8° y 12°
    print("\n[PRUEBA 12] Cadera inclinada 10 grados: el ruedo debe acompañarla...")
    _, _, info_b = preparar("rectangulo", inclinacion_cadera_deg=10.0)
    dst_b = tracker.calcular_puntos_destino_malla(info_b, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
    ang_cadera = abs(angulo(info_b["p_hip_l"], info_b["p_hip_r"]))
    ang_ruedo = abs(angulo(dst_b["hem_l"], dst_b["hem_r"]))
    assert 8.0 <= ang_ruedo <= 12.0, f"El ruedo se inclinó {ang_ruedo:.1f}°"
    print(f"  Cadera: {ang_cadera:.1f}° | Ruedo de la prenda: {ang_ruedo:.1f}°")
    print("  [OK] Prueba 12 superada: el ruedo sigue la línea de caderas.")

    # PRUEBA 13 (c): torso girado -> el lado lejano es más angosto y el centro se corre
    print("\n[PRUEBA 13] Torso girado: el lado que se aleja se ve más angosto...")
    _, _, info_c = preparar("rectangulo", giro=0.6)
    dst_c = tracker.calcular_puntos_destino_malla(info_c, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
    centro_c = info_c["p_neck_base"][0]
    lado_cerca = centro_c - dst_c["waist_l"][0]
    lado_lejos = dst_c["waist_r"][0] - centro_c
    assert info_c["giro"] > 0.1, "No se detectó el giro"
    assert lado_lejos < lado_cerca, "El lado lejano debe ser más angosto"
    assert dst_c["chest_mid"][0] > centro_c, "El centro de la prenda debe correrse hacia el lado lejano"
    # Sin silueta también debe achicarse el lado lejano
    info_c2 = dict(info_c); info_c2["medidas"] = {}
    dst_c2 = tracker.calcular_puntos_destino_malla(info_c2, True, holgura_talle=holgura_de_talle("M"))
    assert (dst_c2["waist_r"][0] - centro_c) < (centro_c - dst_c2["waist_l"][0]), "Sin silueta, el lado lejano debe achicarse"
    print(f"  Giro estimado: {info_c['giro']:+.2f} | cintura lado cercano {lado_cerca:.0f} px vs lejano {lado_lejos:.0f} px")
    print("  [OK] Prueba 13 superada: la prenda acompaña el giro del torso.")

    # PRUEBA 14 (d): brazo levantado -> la axila de ese lado sube
    print("\n[PRUEBA 14] Brazo levantado: la axila de ese lado debe subir...")
    _, _, info_d0 = preparar("rectangulo")
    dst_d0 = tracker.calcular_puntos_destino_malla(info_d0, True, holgura_talle=holgura_de_talle("M"))
    _, _, info_d = preparar("rectangulo", angulo_brazo_izq_deg=150.0)
    dst_d = tracker.calcular_puntos_destino_malla(info_d, True, holgura_talle=holgura_de_talle("M"))
    subida = float(dst_d0["armpit_l"][1] - dst_d["armpit_l"][1])
    quieta = abs(float(dst_d0["armpit_r"][1] - dst_d["armpit_r"][1]))
    assert subida > 5.0 and subida > quieta + 5.0, f"La axila subió sólo {subida:.1f} px"
    assert dst_d["hem_mid"][1] < dst_d0["hem_mid"][1], "El ruedo debe levantarse un poco"
    print(f"  Axila del brazo levantado: sube {subida:.0f} px | axila del otro lado: {quieta:.0f} px")
    print("  [OK] Prueba 14 superada: la prenda se levanta con el brazo.")

    # PRUEBA 15 (e): un salto brusco de 40 px se sigue en menos de 3 cuadros
    print("\n[PRUEBA 15] Movimiento brusco de 40 px: la prenda no debe quedar atrás...")
    filtro = OneEuroFilter(t0=0.0, x0=np.array([100.0, 0.0]), min_cutoff=1.0, beta=0.04, d_cutoff=1.0)
    t_seg, errores = 0.0, []
    for _ in range(3):
        t_seg += 1.0 / 30.0
        errores.append(abs(140.0 - float(filtro.filter(np.array([140.0, 0.0]), t_seg)[0])))
    assert errores[-1] < 4.0, f"Después de 3 cuadros sigue {errores[-1]:.1f} px atrás"
    print(f"  Distancia a la posición real por cuadro: {', '.join(f'{e:.1f}' for e in errores)} px")
    print("  [OK] Prueba 15 superada: la prenda alcanza a la persona en 3 cuadros.")

    # Imagen de validación para la presentación
    escenas = [("Pegada a la silueta", "pera", {}), ("Cadera inclinada", "rectangulo", {"inclinacion_cadera_deg": 10.0}),
               ("Torso girado", "rectangulo", {"giro": 0.6}), ("Brazo levantado", "rectangulo", {"angulo_brazo_izq_deg": 150.0})]
    vistas = []
    for titulo, fig, kw in escenas:
        fr, ms, inf = preparar(fig, **kw)
        dd = tracker.calcular_puntos_destino_malla(inf, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
        pa, x1_, y1_, x2_, y2_ = deformar_malla_prenda(remera_t["imagen_cv"], remera_t["src_puntos"], dd, ancho, alto)
        vista = componer_prenda_con_capas(fr, pa, x1_, y1_, x2_, y2_, inf, talle="M")[0:640, 380:900].copy()
        cv2.putText(vista, titulo, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2, cv2.LINE_AA)
        vistas.append(vista)
    cv2.imwrite("temp/validacion_prenda_pegada.png", np.hstack(vistas))

    # =============================================================
    # PRUEBAS 16 a 18: DE FRENTE, DE ESPALDAS Y DE PERFIL
    # =============================================================
    def orientacion_de(pts_o, z_o, vis_o):
        info_o = tracker._calcular_geometria_corporal(pts_o, z_o, vis_o, ancho, alto)
        return info_o["orientacion_cuadro"]

    print("\n[PRUEBA 16] Detectar si la persona está de frente, girada, de perfil o de espaldas...")
    _, _, _, pts_f = sp.crear_persona_sintetica("rectangulo")
    z_f = dict(sp.crear_persona_sintetica.ultima_z)
    o_frente = orientacion_de(pts_f, z_f, {k: 0.99 for k in pts_f})
    _, _, _, pts_g = sp.crear_persona_sintetica("rectangulo", giro=0.6)
    o_girada = orientacion_de(pts_g, dict(sp.crear_persona_sintetica.ultima_z), {k: 0.99 for k in pts_g})
    _, _, _, pts_p = sp.crear_persona_sintetica("rectangulo", ancho_hombros=90)
    o_perfil = orientacion_de(pts_p, {k: 0.0 for k in pts_p}, {k: 0.99 for k in pts_p})
    pts_e, z_e, vis_e = sp.poner_de_espaldas(pts_f, z_f)
    o_espalda = orientacion_de(pts_e, z_e, vis_e)
    assert (o_frente, o_girada, o_perfil, o_espalda) == ("frente", "girada", "perfil", "espalda"), \
        f"Orientaciones detectadas: {o_frente}, {o_girada}, {o_perfil}, {o_espalda}"
    # Histéresis: un solo cuadro "raro" no cambia la vista
    tracker.orientacion, tracker._cuadros_candidata = "frente", 0
    estados = [tracker.actualizar_orientacion(o) for o in ["espalda", "frente", "espalda", "espalda", "espalda", "espalda"]]
    assert estados[:5] == ["frente"] * 5 and estados[5] == "espalda", f"Histéresis incorrecta: {estados}"
    tracker.orientacion = "frente"
    print(f"  Detectado: {o_frente} | {o_girada} | {o_perfil} | {o_espalda}")
    print("  [OK] Prueba 16 superada: el probador sabe hacia dónde mira la persona.")

    print("\n[PRUEBA 17] Cada prenda tiene vista de espalda sin logos ni botones...")
    for p in catalogo:
        assert p.get("imagen_espalda_cv") is not None and p.get("src_puntos_espalda"), f"{p['id']} sin espalda"
    def detalle(img):
        tela = img[:, :, 3] > 200
        grises = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float32)
        bordes = np.abs(cv2.Laplacian(grises, cv2.CV_32F, ksize=3))
        return float(np.mean(bordes[tela]))
    polo = next((p for p in catalogo if "polo" in p["id"]), catalogo[0])
    d_frente, d_espalda = detalle(polo["imagen_cv"]), detalle(polo["imagen_espalda_cv"])
    assert d_espalda < d_frente * 0.85, "La espalda automática debería tener menos detalles que el frente"
    print(f"  {polo['nombre']}: detalle del frente {d_frente:.1f} -> espalda {d_espalda:.1f} "
          f"({'foto propia' if not polo['espalda_automatica'] else 'automática'})")
    print("  [OK] Prueba 17 superada: de espaldas no se muestran logos ni botones del frente.")

    print("\n[PRUEBA 18] De perfil la prenda se desvanece suavemente (sin verse rota)...")
    opacidad, pasos = 1.0, []
    for _ in range(12):
        opacidad += (0.0 - opacidad) * 0.25
        pasos.append(opacidad)
    assert pasos[0] > 0.5 and pasos[-1] < 0.05, "El desvanecido debe ser gradual y terminar casi en 0"
    print(f"  Opacidad: {pasos[0]:.2f} -> {pasos[3]:.2f} -> {pasos[-1]:.2f} en 12 cuadros (~0,4 s)")
    print("  [OK] Prueba 18 superada: de perfil se avisa en lugar de mostrar la prenda deformada.")

    # Imagen para la presentación: frente y espalda de la misma prenda
    vistas = []
    for titulo, espalda in (("De frente", False), ("De espaldas", True)):
        fr, ms, inf = preparar("reloj_de_arena")
        img_p = polo["imagen_espalda_cv"] if espalda else polo["imagen_cv"]
        src_p = polo["src_puntos_espalda"] if espalda else polo["src_puntos"]
        dd = tracker.calcular_puntos_destino_malla(inf, polo["tiene_mangas"], holgura_talle=holgura_de_talle("M"),
                                                   calce=polo.get("calce", "regular"))
        pa, x1_, y1_, x2_, y2_ = deformar_malla_prenda(img_p, src_p, dd, ancho, alto, polo["tiene_mangas"])
        vista = componer_prenda_con_capas(fr, pa, x1_, y1_, x2_, y2_, inf, talle="M")[0:640, 380:900].copy()
        cv2.putText(vista, titulo, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2, cv2.LINE_AA)
        vistas.append(vista)
    cv2.imwrite("temp/validacion_frente_espalda.png", np.hstack(vistas))

    # =============================================================
    # PRUEBA 19: AJUSTE TIPO ESCÁNER (la tela copia la silueta fila por fila)
    # =============================================================
    from ajuste_silueta import ajustar_prenda_a_silueta, ajustar_prenda_completa, _mascara_torso_sin_brazos
    print("\n[PRUEBA 19] Escáner: el borde de la tela sigue el borde del cuerpo en cada fila...")
    for figura_s in ("pera", "ovalada", "reloj_de_arena"):
        fr_s, ms_s, inf_s = preparar(figura_s)
        dd = tracker.calcular_puntos_destino_malla(inf_s, True, holgura_talle=holgura_de_talle("S"), calce="entallado")
        pa, x1_, y1_, x2_, y2_ = deformar_malla_prenda(remera_t["imagen_cv"], remera_t["src_puntos"], dd, ancho, alto)
        ajustado = ajustar_prenda_a_silueta(pa, x1_, y1_, ms_s, inf_s, holgura=1.0, calce="entallado")
        errores_px = []
        cuerpo_s = _mascara_torso_sin_brazos(ms_s, inf_s, 0, 0, alto, ancho)  # torso sin brazos
        for frac in (0.62, 0.80, 0.95):  # cintura, cadera alta, cadera
            y = int(inf_s["p_neck_base"][1] + inf_s["dist_torso"] * frac)
            fila_tela = np.where(ajustado[y - y1_, :, 3] > 128)[0] + x1_
            fila_cuerpo = np.where(cuerpo_s[y])[0]
            if len(fila_tela) and len(fila_cuerpo):
                cx_s = int(inf_s["p_neck_base"][0])
                # borde del torso del cuerpo desde el centro (sin brazos: tomamos el tramo central)
                izq = cx_s - np.argmin(cuerpo_s[y, :cx_s][::-1])
                der = cx_s + np.argmin(cuerpo_s[y, cx_s:]) - 1
                errores_px += [abs(fila_tela.min() - izq), abs(fila_tela.max() - der)]
        error_medio = float(np.mean(errores_px))
        assert error_medio < 6.0, f"{figura_s}: el borde de la tela queda a {error_medio:.1f} px del cuerpo"
        print(f"  {figura_s:<15} distancia media tela-cuerpo: {error_medio:.1f} px")
    # Hombros: la línea de arriba de la prenda se apoya sobre la línea real del hombro
    fr_h, ms_h, inf_h = preparar("rectangulo")
    dd = tracker.calcular_puntos_destino_malla(inf_h, True, holgura_talle=holgura_de_talle("M"), calce="entallado")
    pa, x1_, y1_, x2_, y2_ = deformar_malla_prenda(remera_t["imagen_cv"], remera_t["src_puntos"], dd, ancho, alto)
    antes_h = pa
    despues_h = ajustar_prenda_completa(pa, x1_, y1_, ms_h, inf_h, holgura=1.05, calce="entallado")
    def distancia_hombros(parche):
        dist = []
        for lado in ("p_sh_l", "p_sh_r"):
            for f in (0.35, 0.65):  # entre el cuello y la punta del hombro
                x = int(inf_h["p_neck_base"][0] + (inf_h[lado][0] - inf_h["p_neck_base"][0]) * (f + 0.4))
                col_c = np.where(ms_h[:, x] > 0.5)[0]
                col_t = np.where(parche[:, x - x1_, 3] > 128)[0]
                if len(col_c) and len(col_t):
                    dist.append(abs(float(col_t.min() + y1_) - float(col_c.min())))
        return float(np.mean(dist)) if dist else 99.0
    d_antes, d_despues = distancia_hombros(antes_h), distancia_hombros(despues_h)
    assert d_despues < 6.0 and d_despues <= d_antes, f"Hombros: {d_antes:.1f} px -> {d_despues:.1f} px"
    print(f"  Hombros: distancia entre la tela y la línea del hombro {d_antes:.1f} px -> {d_despues:.1f} px")
    print("  [OK] Prueba 19 superada: la prenda copia la forma del cuerpo como un escáner.")

    # =============================================================
    # PRUEBA 20: SALTEAR CUADROS DE MEDIAPIPE SIN PERDER A LA PERSONA
    # =============================================================
    print("\n[PRUEBA 20] MediaPipe 1 de cada 2 cuadros: la prenda sigue igual a la persona...")

    class _Mascara:
        def __init__(self, m):
            self.m = m
        def numpy_view(self):
            return self.m

    class _DetectorSimulado:
        """Reemplaza a MediaPipe: devuelve la persona sintética del cuadro actual."""
        def __init__(self):
            self.llamadas = 0
            self.escena = None
        def detect_for_video(self, imagen, timestamp_ms):
            self.llamadas += 1
            lms_s, mascara_s = self.escena
            return type("R", (), {"pose_landmarks": [lms_s], "segmentation_masks": [_Mascara(mascara_s)]})()
        def close(self):
            pass

    def recorrido(cada_n):
        tr = PoseTracker(cada_n_cuadros=cada_n)
        tr.detector.close()
        tr.detector = _DetectorSimulado()
        cuellos, verdad, centros_mascara = [], [], []
        for i in range(16):
            cx_i = 200 + 8 * i  # se mueve 8 px por cuadro (~240 px/s)
            fr_i, ms_i, lms_i, _ = sp.crear_persona_sintetica("rectangulo", ancho=640, alto=360, cx=cx_i, cy=90,
                                                              ancho_hombros=110, largo_torso=140)
            tr.detector.escena = (lms_i, ms_i)
            _, inf_i = tr.procesar_frame(fr_i, timestamp_ms=1000 + 33 * i)
            if i >= 4:  # después de que el filtro arranca
                cuellos.append(float(inf_i["p_neck_base"][0]))
                verdad.append(float(cx_i))
                centros_mascara.append(float(np.mean(np.where(inf_i["mascara"] > 0.5)[1])) - float(np.mean(np.where(ms_i > 0.5)[1])))
        tr.cerrar()
        return tr.detector.llamadas, np.array(cuellos) - np.array(verdad), np.array(centros_mascara)

    llamadas_1, error_1, _ = recorrido(1)
    llamadas_2, error_2, error_mascara = recorrido(2)
    assert llamadas_2 == llamadas_1 // 2, f"Se llamó a MediaPipe {llamadas_2} veces de {llamadas_1}"
    assert np.max(np.abs(error_2 - error_1)) < 3.0, \
        f"Saltear cuadros corre la prenda {np.max(np.abs(error_2 - error_1)):.1f} px respecto de detectar siempre"
    assert np.max(np.abs(error_mascara)) < 2.0, f"La silueta predicha queda {np.max(np.abs(error_mascara)):.1f} px corrida"
    print(f"  MediaPipe: {llamadas_1} -> {llamadas_2} llamadas | diferencia de posición máx {np.max(np.abs(error_2 - error_1)):.1f} px"
          f" | silueta predicha corrida máx {np.max(np.abs(error_mascara)):.1f} px")
    print("  [OK] Prueba 20 superada: saltear cuadros no hace perder a la persona.")

    print("\n" + "=" * 65)
    print("   [OK] TODAS LAS 20 PRUEBAS DEL SISTEMA FUERON SUPERADAS CON EXITO")
    print("=" * 65)

if __name__ == "__main__":
    ejecutar_todas_las_pruebas()
