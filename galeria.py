# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - VESTIDOR VIRTUAL
# MÓDULO: GALERÍA (interfaz Tkinter: catálogo, detalle, compra y cuenta del cliente)
# ==========================================================

import datetime
import gc
import math

import cv2
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, messagebox

from catalogo import (
    cargar_catalogo_completo,
    holgura_de_talle,
    talle_inicial,
    obtener_medidas_talle,
    obtener_guia_medidas_completa
)
from colores_prenda import CacheColores
from recursos import asegurar_recursos
from probador_camara import ejecutar_probador_camara
from config import (
    COLOR_BG_APP,
    COLOR_HEADER_BG,
    COLOR_CARD_BG,
    COLOR_CARD_BORDER,
    COLOR_CARD_HOVER,
    COLOR_TEXT_MAIN,
    COLOR_TEXT_MUTED,
    COLOR_GOLD,
    COLOR_ROSE,
    COLOR_ROSE_HOVER,
    COLOR_TAG_BG,
)

# Filtros de la galería: (texto del botón, función que decide si la prenda entra)
FILTROS = [
    ("Todo", lambda p, fav: True),
    ("Mujer", lambda p, fav: p.get("genero") in ("mujer", "unisex")),
    ("Hombre", lambda p, fav: p.get("genero") in ("hombre", "unisex")),
    ("Remeras", lambda p, fav: p.get("categoria") == "Remeras"),
    ("Tops", lambda p, fav: p.get("categoria") == "Tops"),
    ("Chombas", lambda p, fav: p.get("categoria") == "Chombas"),
    ("Buzos", lambda p, fav: p.get("categoria") == "Buzos"),
    ("♥ Favoritos", lambda p, fav: p.get("id") in fav),
]
POCO_STOCK = 2  # "¡Últimas unidades!" con esta cantidad o menos


def precio_str(valor):
    return f"${int(round(float(valor))):,}".replace(",", ".")


def colores_de(prenda):
    """Colores de la prenda; sin MySQL hay uno solo (el de la foto)."""
    return prenda.get("colores") or [{"nombre": prenda.get("color", "Único"), "hex": None, "es_foto": True}]


def stock_de(prenda, color=None, talle=None):
    """Unidades disponibles (de un color y/o talle). None si no se conoce (sin MySQL)."""
    stock = prenda.get("stock")
    if stock is None:
        return None
    return sum(n for (c, t), n in stock.items() if (color is None or c == color) and (talle is None or t == talle))


# =========================================================================
# INTERFAZ GRÁFICA TKINTER: VESTIDOR VIRTUAL
# =========================================================================
class BoutiqueVirtualApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vestidor Virtual - Probador Inteligente")
        self.root.geometry("1240x820")
        self.root.minsize(1040, 720)
        self.root.configure(bg=COLOR_BG_APP)
        self.centrar_ventana(1240, 820)

        # Asegurar recursos y cargar prendas
        asegurar_recursos()
        self.catalogo = cargar_catalogo_completo()
        self.fotos_tk_cache = {}  # Cache para evitar recolección de basura de PhotoImage
        self.colores_cache = CacheColores()
        self.prenda_seleccionada = None
        self.talle_seleccionado = tk.StringVar(value="M")
        self.color_seleccionado = tk.StringVar(value="")
        self.filtro_actual = "Todo"
        self.cliente = None
        self._animacion = None

        self.contenedor_principal = tk.Frame(self.root, bg=COLOR_BG_APP)
        self.contenedor_principal.pack(fill=tk.BOTH, expand=True)
        self.mostrar_galeria()

    def centrar_ventana(self, ancho, alto):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{ancho}x{alto}+{max(0, (sw - ancho) // 2)}+{max(0, (sh - alto) // 2)}")

    def limpiar_contenedor(self):
        if self._animacion:
            self.root.after_cancel(self._animacion)
            self._animacion = None
        for widget in self.contenedor_principal.winfo_children():
            widget.destroy()

    # ---------------------------------------------------------------------
    # IMÁGENES (con el color elegido)
    # ---------------------------------------------------------------------
    def imagen_rgba(self, prenda, color=None, espalda=False):
        """Imagen de la prenda (BGRA, ya limpia) en el color pedido."""
        img = prenda.get("imagen_espalda_cv" if espalda else "imagen_cv")
        if img is None:
            img = cv2.imread(prenda["archivo"], cv2.IMREAD_UNCHANGED)
        datos = next((c for c in colores_de(prenda) if c["nombre"] == color), None)
        if datos and not datos.get("es_foto") and datos.get("hex"):
            img = self.colores_cache.obtener(prenda["id"], img, datos["hex"])
        return img

    def obtener_imagen_tk(self, prenda, tamano=(190, 190), color=None, espalda=False, escala_x=1.0):
        """Foto de la prenda reescalada con alta calidad para Tkinter (con cache)."""
        clave = (prenda["id"], color, espalda, tamano, round(escala_x, 2))
        if clave in self.fotos_tk_cache:
            return self.fotos_tk_cache[clave]
        try:
            bgra = self.imagen_rgba(prenda, color, espalda)
            img = Image.fromarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA))
            img.thumbnail(tamano, Image.Resampling.LANCZOS)
            if escala_x < 0.999:  # vista 360: la prenda "gira" achicándose de costado
                img = img.resize((max(1, int(img.width * escala_x)), img.height), Image.Resampling.BILINEAR)
            lienzo = Image.new("RGBA", tamano, (255, 255, 255, 0))
            lienzo.paste(img, ((tamano[0] - img.width) // 2, (tamano[1] - img.height) // 2), img)
            foto_tk = ImageTk.PhotoImage(lienzo)
            if len(self.fotos_tk_cache) > 400:
                self.fotos_tk_cache.clear()
            self.fotos_tk_cache[clave] = foto_tk
            return foto_tk
        except Exception as e:
            print(f"[AVISO] Error cargando imagen para Tkinter: {e}")
            return None

    # ---------------------------------------------------------------------
    # CABECERA (marca + cuenta del cliente)
    # ---------------------------------------------------------------------
    def crear_cabecera(self, parent):
        header = tk.Frame(parent, bg=COLOR_HEADER_BG, pady=14)
        header.pack(fill=tk.X, side=tk.TOP)
        barra = tk.Frame(header, bg=COLOR_HEADER_BG)
        barra.pack(fill=tk.X, padx=28)

        marca = tk.Frame(barra, bg=COLOR_HEADER_BG)
        marca.pack(side=tk.LEFT)
        tk.Label(marca, text="V E S T I D O R   V I R T U A L", font=("Segoe UI", 10, "bold"),
                 fg=COLOR_GOLD, bg=COLOR_HEADER_BG).pack(anchor="w")
        tk.Label(marca, text="Probá cada prenda en vivo, a tu medida", font=("Georgia", 20, "bold"),
                 fg=COLOR_TEXT_MAIN, bg=COLOR_HEADER_BG).pack(anchor="w")
        tk.Label(marca, text="Colección minimalista para mujer y hombre · probador con cámara y calce 3D",
                 font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_HEADER_BG).pack(anchor="w")

        cuenta = tk.Frame(barra, bg=COLOR_HEADER_BG)
        cuenta.pack(side=tk.RIGHT)
        if self.cliente:
            c = self.cliente
            tk.Label(cuenta, text=f"Hola, {c['nombre']} ✨", font=("Segoe UI", 11, "bold"),
                     fg=COLOR_TEXT_MAIN, bg=COLOR_HEADER_BG).pack(anchor="e")
            tk.Label(cuenta, text=f"Nivel {c['nivel']} · {c['puntos']} puntos · {len(c['cupones'])} cupones",
                     font=("Segoe UI", 9), fg=COLOR_GOLD, bg=COLOR_HEADER_BG).pack(anchor="e")
            texto = "MI CUENTA"
        else:
            tk.Label(cuenta, text="Registrate y llevate 15% OFF en tu primera compra",
                     font=("Segoe UI", 9, "bold"), fg=COLOR_ROSE, bg=COLOR_HEADER_BG).pack(anchor="e")
            texto = "INGRESAR / REGISTRARME"
        self.boton(cuenta, texto, self.mostrar_cuenta, color=COLOR_TEXT_MAIN, hover="#4A3F3B",
                   tam=9).pack(anchor="e", pady=(4, 0))
        tk.Frame(header, height=1, bg=COLOR_CARD_BORDER).pack(fill=tk.X, pady=(12, 0))

    def boton(self, parent, texto, comando, color=COLOR_ROSE, hover=COLOR_ROSE_HOVER, tam=10, fg="#FFFFFF",
              padx=18, pady=7, estado=tk.NORMAL):
        b = tk.Button(parent, text=texto, font=("Segoe UI", tam, "bold"), fg=fg, bg=color, activeforeground=fg,
                      activebackground=hover, relief=tk.FLAT, bd=0, padx=padx, pady=pady, cursor="hand2",
                      command=comando, state=estado, disabledforeground="#BDB3AE")
        if estado == tk.NORMAL:
            b.bind("<Enter>", lambda e: b.config(bg=hover))
            b.bind("<Leave>", lambda e: b.config(bg=color))
        return b

    # ---------------------------------------------------------------------
    # VISTA 1: GALERÍA DE PRENDAS
    # ---------------------------------------------------------------------
    def mostrar_galeria(self):
        self.limpiar_contenedor()
        self.crear_cabecera(self.contenedor_principal)

        # Filtros
        barra_filtros = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        barra_filtros.pack(fill=tk.X, padx=30, pady=(12, 0))
        favoritos = self.cliente["favoritos"] if self.cliente else set()
        for nombre, _ in FILTROS:
            activo = nombre == self.filtro_actual
            b = tk.Button(barra_filtros, text=nombre, font=("Segoe UI", 9, "bold"),
                          fg="#FFFFFF" if activo else COLOR_TEXT_MAIN, bg=COLOR_TEXT_MAIN if activo else COLOR_TAG_BG,
                          activebackground=COLOR_CARD_HOVER, relief=tk.FLAT, bd=0, padx=14, pady=5, cursor="hand2",
                          command=lambda n=nombre: self.cambiar_filtro(n))
            b.pack(side=tk.LEFT, padx=(0, 6))
        visibles = [p for p in self.catalogo if dict(FILTROS)[self.filtro_actual](p, favoritos)]
        tk.Label(barra_filtros, text=f"{len(visibles)} prendas", font=("Segoe UI", 9),
                 fg=COLOR_TEXT_MUTED, bg=COLOR_BG_APP).pack(side=tk.RIGHT)

        # Área desplazable
        canvas_contenedor = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        canvas_contenedor.pack(fill=tk.BOTH, expand=True, padx=25, pady=10)
        # Desplazamiento de a 30 px por paso de la rueda (suave, sin saltos grandes)
        canvas = tk.Canvas(canvas_contenedor, bg=COLOR_BG_APP, highlightthickness=0, yscrollincrement=30)
        scrollbar = ttk.Scrollbar(canvas_contenedor, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLOR_BG_APP)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        def desplazar(evento):
            if not canvas.winfo_exists():
                return
            pasos = -1 if evento.delta > 0 else 1
            canvas.yview_scroll(pasos * max(1, abs(evento.delta) // 120), "units")
            canvas.update_idletasks()  # redibujar ya: las tarjetas no quedan "arrastradas"
        canvas.bind_all("<MouseWheel>", desplazar)

        grid_frame = tk.Frame(scrollable_frame, bg=COLOR_BG_APP)
        grid_frame.pack(anchor="center", pady=6)
        if not visibles:
            mensaje = ("Todavía no hay buzos en el catálogo: pronto llegan."
                       if self.filtro_actual == "Buzos" else "No hay prendas en esta sección.")
            tk.Label(grid_frame, text=mensaje, font=("Segoe UI", 12), fg=COLOR_TEXT_MUTED,
                     bg=COLOR_BG_APP, pady=60).pack()
        for idx, prenda in enumerate(visibles):
            self.crear_tarjeta_prenda(grid_frame, prenda, idx // 4, idx % 4)

    def cambiar_filtro(self, nombre):
        if nombre == "♥ Favoritos" and not self.cliente:
            messagebox.showinfo("Favoritos", "Ingresá a tu cuenta para guardar y ver tus favoritos.")
            return
        self.filtro_actual = nombre
        self.mostrar_galeria()

    def crear_tarjeta_prenda(self, parent, prenda, fila, col):
        # El borde tiene siempre el mismo grosor y al pasar el mouse sólo cambia de color:
        # si cambiara de tamaño, al deslizar la galería las tarjetas "saltarían"
        card = tk.Frame(parent, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER, highlightthickness=2,
                        padx=14, pady=12)
        card.grid(row=fila, column=col, padx=9, pady=10, sticky="nsew")
        card.bind("<Enter>", lambda e: card.config(highlightbackground=COLOR_CARD_HOVER))
        card.bind("<Leave>", lambda e: card.config(highlightbackground=COLOR_CARD_BORDER))

        arriba = tk.Frame(card, bg=COLOR_CARD_BG)
        arriba.pack(fill=tk.X)
        tk.Label(arriba, text=prenda.get("sku", ""), font=("Consolas", 8), fg=COLOR_TEXT_MUTED,
                 bg=COLOR_CARD_BG).pack(side=tk.LEFT)
        disponible = stock_de(prenda)
        if disponible is not None:
            if disponible == 0:
                etiqueta, color = "AGOTADO", "#A35848"
            elif any(0 < n <= POCO_STOCK for n in prenda["stock"].values()):
                etiqueta, color = "¡ÚLTIMAS UNIDADES!", COLOR_ROSE
            else:
                etiqueta, color = "EN STOCK", "#6E8B6A"
            tk.Label(arriba, text=etiqueta, font=("Segoe UI", 7, "bold"), fg=color, bg=COLOR_CARD_BG).pack(side=tk.RIGHT)

        foto_tk = self.obtener_imagen_tk(prenda, tamano=(200, 200), color=colores_de(prenda)[0]["nombre"])
        if foto_tk:
            lbl_img = tk.Label(card, image=foto_tk, bg=COLOR_CARD_BG, cursor="hand2")
            lbl_img.image = foto_tk
            lbl_img.pack(pady=(4, 8))
            lbl_img.bind("<Button-1>", lambda e, p=prenda: self.mostrar_confirmacion(p))

        tk.Label(card, text=prenda["nombre"], font=("Segoe UI", 11, "bold"), fg=COLOR_TEXT_MAIN,
                 bg=COLOR_CARD_BG, wraplength=210).pack()
        tk.Label(card, text=precio_str(prenda["precio"]), font=("Segoe UI", 13, "bold"), fg=COLOR_GOLD,
                 bg=COLOR_CARD_BG).pack(pady=(0, 4))
        self.crear_muestras_color(card, prenda, tam=14).pack(pady=(0, 4))
        tk.Label(card, text=f"{prenda.get('categoria', '')} · {' · '.join(prenda['talles'])}",
                 font=("Segoe UI", 8, "bold"), fg="#9E786B", bg=COLOR_TAG_BG, padx=8, pady=2).pack(pady=(2, 8))

        botones = tk.Frame(card, bg=COLOR_CARD_BG)
        botones.pack(fill=tk.X)
        self.boton(botones, "VER Y PROBAR", lambda p=prenda: self.mostrar_confirmacion(p), pady=6
                   ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        es_fav = bool(self.cliente) and prenda["id"] in self.cliente["favoritos"]
        tk.Button(botones, text="♥" if es_fav else "♡", font=("Segoe UI", 12), fg=COLOR_ROSE, bg=COLOR_CARD_BG,
                  relief=tk.FLAT, bd=0, cursor="hand2", command=lambda p=prenda: self.alternar_favorito(p)
                  ).pack(side=tk.LEFT, padx=(6, 0))

    def crear_muestras_color(self, parent, prenda, tam=14, al_elegir=None, elegido=None):
        """Circulitos con los colores disponibles (clic para elegir, si se pasa al_elegir)."""
        marco = tk.Frame(parent, bg=parent["bg"])
        for c in colores_de(prenda):
            sin_stock = stock_de(prenda, color=c["nombre"]) == 0
            lienzo = tk.Canvas(marco, width=tam + 6, height=tam + 6, bg=parent["bg"], highlightthickness=0,
                               cursor="hand2" if al_elegir else "")
            borde = COLOR_TEXT_MAIN if c["nombre"] == elegido else "#CFC6C0"
            lienzo.create_oval(3, 3, tam + 3, tam + 3, fill=c.get("hex") or "#CCCCCC", outline=borde,
                               width=2 if c["nombre"] == elegido else 1)
            if sin_stock:
                lienzo.create_line(3, tam + 3, tam + 3, 3, fill="#A35848", width=2)
            lienzo.pack(side=tk.LEFT, padx=2)
            if al_elegir:
                lienzo.bind("<Button-1>", lambda e, n=c["nombre"]: al_elegir(n))
        return marco

    def alternar_favorito(self, prenda):
        if not self.cliente:
            messagebox.showinfo("Favoritos", "Ingresá a tu cuenta para guardar tus prendas favoritas.")
            return
        try:
            import tienda
            quedo = tienda.alternar_favorito(self.cliente["id_cliente"], prenda["id_prenda"])
        except Exception as e:
            messagebox.showerror("Favoritos", f"No se pudo guardar: {e}")
            return
        (self.cliente["favoritos"].add if quedo else self.cliente["favoritos"].discard)(prenda["id"])
        self.mostrar_galeria()

    # ---------------------------------------------------------------------
    # VISTA 2: DETALLE (colores, talles con stock, vista 360°, probar y comprar)
    # ---------------------------------------------------------------------
    def mostrar_confirmacion(self, prenda):
        self.prenda_seleccionada = prenda
        self.limpiar_contenedor()
        if self.color_seleccionado.get() not in [c["nombre"] for c in colores_de(prenda)]:
            self.color_seleccionado.set(colores_de(prenda)[0]["nombre"])

        contenedor = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        contenedor.pack(expand=True, fill=tk.BOTH, padx=25, pady=16)
        tarjeta = tk.Frame(contenedor, bg=COLOR_CARD_BG, highlightbackground=COLOR_CARD_BORDER,
                           highlightthickness=1, padx=32, pady=20)
        tarjeta.pack(anchor="center", expand=True)

        tk.Label(tarjeta, text=f"VESTIDOR VIRTUAL · {prenda.get('sku', '')} · {prenda.get('categoria', '').upper()}",
                 font=("Segoe UI", 9, "bold"), fg=COLOR_GOLD, bg=COLOR_CARD_BG).pack()
        tk.Label(tarjeta, text=prenda["nombre"], font=("Georgia", 19, "bold"), fg=COLOR_TEXT_MAIN,
                 bg=COLOR_CARD_BG).pack(pady=(0, 10))

        columnas = tk.Frame(tarjeta, bg=COLOR_CARD_BG)
        columnas.pack(fill=tk.BOTH, expand=True)

        # --- Izquierda: vista 360° animada ---
        col_izq = tk.Frame(columnas, bg=COLOR_CARD_BG)
        col_izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 24))
        marco = tk.Frame(col_izq, bg="#F9F6F3", highlightbackground=COLOR_CARD_BORDER, highlightthickness=1,
                         padx=6, pady=6)
        marco.pack()
        lbl_foto = tk.Label(marco, bg="#F9F6F3")
        lbl_foto.pack()
        lbl_vista = tk.Label(col_izq, text="", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG)
        lbl_vista.pack(pady=(4, 0))
        girando = tk.BooleanVar(value=True)
        tk.Checkbutton(col_izq, text="Vista 360° (frente y espalda)", variable=girando, font=("Segoe UI", 9),
                       bg=COLOR_CARD_BG, activebackground=COLOR_CARD_BG, fg=COLOR_TEXT_MAIN).pack()
        tk.Label(col_izq, text=precio_str(prenda["precio"]), font=("Segoe UI", 18, "bold"), fg=COLOR_GOLD,
                 bg=COLOR_CARD_BG).pack(pady=(6, 0))
        if self.cliente and float(self.cliente["descuento_pct"]) > 0:
            con_desc = prenda["precio"] * (1 - float(self.cliente["descuento_pct"]) / 100)
            tk.Label(col_izq, text=f"Con tu nivel {self.cliente['nivel']}: {precio_str(con_desc)}",
                     font=("Segoe UI", 9, "bold"), fg=COLOR_ROSE, bg=COLOR_CARD_BG).pack()

        angulo = [0.0]

        def animar():
            if not lbl_foto.winfo_exists():
                return
            if girando.get():
                angulo[0] = (angulo[0] + 6) % 360
            a = math.radians(angulo[0])
            espalda = math.cos(a) < 0
            escala = max(0.06, abs(math.cos(a)))
            escala = round(escala * 20) / 20  # pasos de 5%: menos imágenes distintas en la cache
            foto = self.obtener_imagen_tk(prenda, (260, 260), self.color_seleccionado.get(), espalda, escala)
            if foto:
                lbl_foto.config(image=foto)
                lbl_foto.image = foto
            lbl_vista.config(text="Espalda" if espalda else "Frente")
            self._animacion = self.root.after(70, animar)

        # --- Derecha: descripción, color, talle, medidas y acciones ---
        col_der = tk.Frame(columnas, bg=COLOR_CARD_BG)
        col_der.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(col_der, text=prenda.get("descripcion", ""), font=("Segoe UI", 10, "italic"), fg=COLOR_TEXT_MUTED,
                 bg=COLOR_CARD_BG, wraplength=500, justify="left").pack(anchor="w", pady=(0, 8))

        tk.Label(col_der, text="1. Elegí el color:", font=("Segoe UI", 11, "bold"), fg=COLOR_TEXT_MAIN,
                 bg=COLOR_CARD_BG).pack(anchor="w")
        fila_color = tk.Frame(col_der, bg=COLOR_CARD_BG)
        fila_color.pack(anchor="w", pady=(2, 8))
        lbl_color = tk.Label(fila_color, text="", font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG)

        tk.Label(col_der, text="2. Elegí tu talle:", font=("Segoe UI", 11, "bold"), fg=COLOR_TEXT_MAIN,
                 bg=COLOR_CARD_BG).pack(anchor="w")
        talles_bar = tk.Frame(col_der, bg=COLOR_CARD_BG)
        talles_bar.pack(anchor="w", pady=(2, 4))
        lbl_stock = tk.Label(col_der, text="", font=("Segoe UI", 9, "bold"), bg=COLOR_CARD_BG)
        lbl_stock.pack(anchor="w", pady=(0, 6))

        medidas_box = tk.Frame(col_der, bg="#FAF6F0", highlightbackground="#E2D5C8", highlightthickness=1,
                               padx=12, pady=8)
        medidas_box.pack(fill=tk.X, pady=(0, 8))
        lbl_medidas = tk.Label(medidas_box, text="", font=("Segoe UI", 9), fg="#7E5835", bg="#FAF6F0",
                               justify="left")
        lbl_medidas.pack(anchor="w")

        def refrescar():
            color = self.color_seleccionado.get()
            for w in fila_color.winfo_children():
                w.destroy()
            self.crear_muestras_color(fila_color, prenda, tam=22, al_elegir=elegir_color, elegido=color
                                      ).pack(side=tk.LEFT)
            tk.Label(fila_color, text=color, font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED,
                     bg=COLOR_CARD_BG).pack(side=tk.LEFT, padx=8)
            for w in talles_bar.winfo_children():
                w.destroy()
            if self.talle_seleccionado.get() not in prenda["talles"]:
                self.talle_seleccionado.set(talle_inicial(prenda, self.talle_seleccionado.get()))
            for t in prenda["talles"]:
                n = stock_de(prenda, color, t)
                rb = tk.Radiobutton(talles_bar, text=t, value=t, variable=self.talle_seleccionado, indicatoron=False,
                                    width=5, font=("Segoe UI", 11, "bold" if n != 0 else "overstrike"),
                                    fg=COLOR_TEXT_MAIN if n != 0 else "#B5A9A3", bg=COLOR_TAG_BG,
                                    selectcolor=COLOR_ROSE, relief=tk.FLAT, bd=0, pady=5, cursor="hand2",
                                    command=refrescar)
                rb.pack(side=tk.LEFT, padx=3)
            self.boton(talles_bar, "📏 Guía de medidas", lambda: self.mostrar_tabla_medidas_modal(prenda),
                       color="#F0E5D8", hover="#E5D6C5", fg="#7E5835", tam=9, padx=10, pady=5
                       ).pack(side=tk.LEFT, padx=(10, 0))
            t = self.talle_seleccionado.get()
            n = stock_de(prenda, color, t)
            if n is None:
                lbl_stock.config(text="Stock: consultá en la tienda (sin conexión a la base).", fg=COLOR_TEXT_MUTED)
            elif n == 0:
                lbl_stock.config(text=f"Sin stock en {color} talle {t}. Probá otro color o talle.", fg="#A35848")
            elif n <= POCO_STOCK:
                lbl_stock.config(text=f"¡Últimas {n} unidades en {color} talle {t}!", fg=COLOR_ROSE)
            else:
                lbl_stock.config(text=f"{n} unidades disponibles en {color} talle {t}.", fg="#6E8B6A")
            m = obtener_medidas_talle(prenda, t)
            h_pct = int(round((holgura_de_talle(t) - 1.0) * 100))
            lbl_medidas.config(text=f"📐 Talle {t}:  pecho {m['pecho']} cm · cintura {m['cintura']} cm · "
                                    f"cadera {m['cadera']} cm · hombros {m['hombros']} cm · largo {m['largo']} cm"
                                    f"   |   calce {prenda.get('calce', 'regular')} ({h_pct:+d}% holgura)")
            btn_comprar.config(state=tk.NORMAL if n else tk.DISABLED)

        def elegir_color(nombre):
            self.color_seleccionado.set(nombre)
            refrescar()

        tk.Label(col_der, text="💡 La cámara mide tu silueta (pecho, cintura y cadera) y ajusta la prenda a tu "
                                "cuerpo en el color y talle elegidos. En la cámara: [K] cambia el color, [T] el talle.",
                 font=("Segoe UI", 9), fg="#8C7F79", bg=COLOR_TAG_BG, padx=12, pady=7, wraplength=500,
                 justify="left").pack(anchor="w", pady=(0, 12))

        botones = tk.Frame(col_der, bg=COLOR_CARD_BG)
        botones.pack(anchor="w")
        self.boton(botones, "⭐ PROBAR EN CÁMARA", self.lanzar_camara, color=COLOR_GOLD, hover="#A8853F", tam=11,
                   padx=24, pady=9).grid(row=0, column=0, padx=(0, 10))
        btn_comprar = self.boton(botones, "🛍 COMPRAR", lambda: self.mostrar_compra(prenda), tam=11, padx=24, pady=9)
        btn_comprar.grid(row=0, column=1, padx=(0, 10))
        self.boton(botones, "← GALERÍA", self.mostrar_galeria, color="#F2EBE5", hover="#E5DCD4",
                   fg=COLOR_TEXT_MAIN, tam=11, pady=9).grid(row=0, column=2)

        refrescar()
        animar()

    def mostrar_tabla_medidas_modal(self, prenda):
        """Modal con la tabla de medidas de todos los talles de la prenda."""
        modal = tk.Toplevel(self.root)
        modal.title(f"Guía de medidas - {prenda['nombre']}")
        modal.configure(bg=COLOR_BG_APP)
        modal.transient(self.root)
        modal.grab_set()
        f = tk.Frame(modal, bg=COLOR_CARD_BG, padx=25, pady=18)
        f.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        tk.Label(f, text="📏 TABLA DE MEDIDAS Y GUÍA DE CALCE", font=("Segoe UI", 11, "bold"),
                 fg=COLOR_GOLD, bg=COLOR_CARD_BG).pack()
        tk.Label(f, text=prenda["nombre"], font=("Georgia", 16, "bold"), fg=COLOR_TEXT_MAIN,
                 bg=COLOR_CARD_BG, pady=3).pack(pady=(0, 10))
        tabla = tk.Frame(f, bg=COLOR_CARD_BORDER, padx=1, pady=1)
        tabla.pack(fill=tk.X, pady=(0, 14))
        cabeceras = ["Talle", "Pecho / Busto", "Cintura", "Cadera", "Hombros", "Largo Total", "Calce"]
        for col, h in enumerate(cabeceras):
            tk.Label(tabla, text=h, font=("Segoe UI", 10, "bold"), bg="#EAE0D6", fg=COLOR_TEXT_MAIN,
                     padx=8, pady=7).grid(row=0, column=col, sticky="nsew", padx=1, pady=1)
        actual = self.talle_seleccionado.get()
        for fila, datos in enumerate(obtener_guia_medidas_completa(prenda), start=1):
            sel = datos["talle"] == actual
            fondo = "#F5E6E0" if sel else ("#FFFFFF" if fila % 2 else "#FAF7F5")
            valores = [datos["talle"] + (" ★" if sel else ""), datos["pecho"], datos["cintura"], datos["cadera"],
                       datos["hombros"], datos["largo"], datos["calce"]]
            for col, v in enumerate(valores):
                tk.Label(tabla, text=v, font=("Segoe UI", 9, "bold" if sel or col == 0 else "normal"), bg=fondo,
                         fg=COLOR_TEXT_MAIN, padx=8, pady=6).grid(row=fila, column=col, sticky="nsew", padx=1, pady=1)
        tk.Label(f, text="• Pecho: rodeá la parte más ancha del torso.\n• Cintura: el punto más angosto, a la altura "
                         "del ombligo.\n• Cadera: de pie, en la parte más amplia.", font=("Segoe UI", 9),
                 fg=COLOR_TEXT_MUTED, bg=COLOR_TAG_BG, justify="left", padx=12, pady=8).pack(fill=tk.X, pady=(0, 12))
        self.boton(f, "ENTENDIDO", modal.destroy).pack()

    # ---------------------------------------------------------------------
    # CUENTA DEL CLIENTE (ingreso, registro y beneficios)
    # ---------------------------------------------------------------------
    def mostrar_cuenta(self, al_terminar=None):
        modal = tk.Toplevel(self.root)
        modal.title("Mi cuenta - Vestidor Virtual")
        modal.configure(bg=COLOR_BG_APP)
        modal.transient(self.root)
        modal.grab_set()
        f = tk.Frame(modal, bg=COLOR_CARD_BG, padx=28, pady=20)
        f.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        if self.cliente:
            c = self.cliente
            tk.Label(f, text=f"{c['nombre']} {c.get('apellido') or ''}", font=("Georgia", 17, "bold"),
                     fg=COLOR_TEXT_MAIN, bg=COLOR_CARD_BG).pack(anchor="w")
            tk.Label(f, text=c["email"], font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG).pack(anchor="w")
            caja = tk.Frame(f, bg="#FAF6F0", padx=14, pady=10)
            caja.pack(fill=tk.X, pady=10)
            tk.Label(caja, text=f"⭐ Nivel {c['nivel']}  ·  {c['puntos']} puntos (= {precio_str(c['puntos'])})",
                     font=("Segoe UI", 11, "bold"), fg="#7E5835", bg="#FAF6F0").pack(anchor="w")
            tk.Label(caja, text=c.get("beneficio") or "", font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED,
                     bg="#FAF6F0").pack(anchor="w")
            if c["siguiente_nivel"]:
                tk.Label(caja, text=f"Te faltan {precio_str(c['falta_para_siguiente'])} en compras para llegar a "
                                    f"{c['siguiente_nivel']}.", font=("Segoe UI", 9, "bold"), fg=COLOR_ROSE,
                         bg="#FAF6F0").pack(anchor="w", pady=(4, 0))
            tk.Label(f, text="Tus cupones:", font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT_MAIN,
                     bg=COLOR_CARD_BG).pack(anchor="w")
            if not c["cupones"]:
                tk.Label(f, text="No tenés cupones activos.", font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED,
                         bg=COLOR_CARD_BG).pack(anchor="w")
            for cupon in c["cupones"]:
                vence = f" · vence {cupon['vence']:%d/%m/%Y}" if cupon.get("vence") else ""
                tk.Label(f, text=f"🎟  {cupon['codigo']} — {cupon['descripcion']}{vence}", font=("Segoe UI", 9),
                         fg=COLOR_TEXT_MAIN, bg=COLOR_TAG_BG, padx=8, pady=3).pack(anchor="w", pady=2, fill=tk.X)
            fila = tk.Frame(f, bg=COLOR_CARD_BG)
            fila.pack(pady=(14, 0))
            self.boton(fila, "CERRAR", modal.destroy).pack(side=tk.LEFT, padx=4)

            def salir():
                self.cliente = None
                modal.destroy()
                self.mostrar_galeria()
            self.boton(fila, "SALIR DE MI CUENTA", salir, color="#F2EBE5", hover="#E5DCD4",
                       fg=COLOR_TEXT_MAIN).pack(side=tk.LEFT, padx=4)
            return

        tk.Label(f, text="Sumate al Club Vestidor Virtual", font=("Georgia", 17, "bold"), fg=COLOR_TEXT_MAIN,
                 bg=COLOR_CARD_BG).pack(anchor="w")
        tk.Label(f, text="15% OFF de bienvenida · puntos en cada compra · regalo de cumpleaños · "
                         "descuentos por nivel (Plata 5%, Oro 10%, Diamante 15%)", font=("Segoe UI", 9),
                 fg=COLOR_ROSE, bg=COLOR_CARD_BG, wraplength=460, justify="left").pack(anchor="w", pady=(2, 10))
        campos = {}
        etiquetas = [("email", "Email *"), ("nombre", "Nombre * (si es tu primera vez)"), ("apellido", "Apellido"),
                     ("telefono", "Teléfono"), ("nacimiento", "Fecha de nacimiento (dd/mm/aaaa)"),
                     ("talle", "Talle preferido")]
        for clave, texto in etiquetas:
            tk.Label(f, text=texto, font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT_MAIN, bg=COLOR_CARD_BG).pack(anchor="w")
            e = tk.Entry(f, font=("Segoe UI", 10), width=42, relief=tk.SOLID, bd=1)
            e.pack(anchor="w", pady=(0, 6), ipady=3)
            campos[clave] = e
        acepta = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Quiero recibir novedades y promociones por email.", variable=acepta,
                       font=("Segoe UI", 9), bg=COLOR_CARD_BG, activebackground=COLOR_CARD_BG).pack(anchor="w")
        tk.Label(f, text="Tus datos se guardan sólo para tu cuenta de cliente y tus beneficios. No guardamos fotos "
                         "ni videos de la cámara.", font=("Segoe UI", 8), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG,
                 wraplength=460, justify="left").pack(anchor="w", pady=(2, 10))

        def ingresar():
            import tienda
            email = campos["email"].get().strip()
            try:
                cliente = tienda.buscar_cliente(email) if tienda.email_valido(email) else None
                if cliente is None:
                    nacimiento = None
                    texto = campos["nacimiento"].get().strip()
                    if texto:
                        try:
                            nacimiento = datetime.datetime.strptime(texto, "%d/%m/%Y").date()
                        except ValueError:
                            raise tienda.ErrorTienda("La fecha de nacimiento tiene que ser dd/mm/aaaa.")
                    cliente = tienda.registrar_cliente(
                        campos["nombre"].get(), email, campos["apellido"].get(), campos["telefono"].get(),
                        nacimiento, campos["talle"].get().strip().upper() or None, acepta.get())
                    bienvenida = f"¡Bienvenida/o, {cliente['nombre']}! Te regalamos un cupón del 15% para tu primera compra."
                else:
                    bienvenida = f"¡Hola de nuevo, {cliente['nombre']}! Nivel {cliente['nivel']} · {cliente['puntos']} puntos."
            except tienda.ErrorTienda as error:
                messagebox.showwarning("Mi cuenta", str(error), parent=modal)
                return
            except Exception as error:
                messagebox.showerror("Mi cuenta", f"No se pudo conectar con la base de datos:\n{error}", parent=modal)
                return
            self.cliente = cliente
            modal.destroy()
            messagebox.showinfo("Club Vestidor Virtual", bienvenida)
            if al_terminar:
                al_terminar()
            else:
                self.mostrar_galeria()

        self.boton(f, "INGRESAR / CREAR MI CUENTA", ingresar, tam=11, padx=24, pady=8).pack(pady=(4, 0))

    # ---------------------------------------------------------------------
    # COMPRA
    # ---------------------------------------------------------------------
    def mostrar_compra(self, prenda):
        import tienda
        color, talle = self.color_seleccionado.get(), self.talle_seleccionado.get()
        disponibles = stock_de(prenda, color, talle) or 0
        if disponibles == 0:
            messagebox.showwarning("Compra", "No hay stock de esa combinación.")
            return
        modal = tk.Toplevel(self.root)
        modal.title("Finalizar compra")
        modal.configure(bg=COLOR_BG_APP)
        modal.transient(self.root)
        modal.grab_set()
        f = tk.Frame(modal, bg=COLOR_CARD_BG, padx=28, pady=20)
        f.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        tk.Label(f, text="🛍 Tu compra", font=("Georgia", 17, "bold"), fg=COLOR_TEXT_MAIN, bg=COLOR_CARD_BG).pack(anchor="w")
        sku = (prenda.get("skus") or {}).get((color, talle), prenda.get("sku", ""))
        tk.Label(f, text=f"{prenda['nombre']}\n{color} · talle {talle} · SKU {sku}", font=("Segoe UI", 10),
                 fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG, justify="left").pack(anchor="w", pady=(2, 8))
        fila = tk.Frame(f, bg=COLOR_CARD_BG)
        fila.pack(anchor="w")
        tk.Label(fila, text="Cantidad:", font=("Segoe UI", 10, "bold"), bg=COLOR_CARD_BG).pack(side=tk.LEFT)
        cantidad = tk.IntVar(value=1)
        tk.Spinbox(fila, from_=1, to=disponibles, textvariable=cantidad, width=4, font=("Segoe UI", 10),
                   command=lambda: actualizar()).pack(side=tk.LEFT, padx=6)
        tk.Label(fila, text=f"(hay {disponibles})", font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED,
                 bg=COLOR_CARD_BG).pack(side=tk.LEFT)

        cupon_var, usar_puntos = tk.StringVar(value="Sin cupón"), tk.BooleanVar(value=False)
        cupones = {}
        if self.cliente:
            for cup in self.cliente["cupones"]:
                cupones[f"{cup['codigo']} — {cup['descripcion']}"] = cup
            if cupones:
                cupon_var.set(next(iter(cupones)))
                tk.Label(f, text="Cupón:", font=("Segoe UI", 10, "bold"), bg=COLOR_CARD_BG).pack(anchor="w", pady=(8, 0))
                ttk.Combobox(f, textvariable=cupon_var, values=["Sin cupón"] + list(cupones), state="readonly",
                             width=52).pack(anchor="w")
            if self.cliente["puntos"] > 0:
                tk.Checkbutton(f, text=f"Usar mis {self.cliente['puntos']} puntos (hasta 30% del pedido)",
                               variable=usar_puntos, bg=COLOR_CARD_BG, activebackground=COLOR_CARD_BG,
                               command=lambda: actualizar()).pack(anchor="w", pady=(6, 0))
        else:
            aviso = tk.Frame(f, bg=COLOR_TAG_BG, padx=10, pady=6)
            aviso.pack(fill=tk.X, pady=8)
            tk.Label(aviso, text="Ingresá a tu cuenta y ahorrá 15% con tu cupón de bienvenida.",
                     font=("Segoe UI", 9, "bold"), fg=COLOR_ROSE, bg=COLOR_TAG_BG).pack(side=tk.LEFT)
            self.boton(aviso, "INGRESAR", lambda: (modal.destroy(), self.mostrar_cuenta(
                al_terminar=lambda: (self.mostrar_confirmacion(prenda), self.mostrar_compra(prenda)))),
                tam=8, padx=10, pady=3).pack(side=tk.RIGHT)

        resumen = tk.Label(f, text="", font=("Consolas", 10), fg=COLOR_TEXT_MAIN, bg="#FAF6F0", justify="left",
                           padx=12, pady=10)
        resumen.pack(fill=tk.X, pady=10)

        def actualizar(*_):
            try:
                cant = max(1, min(disponibles, int(cantidad.get())))
            except (tk.TclError, ValueError):
                cant = 1
            try:
                d = tienda.calcular_total(prenda["precio"] * cant, self.cliente, cupones.get(cupon_var.get()),
                                          usar_puntos.get())
            except tienda.ErrorTienda as error:
                resumen.config(text=str(error))
                return None
            lineas = [f"Subtotal            {precio_str(d['subtotal']):>12}"]
            if d["descuento_nivel"]:
                lineas.append(f"Nivel {self.cliente['nivel']:<13} -{precio_str(d['descuento_nivel']):>11}")
            if d["descuento_cupon"]:
                lineas.append(f"Cupón               -{precio_str(d['descuento_cupon']):>11}")
            if d["descuento_puntos"]:
                lineas.append(f"Puntos ({d['puntos_usados']})        -{precio_str(d['descuento_puntos']):>11}")
            lineas.append(f"TOTAL               {precio_str(d['total']):>12}")
            if self.cliente:
                lineas.append(f"Sumás {d['puntos_ganados']} puntos ⭐")
            resumen.config(text="\n".join(lineas))
            return cant

        cupon_var.trace_add("write", actualizar)
        cantidad.trace_add("write", actualizar)
        actualizar()

        def confirmar():
            cant = actualizar()
            if cant is None:
                return
            cupon = cupones.get(cupon_var.get())
            try:
                r = tienda.comprar([{"id_prenda": prenda["id_prenda"], "color": color, "talle": talle,
                                     "cantidad": cant}],
                                   self.cliente["id_cliente"] if self.cliente else None,
                                   cupon["id_cupon"] if cupon else None, usar_puntos.get())
            except tienda.ErrorTienda as error:
                messagebox.showwarning("Compra", str(error), parent=modal)
                return
            except Exception as error:
                messagebox.showerror("Compra", f"No se pudo registrar la compra:\n{error}", parent=modal)
                return
            try:
                from conexion_mysql import leer_stock
                prenda["stock"] = leer_stock(prenda["id_prenda"])
            except Exception:
                pass
            if r["cliente"]:
                self.cliente = r["cliente"]
            mensaje = f"¡Gracias por tu compra! Pedido #{r['id_pedido']} por {precio_str(r['detalle']['total'])}."
            if r["detalle"]["puntos_ganados"]:
                mensaje += f"\nSumaste {r['detalle']['puntos_ganados']} puntos."
            if r["nivel_nuevo"]:
                mensaje += f"\n🎉 ¡Subiste a nivel {r['nivel_nuevo']}!"
            modal.destroy()
            messagebox.showinfo("Compra confirmada", mensaje)
            self.mostrar_confirmacion(prenda)

        self.boton(f, "CONFIRMAR COMPRA", confirmar, color=COLOR_GOLD, hover="#A8853F", tam=11, padx=24,
                   pady=8).pack()

    # ---------------------------------------------------------------------
    # VISTA 3: CÁMARA
    # ---------------------------------------------------------------------
    def lanzar_camara(self):
        """Oculta la galería, abre la cámara y al cerrarla vuelve al detalle de la prenda probada."""
        if not self.prenda_seleccionada:
            return
        self.limpiar_contenedor()
        self.root.withdraw()
        # Los objetos de la galería que quedaron sin uso se borran AHORA, desde la ventana
        # principal. Si Python los borrara más tarde en el hilo de MediaPipe, ese hilo se
        # quedaría esperando a la ventana (ocupada con la cámara): la prenda se congelaba
        # y el programa no se podía cerrar. Durante la cámara, el borrado automático queda
        # en pausa (lo común se libera igual al dejar de usarse).
        gc.collect()
        gc.disable()
        try:
            prenda_final, color_final = ejecutar_probador_camara(
                self.prenda_seleccionada, self.catalogo, talle_elegido=self.talle_seleccionado.get(),
                color_elegido=self.color_seleccionado.get())
        finally:
            gc.enable()
            gc.collect()
        self.color_seleccionado.set(color_final or "")
        self.root.deiconify()
        self.mostrar_confirmacion(prenda_final or self.prenda_seleccionada)
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
