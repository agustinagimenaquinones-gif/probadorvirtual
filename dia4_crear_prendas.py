# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# DÍA 4 / ETAPA 4: Creación de Prendas PNG con Transparencia
# ==========================================================

import os
from crear_prendas import generar_catalogo_inicial
def main():
    print("=" * 60)
    print("   DÍA 4: GENERACIÓN DE PRENDAS PNG (CANAL ALFA)   ")
    print("=" * 60)
    print("Objetivo: Generar las imágenes PNG transparentes con Pillow.")
    print("Guardando en carpeta 'prendas/'...\n")

    os.makedirs("prendas", exist_ok=True)
    generar_catalogo_inicial()

    print("\n[OK] Catálogo de prendas generado exitosamente:")
    for f in os.listdir("prendas"):
        if f.endswith(".png"):
            print(f" -> prendas/{f}")

    print("\nPresiona Enter para volver al menú...")
    try:
        input()
    except EOFError:
        pass

if __name__ == "__main__":
    main()
