# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE
# MENÚ PRINCIPAL - EJECUTOR DE ETAPAS (DÍA 1 AL DÍA 6)
# ==========================================================

import os
import sys

def limpiar_pantalla():
    os.system('cls' if os.name == 'nt' else 'clear')

def mostrar_banner():
    print("=" * 65)
    print("      🌟 PROBADOR VIRTUAL INTELIGENTE - MENÚ DE ETAPAS 🌟      ")
    print("=" * 65)
    print(" Selecciona qué etapa / día deseas ejecutar:")
    print("-" * 65)
    print("  [1] DÍA 1: Cámara y OpenCV (Captura básica, FPS y espejo)")
    print("  [2] DÍA 2: Puntos Clave MediaPipe (Detección de 33 landmarks)")
    print("  [3] DÍA 3: Esqueleto Visual y Medidas (Huesos y cálculos)")
    print("  [4] DÍA 4: Creación de Prendas PNG (Generación con canal Alfa)")
    print("  [5] DÍA 5: Inspección de Canal Alfa (Transparencia RGBA)")
    print("  [6] DÍA 6: 👗 VESTIDOR VIRTUAL FEMENINO (Galería Boutique + Probador en Vivo)")
    print("  [A] Ejecutar demostración completa paso a paso (Día 1 al 6)")
    print("  [0] Salir")
    print("=" * 65)

def ejecutar_dia(opcion):
    if opcion == "1":
        import dia1_camara
        dia1_camara.main()
    elif opcion == "2":
        import dia2_mediapipe_basico
        dia2_mediapipe_basico.main()
    elif opcion == "3":
        import dia3_esqueleto
        dia3_esqueleto.main()
    elif opcion == "4":
        import dia4_crear_prendas
        dia4_crear_prendas.main()
    elif opcion == "5":
        import dia5_canal_alfa
        dia5_canal_alfa.main()
    elif opcion == "6":
        import main as probador_final
        probador_final.main()
    elif opcion.upper() == "A":
        print("\n--- INICIANDO DÍA 1 ---")
        import dia1_camara
        dia1_camara.main()
        print("\n--- INICIANDO DÍA 2 ---")
        import dia2_mediapipe_basico
        dia2_mediapipe_basico.main()
        print("\n--- INICIANDO DÍA 3 ---")
        import dia3_esqueleto
        dia3_esqueleto.main()
        print("\n--- INICIANDO DÍA 4 ---")
        import dia4_crear_prendas
        dia4_crear_prendas.main()
        print("\n--- INICIANDO DÍA 5 ---")
        import dia5_canal_alfa
        dia5_canal_alfa.main()
        print("\n--- INICIANDO DÍA 6: PROBADOR VIRTUAL ---")
        import main as probador_final
        probador_final.main()

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # tildes bien aunque se redirija la salida
    except Exception:
        pass
    while True:
        limpiar_pantalla()
        mostrar_banner()
        opcion = input(" Ingresa tu opción (1-6, A o 0): ").strip()
        
        if opcion == "0":
            print("\n¡Gracias por usar el Probador Virtual Inteligente! Hasta luego.\n")
            break
        elif opcion in ["1", "2", "3", "4", "5", "6", "a", "A"]:
            try:
                ejecutar_dia(opcion)
            except Exception as e:
                print(f"\n[ERROR durante la ejecución]: {e}")
                print("Presiona Enter para continuar...")
                try:
                    input()
                except EOFError:
                    pass
        else:
            print("\n[!] Opción no válida. Por favor selecciona un número del 1 al 6, o 0 para salir.")
            print("Presiona Enter para continuar...")
            try:
                input()
            except EOFError:
                pass

if __name__ == "__main__":
    main()
