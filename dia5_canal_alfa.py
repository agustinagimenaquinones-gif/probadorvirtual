# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# DÍA 5 / ETAPA 5: Inspección y Fusión del Canal Alfa
# ==========================================================

import os
from ver_prenda import inspeccionar_prenda

def main():
    print("=" * 60)
    print("   DÍA 5: INSPECCIÓN DE PRENDAS Y CANAL ALFA (BGRA)   ")
    print("=" * 60)
    print("Objetivo: Entender cómo funciona el canal Alfa para superposición.")
    print("Mostrando prenda sobre patrón de ajedrez...\n")

    ruta_remera = os.path.join("prendas", "remera_azul.png")
    if not os.path.exists(ruta_remera):
        from crear_prendas import generar_catalogo_inicial
        generar_catalogo_inicial()

    inspeccionar_prenda(ruta_remera)

if __name__ == "__main__":
    main()
