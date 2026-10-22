# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# GENERADOR Y GESTOR DE PRENDAS PNG CON CANAL ALFA
# ==========================================================

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def crear_remera_femenina_png(ruta_destino, color_rgb=(41, 128, 185), texto_logo="ATELIER"):
    """
    Crea una prenda femenina estilizada en formato PNG con fondo transparente (canal Alfa).
    Posee silueta entallada, escote femenino, mangas suaves y sutiles costuras.
    """
    ancho, alto = 600, 650
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Silueta de remera femenina (con entalle en cintura y curva natural en mangas)
    puntos_remera = [
        (225, 75),   # Cuello izquierdo
        (375, 75),   # Cuello derecho
        (480, 115),  # Hombro derecho
        (565, 230),  # Manga derecha superior
        (505, 275),  # Manga derecha inferior
        (440, 220),  # Axila derecha
        (415, 360),  # Cintura derecha (entallada)
        (445, 540),  # Cadera/Ruedo derecha
        (155, 540),  # Cadera/Ruedo izquierda
        (185, 360),  # Cintura izquierda (entallada)
        (160, 220),  # Axila izquierda
        (95, 275),   # Manga izquierda inferior
        (35, 230),   # Manga izquierda superior
        (120, 115),  # Hombro izquierdo
    ]

    r, g, b = color_rgb
    color_relleno = (r, g, b, 255)
    # Borde sutil más oscuro
    color_borde = (max(0, r - 35), max(0, g - 35), max(0, b - 35), 255)
    # Tono para costuras y detalles interiores
    color_detalle = (max(0, r - 25), max(0, g - 25), max(0, b - 25), 180)

    # 1. Dibujar silueta base
    draw.polygon(puntos_remera, fill=color_relleno, outline=color_borde, width=3)

    # 2. Escote femenino redondeado / escote en U suave
    draw.arc([220, 50, 380, 150], start=0, end=180, fill=color_borde, width=4)

    # 3. Costuras estilizadas en mangas y dobladillo
    draw.line([(120, 115), (160, 220)], fill=color_detalle, width=2)
    draw.line([(480, 115), (440, 220)], fill=color_detalle, width=2)
    draw.line([(155, 520), (445, 520)], fill=color_detalle, width=2)

    # 4. Sutil brillo / luz en el pecho para dar volumen tridimensional
    overlay = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    color_brillo = (min(255, r + 40), min(255, g + 40), min(255, b + 40), 55)
    draw_ov.ellipse([230, 200, 370, 380], fill=color_brillo)
    overlay = overlay.filter(ImageFilter.GaussianBlur(15))
    img = Image.alpha_composite(img, overlay)

    # Guardar en formato PNG preservando transparencia
    img.save(ruta_destino, "PNG")
    print(f"[OK] Prenda generada: {ruta_destino}")


def procesar_top_champagne_si_existe():
    """Si el usuario tiene la foto del top de satén champagne, genera su versión transparente."""
    rutas_posibles = [
        os.path.join("prendas", "top_satin_champagne.jpg"),
        os.path.join("prendas", "top_champagne.jpg"),
        r"C:\Users\gimeni\.gemini\antigravity-ide\brain\f01cf7fe-7982-430a-a244-6af983a1222f\.user_uploaded\media_1790809137995.jpg"
    ]
    
    destino_png = os.path.join("prendas", "top_satin_champagne.png")
    if os.path.exists(destino_png):
        return
        
    for ruta in rutas_posibles:
        if os.path.exists(ruta):
            try:
                img = cv2.imread(ruta)
                h, w = img.shape[:2]
                bg = np.array([190, 190, 190], dtype=np.float32)
                dist = np.linalg.norm(img.astype(np.float32) - bg, axis=2)
                mask = (dist >= 14).astype(np.uint8) * 255
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
                
                bg_mask = (mask == 0).astype(np.uint8) * 255
                mask_outside = np.zeros((h+2, w+2), np.uint8)
                cv2.floodFill(bg_mask, mask_outside, (0, 0), 128)
                cv2.floodFill(bg_mask, mask_outside, (w // 2, int(h * 0.24)), 128)
                
                alpha = np.where(bg_mask == 128, 0, 255).astype(np.uint8)
                alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
                
                b, g, r = cv2.split(img)
                rgba = cv2.merge([b, g, r, alpha])
                cv2.imwrite(destino_png, rgba)
                print(f"[OK] Top Satin Champagne preparado en: {destino_png}")
                break
            except Exception as e:
                print(f"[AVISO] No se pudo procesar top champagne: {e}")


def generar_catalogo_inicial():
    """Genera las prendas base solicitadas con transparencia PNG."""
    os.makedirs("prendas", exist_ok=True)

    # 1. Remera Básica Blanca
    crear_remera_femenina_png(
        ruta_destino=os.path.join("prendas", "remera_blanca.png"),
        color_rgb=(245, 245, 248),
        texto_logo="BASIC WHITE"
    )

    # 2. Remera Clásica Azul
    crear_remera_femenina_png(
        ruta_destino=os.path.join("prendas", "remera_azul.png"),
        color_rgb=(35, 95, 175),
        texto_logo="CLASSIC BLUE"
    )

    # 3. Remera Urbana Negra
    crear_remera_femenina_png(
        ruta_destino=os.path.join("prendas", "remera_negra.png"),
        color_rgb=(32, 32, 36),
        texto_logo="URBAN BLACK"
    )

    # 4. Remera Coral Roja
    crear_remera_femenina_png(
        ruta_destino=os.path.join("prendas", "remera_roja.png"),
        color_rgb=(215, 55, 65),
        texto_logo="CORAL RED"
    )

    # 5. Chomba Polo Azul Marino / Ralph Lauren (si la imagen de referencia está disponible)
    procesar_polo_azul_marino_si_existe()
    procesar_polo_ralph_lauren_si_existe()

    # 6. Top Satin Champagne (si está disponible la imagen)
    procesar_top_champagne_si_existe()

    # 7. Top / Vestido Asimétrico Drapeado Negro
    procesar_top_asimetrico_negro_si_existe()


def procesar_polo_azul_marino_si_existe():
    """Asegura la existencia de la chomba polo azul marino con cuello blanco."""
    destino_png = os.path.join("prendas", "polo_azul_marino.png")
    if os.path.exists(destino_png):
        return

    # Buscar imágenes de referencia
    rutas = [
        r"C:\Users\gimeni\.gemini\antigravity-ide\brain\4a8e5b91-5b64-488b-9863-1c0dde391743\.user_uploaded\media_1792522282883.jpg",
        r"C:\Users\gimeni\.gemini\antigravity-ide\brain\b90a2a09-3600-4d2a-8674-44138912e0e2\polo_azul_marino_1791148065781.jpg",
        os.path.join("prendas", "polo_azul_marino.jpg"),
    ]
    for r in rutas:
        if os.path.exists(r):
            try:
                img = cv2.imread(r)
                h, w = img.shape[:2]
                mask_flood = np.zeros((h + 2, w + 2), np.uint8)
                diff = (12, 12, 12)
                for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
                    cv2.floodFill(img.copy(), mask_flood, pt, (0, 0, 0), loDiff=diff, upDiff=diff, flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
                bg_mask = mask_flood[1:h+1, 1:w+1]
                fg_mask = (bg_mask == 0).astype(np.uint8) * 255
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
                alpha = cv2.GaussianBlur(fg_mask, (3, 3), 0)
                b, g, r_ch = cv2.split(img)
                rgba = cv2.merge([b, g, r_ch, alpha])
                cv2.imwrite(destino_png, rgba)
                print(f"[OK] Chomba Polo Azul Marino preparada en: {destino_png}")
                return
            except Exception as e:
                print(f"[AVISO] Error procesando polo azul marino: {e}")


def procesar_polo_ralph_lauren_si_existe():
    """Asegura la chomba Polo Ralph Lauren clásica con Big Pony y número 3."""
    destino_png = os.path.join("prendas", "polo_ralph_lauren.png")
    if os.path.exists(destino_png):
        return

    rutas = [
        r"C:\Users\gimeni\.gemini\antigravity-ide\brain\4a8e5b91-5b64-488b-9863-1c0dde391743\.user_uploaded\media_1792522282883.jpg",
        os.path.join("prendas", "polo_ralph_lauren.jpg"),
    ]
    for r in rutas:
        if os.path.exists(r):
            try:
                img = cv2.imread(r)
                h, w = img.shape[:2]
                mask_flood = np.zeros((h + 2, w + 2), np.uint8)
                diff = (14, 14, 14)
                for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (0, h // 2), (w - 1, h // 2)]:
                    cv2.floodFill(img.copy(), mask_flood, pt, (0, 0, 0), loDiff=diff, upDiff=diff, flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
                bg_mask = mask_flood[1:h+1, 1:w+1]
                fg_mask = (bg_mask == 0).astype(np.uint8) * 255
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel)
                alpha = cv2.GaussianBlur(fg_mask, (3, 3), 0)
                b, g, r_ch = cv2.split(img)
                rgba = cv2.merge([b, g, r_ch, alpha])
                cv2.imwrite(destino_png, rgba)
                print(f"[OK] Polo Ralph Lauren preparado en: {destino_png}")
                return
            except Exception as e:
                print(f"[AVISO] Error procesando polo Ralph Lauren: {e}")


def procesar_top_asimetrico_negro_si_existe():
    """Asegura el Top / Vestido Asimétrico Drapeado Negro con fular lateral."""
    destino_png = os.path.join("prendas", "top_asimetrico_negro.png")
    if os.path.exists(destino_png):
        return

    rutas = [
        r"C:\Users\gimeni\.gemini\antigravity-ide\brain\4a8e5b91-5b64-488b-9863-1c0dde391743\.user_uploaded\media_1792522368481.jpg",
        os.path.join("prendas", "top_asimetrico_negro.jpg"),
    ]
    for r in rutas:
        if os.path.exists(r):
            try:
                img = cv2.imread(r)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                fg_mask = (gray < 135).astype(np.uint8) * 255
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
                fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel, iterations=1)
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(fg_mask)
                clean_mask = np.zeros_like(fg_mask)
                for i in range(1, num_labels):
                    if stats[i, cv2.CC_STAT_AREA] > 500:
                        clean_mask[labels == i] = 255
                alpha = cv2.GaussianBlur(clean_mask, (3, 3), 0)
                b, g, r_ch = cv2.split(img)
                rgba = cv2.merge([b, g, r_ch, alpha])
                cv2.imwrite(destino_png, rgba)
                print(f"[OK] Top Asimétrico Negro preparado en: {destino_png}")
                return
            except Exception as e:
                print(f"[AVISO] Error procesando top asimétrico negro: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("   GENERADOR DE PRENDAS FEMENINAS - PROBADOR VIRTUAL   ")
    print("=" * 60)
    generar_catalogo_inicial()

