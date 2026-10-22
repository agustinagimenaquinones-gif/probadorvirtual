# ==========================================================
# PROYECTO: PROBADOR VIRTUAL INTELIGENTE - BOUTIQUE FEMENINA
# MÓDULO: GALERÍA (interfaz Tkinter: galería, confirmación y tabla de medidas)
# ==========================================================

from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk

from catalogo import (
    cargar_catalogo_completo,
    holgura_de_talle,
    talle_inicial,
    obtener_medidas_talle,
    obtener_guia_medidas_completa
)
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


# =========================================================================
# INTERFAZ GRÁFICA TKINTER: BOUTIQUE FEMENINA & GALERÍA DE PRENDAS
# =========================================================================
class BoutiqueVirtualApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Probador Virtual Inteligente - Boutique Atelier")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        self.root.configure(bg=COLOR_BG_APP)

        # Centrar ventana en pantalla
        self.centrar_ventana(1200, 800)

        # Asegurar recursos y cargar prendas
        asegurar_recursos()
        self.catalogo = cargar_catalogo_completo()
        self.fotos_tk_cache = {}  # Cache para evitar recolección de basura de PhotoImage
        self.prenda_seleccionada = None
        self.talle_seleccionado = tk.StringVar(value="M")

        # Contenedor principal que alternará entre Galería y Confirmación
        self.contenedor_principal = tk.Frame(self.root, bg=COLOR_BG_APP)
        self.contenedor_principal.pack(fill=tk.BOTH, expand=True)

        # Iniciar mostrando la Galería
        self.mostrar_galeria()

    def centrar_ventana(self, ancho, alto):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = max(0, (sw - ancho) // 2)
        y = max(0, (sh - alto) // 2)
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

    def limpiar_contenedor(self):
        for widget in self.contenedor_principal.winfo_children():
            widget.destroy()

    def obtener_imagen_tk(self, ruta_archivo, tamano=(190, 190)):
        """Carga y reescala con alta calidad una imagen para mostrarla en Tkinter."""
        clave = f"{ruta_archivo}_{tamano[0]}x{tamano[1]}"
        if clave in self.fotos_tk_cache:
            return self.fotos_tk_cache[clave]

        try:
            img = Image.open(ruta_archivo)
            img.thumbnail(tamano, Image.Resampling.LANCZOS)

            # Fondo blanco para la tarjeta
            canvas_img = Image.new("RGBA", tamano, (255, 255, 255, 0))
            offset_x = (tamano[0] - img.width) // 2
            offset_y = (tamano[1] - img.height) // 2
            canvas_img.paste(img, (offset_x, offset_y), img if img.mode == 'RGBA' else None)

            foto_tk = ImageTk.PhotoImage(canvas_img)
            self.fotos_tk_cache[clave] = foto_tk
            return foto_tk
        except Exception as e:
            print(f"[AVISO] Error cargando imagen para Tkinter: {e}")
            return None

    # ---------------------------------------------------------------------
    # VISTA 1: GALERÍA DE PRENDAS (TIENDA ONLINE FEMENINA)
    # ---------------------------------------------------------------------
    def mostrar_galeria(self):
        self.limpiar_contenedor()

        # 1. Cabecera estilo Atelier de Moda Femenina
        header_frame = tk.Frame(self.contenedor_principal, bg=COLOR_HEADER_BG, pady=18)
        header_frame.pack(fill=tk.X, side=tk.TOP)

        lbl_marca = tk.Label(
            header_frame,
            text="✨   B O U T I Q U E   A T E L I E R   ✨",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_HEADER_BG
        )
        lbl_marca.pack()

        lbl_titulo = tk.Label(
            header_frame,
            text="Vestidor Virtual de Moda Femenina",
            font=("Georgia", 22, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_HEADER_BG,
            pady=4
        )
        lbl_titulo.pack()

        lbl_sub = tk.Label(
            header_frame,
            text="Explora la colección exclusiva y prueba cada prenda en vivo adaptada a tu cuerpo",
            font=("Segoe UI", 11),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_HEADER_BG
        )
        lbl_sub.pack()

        # Línea divisoria suave
        div = tk.Frame(header_frame, height=1, bg=COLOR_CARD_BORDER)
        div.pack(fill=tk.X, pady=(12, 0))

        # 2. Área desplazable (Canvas + Scrollbar) para las tarjetas de prendas
        canvas_contenedor = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        canvas_contenedor.pack(fill=tk.BOTH, expand=True, padx=25, pady=15)

        canvas = tk.Canvas(canvas_contenedor, bg=COLOR_BG_APP, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_contenedor, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=COLOR_BG_APP)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def al_redimensionar(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", al_redimensionar)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Soporte para rueda del ratón
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # 3. Cuadrícula de Tarjetas de Prendas
        columnas = 3
        pad_x, pad_y = 12, 14

        grid_frame = tk.Frame(scrollable_frame, bg=COLOR_BG_APP)
        grid_frame.pack(anchor="center", pady=10)

        for idx, prenda in enumerate(self.catalogo):
            fila = idx // columnas
            col = idx % columnas
            self.crear_tarjeta_prenda(grid_frame, prenda, fila, col, pad_x, pad_y)

    def crear_tarjeta_prenda(self, parent, prenda, fila, col, pad_x, pad_y):
        """Crea una tarjeta individual moderna, limpia y femenina con botón PROBAR."""
        card = tk.Frame(
            parent,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
            width=290
        )
        card.grid(row=fila, column=col, padx=pad_x, pady=pad_y, sticky="nsew")

        # Efecto hover sobre la tarjeta
        def on_enter(e):
            card.config(highlightbackground=COLOR_CARD_HOVER, highlightthickness=2)
        def on_leave(e):
            card.config(highlightbackground=COLOR_CARD_BORDER, highlightthickness=1)
        card.bind("<Enter>", on_enter)
        card.bind("<Leave>", on_leave)

        # Imagen real de la prenda
        foto_tk = self.obtener_imagen_tk(prenda["archivo"], tamano=(180, 180))
        if foto_tk:
            lbl_img = tk.Label(card, image=foto_tk, bg=COLOR_CARD_BG)
            lbl_img.image = foto_tk
            lbl_img.pack(pady=(4, 10))

        # Nombre de la prenda
        lbl_nombre = tk.Label(
            card,
            text=prenda["nombre"],
            font=("Segoe UI", 12, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG,
            wraplength=250
        )
        lbl_nombre.pack(anchor="center", pady=(0, 2))

        # Precio con formato elegante
        precio_str = f"${prenda['precio']:,}".replace(',', '.')
        lbl_precio = tk.Label(
            card,
            text=precio_str,
            font=("Segoe UI", 14, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_CARD_BG
        )
        lbl_precio.pack(anchor="center", pady=(0, 4))

        # Color
        lbl_color = tk.Label(
            card,
            text=f"Color: {prenda['color']}",
            font=("Segoe UI", 10),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG
        )
        lbl_color.pack(anchor="center", pady=(0, 2))

        # Talles disponibles y calce
        talles_str = " · ".join(prenda["talles"])
        calce_str = prenda.get("calce", "regular").capitalize()
        lbl_talles = tk.Label(
            card,
            text=f"Talles: {talles_str}  ·  Calce {calce_str}",
            font=("Segoe UI", 9, "bold"),
            fg="#9E786B",
            bg=COLOR_TAG_BG,
            padx=8,
            pady=2
        )
        lbl_talles.pack(anchor="center", pady=(2, 12))

        # Botón PROBAR
        btn_probar = tk.Button(
            card,
            text="PROBAR",
            font=("Segoe UI", 10, "bold"),
            fg="#FFFFFF",
            bg=COLOR_ROSE,
            activeforeground="#FFFFFF",
            activebackground=COLOR_ROSE_HOVER,
            relief=tk.FLAT,
            bd=0,
            padx=25,
            pady=7,
            cursor="hand2",
            command=lambda p=prenda: self.mostrar_confirmacion(p)
        )
        btn_probar.pack(anchor="center", fill=tk.X, pady=(4, 2))

        # Efecto hover del botón
        btn_probar.bind("<Enter>", lambda e, b=btn_probar: b.config(bg=COLOR_ROSE_HOVER))
        btn_probar.bind("<Leave>", lambda e, b=btn_probar: b.config(bg=COLOR_ROSE))

    # ---------------------------------------------------------------------
    # VISTA 2: PANTALLA DE DETALLE Y CONFIRMACIÓN ("Elegiste: ...")
    # ---------------------------------------------------------------------
    def mostrar_confirmacion(self, prenda):
        """Muestra la pantalla de confirmación y selección de talle con sus medidas reales."""
        self.prenda_seleccionada = prenda
        self.limpiar_contenedor()

        contenedor_detalle = tk.Frame(self.contenedor_principal, bg=COLOR_BG_APP)
        contenedor_detalle.pack(expand=True, fill=tk.BOTH, padx=25, pady=20)

        # Tarjeta central flotante de confirmación (dos columnas: foto y medidas)
        tarjeta_detalle = tk.Frame(
            contenedor_detalle,
            bg=COLOR_CARD_BG,
            highlightbackground=COLOR_CARD_BORDER,
            highlightthickness=1,
            padx=35,
            pady=22
        )
        tarjeta_detalle.pack(anchor="center", expand=True)

        lbl_sub = tk.Label(
            tarjeta_detalle,
            text="✨ VESTIDOR VIRTUAL · ELECCIÓN Y MEDIDAS ✨",
            font=("Segoe UI", 10, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_CARD_BG
        )
        lbl_sub.pack(pady=(0, 2))

        lbl_elegiste = tk.Label(
            tarjeta_detalle,
            text=f"Elegiste: {prenda['nombre']}",
            font=("Georgia", 19, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG
        )
        lbl_elegiste.pack(pady=(0, 10))

        # Panel de dos columnas
        panel_columnas = tk.Frame(tarjeta_detalle, bg=COLOR_CARD_BG)
        panel_columnas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # --- COLUMNA IZQUIERDA: Imagen y Ficha Rápida ---
        col_izq = tk.Frame(panel_columnas, bg=COLOR_CARD_BG)
        col_izq.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 25))

        foto_grande = self.obtener_imagen_tk(prenda["archivo"], tamano=(230, 230))
        if foto_grande:
            marco_foto = tk.Frame(col_izq, bg="#F9F6F3", highlightbackground=COLOR_CARD_BORDER, highlightthickness=1, padx=6, pady=6)
            marco_foto.pack(pady=(0, 8))
            lbl_foto = tk.Label(marco_foto, image=foto_grande, bg="#F9F6F3")
            lbl_foto.image = foto_grande
            lbl_foto.pack()

        precio_str = f"${prenda['precio']:,}".replace(',', '.')
        lbl_precio = tk.Label(
            col_izq,
            text=precio_str,
            font=("Segoe UI", 17, "bold"),
            fg=COLOR_GOLD,
            bg=COLOR_CARD_BG
        )
        lbl_precio.pack(pady=(0, 2))

        lbl_color = tk.Label(
            col_izq,
            text=f"Color: {prenda['color']}",
            font=("Segoe UI", 10),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG
        )
        lbl_color.pack(pady=(0, 2))

        calce_str = prenda.get("calce", "regular").capitalize()
        lbl_calce_tag = tk.Label(
            col_izq,
            text=f"Calce: {calce_str}",
            font=("Segoe UI", 9, "bold"),
            fg="#8B5E3C",
            bg=COLOR_TAG_BG,
            padx=10,
            pady=3
        )
        lbl_calce_tag.pack(pady=(4, 0))

        # --- COLUMNA DERECHA: Descripción, Selección de Talle y Medidas Reales ---
        col_der = tk.Frame(panel_columnas, bg=COLOR_CARD_BG)
        col_der.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        lbl_desc = tk.Label(
            col_der,
            text=prenda.get("descripcion", ""),
            font=("Segoe UI", 10, "italic"),
            fg=COLOR_TEXT_MUTED,
            bg=COLOR_CARD_BG,
            wraplength=480,
            justify="left"
        )
        lbl_desc.pack(anchor="w", pady=(0, 10))

        # 1. Selector de Talle
        self.talle_seleccionado.set(talle_inicial(prenda, self.talle_seleccionado.get()))

        lbl_sel_tit = tk.Label(
            col_der,
            text="1. Elegí tu Talle con sus Medidas:",
            font=("Segoe UI", 11, "bold"),
            fg=COLOR_TEXT_MAIN,
            bg=COLOR_CARD_BG
        )
        lbl_sel_tit.pack(anchor="w", pady=(0, 6))

        talles_bar = tk.Frame(col_der, bg=COLOR_CARD_BG)
        talles_bar.pack(anchor="w", pady=(0, 10))

        # 2. Caja de Medidas Reales Dinámicas
        medidas_box = tk.Frame(
            col_der,
            bg="#FAF6F0",
            highlightbackground="#E2D5C8",
            highlightthickness=1,
            padx=14,
            pady=10
        )
        medidas_box.pack(fill=tk.X, pady=(0, 10))

        lbl_medidas_tit = tk.Label(
            medidas_box,
            text="📐 Medidas de la Prenda para el Talle Elegido (en cm):",
            font=("Segoe UI", 10, "bold"),
            fg="#7E5835",
            bg="#FAF6F0"
        )
        lbl_medidas_tit.pack(anchor="w", pady=(0, 6))

        grid_medidas = tk.Frame(medidas_box, bg="#FAF6F0")
        grid_medidas.pack(fill=tk.X)

        val_pecho = tk.StringVar()
        val_cintura = tk.StringVar()
        val_cadera = tk.StringVar()
        val_hombros = tk.StringVar()
        val_largo = tk.StringVar()
        val_holgura = tk.StringVar()

        def crear_item_medida(parent, r, c, icono, etiqueta, var):
            f_item = tk.Frame(parent, bg="#FAF6F0")
            f_item.grid(row=r, column=c, sticky="w", padx=10, pady=3)
            tk.Label(f_item, text=f"{icono} {etiqueta}:", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT_MAIN, bg="#FAF6F0").pack(side=tk.LEFT)
            tk.Label(f_item, textvariable=var, font=("Segoe UI", 9, "bold"), fg="#A35848", bg="#FAF6F0").pack(side=tk.LEFT, padx=(4, 0))

        crear_item_medida(grid_medidas, 0, 0, "📏", "Pecho/Busto", val_pecho)
        crear_item_medida(grid_medidas, 0, 1, "📐", "Cintura", val_cintura)
        crear_item_medida(grid_medidas, 0, 2, "👗", "Cadera", val_cadera)
        crear_item_medida(grid_medidas, 1, 0, "👔", "Hombros", val_hombros)
        crear_item_medida(grid_medidas, 1, 1, "↕️", "Largo Total", val_largo)
        crear_item_medida(grid_medidas, 1, 2, "🏷️", "Holgura", val_holgura)

        def actualizar_ficha_medidas():
            t_sel = self.talle_seleccionado.get()
            m = obtener_medidas_talle(prenda, t_sel)
            lbl_medidas_tit.config(text=f"📐 Medidas de la Prenda para el Talle Elegido (TALLE {t_sel}):")
            val_pecho.set(f"{m['pecho']} cm")
            val_cintura.set(f"{m['cintura']} cm")
            val_cadera.set(f"{m['cadera']} cm")
            val_hombros.set(f"{m['hombros']} cm")
            val_largo.set(f"{m['largo']} cm")
            h_pct = int(round((holgura_de_talle(t_sel) - 1.0) * 100))
            h_signo = f"+{h_pct}%" if h_pct >= 0 else f"{h_pct}%"
            val_holgura.set(f"{h_signo} ({calce_str})")

        for t in prenda["talles"]:
            rb = tk.Radiobutton(
                talles_bar, text=t, value=t, variable=self.talle_seleccionado,
                indicatoron=False, width=5, font=("Segoe UI", 11, "bold"),
                fg=COLOR_TEXT_MAIN, bg=COLOR_TAG_BG, selectcolor=COLOR_ROSE,
                activebackground=COLOR_CARD_HOVER, relief=tk.FLAT, bd=0, pady=5, cursor="hand2",
                command=actualizar_ficha_medidas
            )
            rb.pack(side=tk.LEFT, padx=3)

        btn_tabla_modal = tk.Button(
            talles_bar,
            text="📏 Ver Guía Completa de Medidas",
            font=("Segoe UI", 9, "bold"),
            fg="#7E5835",
            bg="#F0E5D8",
            activebackground="#E5D6C5",
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            command=lambda p=prenda: self.mostrar_tabla_medidas_modal(p)
        )
        btn_tabla_modal.pack(side=tk.LEFT, padx=(12, 0))

        actualizar_ficha_medidas()

        lbl_tip = tk.Label(
            col_der,
            text="💡 Al abrir la cámara, el sistema medirá tu silueta real (pecho, cintura y cadera) y adaptará la prenda a tu figura y al talle seleccionado.",
            font=("Segoe UI", 9),
            fg="#8C7F79",
            bg=COLOR_TAG_BG,
            padx=12,
            pady=7,
            wraplength=480,
            justify="left"
        )
        lbl_tip.pack(anchor="w", pady=(0, 14))

        # Botones de Acción
        botones_frame = tk.Frame(col_der, bg=COLOR_CARD_BG)
        botones_frame.pack(anchor="w")

        btn_abrir_cam = tk.Button(
            botones_frame,
            text="⭐ PROBAR PRENDA EN CÁMARA",
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF",
            bg=COLOR_GOLD,
            activeforeground="#FFFFFF",
            activebackground="#A8853F",
            relief=tk.FLAT,
            bd=0,
            padx=28,
            pady=9,
            cursor="hand2",
            command=self.lanzar_camara
        )
        btn_abrir_cam.grid(row=0, column=0, padx=(0, 12))

        btn_abrir_cam.bind("<Enter>", lambda e, b=btn_abrir_cam: b.config(bg="#B59048"))
        btn_abrir_cam.bind("<Leave>", lambda e, b=btn_abrir_cam: b.config(bg=COLOR_GOLD))

        btn_volver = tk.Button(
            botones_frame,
            text="← VOLVER A LA GALERÍA",
            font=("Segoe UI", 11),
            fg=COLOR_TEXT_MAIN,
            bg="#F2EBE5",
            activebackground="#E5DCD4",
            relief=tk.FLAT,
            bd=0,
            padx=18,
            pady=9,
            cursor="hand2",
            command=self.mostrar_galeria
        )
        btn_volver.grid(row=0, column=1)

        btn_volver.bind("<Enter>", lambda e, b=btn_volver: b.config(bg="#E5DCD4"))
        btn_volver.bind("<Leave>", lambda e, b=btn_volver: b.config(bg="#F2EBE5"))

    def mostrar_tabla_medidas_modal(self, prenda):
        """Abre un modal elegante con la tabla comparativa de medidas de todos los talles de la prenda."""
        modal = tk.Toplevel(self.root)
        modal.title(f"Guía y Tabla de Medidas - {prenda['nombre']}")
        modal.geometry("680x500")
        modal.minsize(600, 440)
        modal.configure(bg=COLOR_BG_APP)
        modal.transient(self.root)
        modal.grab_set()

        mw, mh = 680, 500
        rx = self.root.winfo_x() + (self.root.winfo_width() - mw) // 2
        ry = self.root.winfo_y() + (self.root.winfo_height() - mh) // 2
        modal.geometry(f"{mw}x{mh}+{max(0, rx)}+{max(0, ry)}")

        f = tk.Frame(modal, bg=COLOR_CARD_BG, padx=25, pady=18)
        f.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        tk.Label(f, text="📏 TABLA DE MEDIDAS Y GUÍA DE CALCE", font=("Segoe UI", 11, "bold"),
                 fg=COLOR_GOLD, bg=COLOR_CARD_BG).pack()
        tk.Label(f, text=prenda["nombre"], font=("Georgia", 16, "bold"),
                 fg=COLOR_TEXT_MAIN, bg=COLOR_CARD_BG, pady=3).pack()
        tk.Label(f, text=f"Calce: {prenda.get('calce', 'regular').capitalize()}  ·  Color: {prenda.get('color')}",
                 font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD_BG).pack(pady=(0, 14))

        tabla_frame = tk.Frame(f, bg=COLOR_CARD_BORDER, padx=1, pady=1)
        tabla_frame.pack(fill=tk.X, pady=(0, 14))

        cabeceras = ["Talle", "Pecho / Busto", "Cintura", "Cadera", "Hombros", "Largo Total", "Calce"]
        filas = obtener_guia_medidas_completa(prenda)

        for col_idx, h in enumerate(cabeceras):
            tk.Label(tabla_frame, text=h, font=("Segoe UI", 10, "bold"),
                     bg="#EAE0D6", fg=COLOR_TEXT_MAIN, padx=8, pady=7).grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)

        talle_actual = self.talle_seleccionado.get()
        for row_idx, fila in enumerate(filas, start=1):
            es_sel = (fila["talle"] == talle_actual)
            bg_fila = "#F5E6E0" if es_sel else ("#FFFFFF" if row_idx % 2 == 1 else "#FAF7F5")
            fg_fila = COLOR_TEXT_MAIN

            vals = [fila["talle"] + (" ★" if es_sel else ""), fila["pecho"], fila["cintura"], fila["cadera"],
                    fila["hombros"], fila["largo"], fila["calce"]]
            for col_idx, val in enumerate(vals):
                font_weight = "bold" if es_sel or col_idx == 0 else "normal"
                lbl = tk.Label(tabla_frame, text=val, font=("Segoe UI", 9, font_weight),
                               bg=bg_fila, fg=fg_fila, padx=8, pady=6)
                lbl.grid(row=row_idx, column=col_idx, sticky="nsew", padx=1, pady=1)

        for i in range(len(cabeceras)):
            tabla_frame.columnconfigure(i, weight=1)

        tips_frame = tk.Frame(f, bg=COLOR_TAG_BG, padx=14, pady=9)
        tips_frame.pack(fill=tk.X, pady=(0, 14))
        tk.Label(tips_frame, text="💡 ¿Cómo tomar tus medidas con cinta métrica?",
                 font=("Segoe UI", 9, "bold"), fg="#7A5230", bg=COLOR_TAG_BG).pack(anchor="w")
        tk.Label(tips_frame, text="• Pecho/Busto: medir horizontalmente rodeando el contorno más ancho del torso.\n• Cintura: medir en el punto más estrecho del torso natural (a la altura del ombligo).\n• Cadera: medir de pie con los talones juntos en la parte más amplia.",
                 font=("Segoe UI", 9), fg=COLOR_TEXT_MUTED, bg=COLOR_TAG_BG, justify="left").pack(anchor="w", pady=(2, 0))

        btn_cerrar = tk.Button(f, text="ENTENDIDO / CERRAR", font=("Segoe UI", 10, "bold"),
                               bg=COLOR_ROSE, fg="#FFFFFF", relief=tk.FLAT, bd=0, padx=22, pady=7,
                               cursor="hand2", command=modal.destroy)
        btn_cerrar.pack()

    # ---------------------------------------------------------------------
    # VISTA 3: APERTURA Y CONTROL DE LA CÁMARA
    # ---------------------------------------------------------------------
    def lanzar_camara(self):
        """Oculta la ventana de la galería e inicia la cámara en vivo."""
        if not self.prenda_seleccionada:
            return

        # 1. Ocultar ventana de la galería
        self.root.withdraw()

        # 2. Ejecutar probador en vivo con OpenCV y MediaPipe
        resultado = ejecutar_probador_camara(self.prenda_seleccionada, self.catalogo,
                                             talle_elegido=self.talle_seleccionado.get())

        # 3. Retorno del probador:
        # Si presionó 'G' vuelve a la galería, si presionó 'Q' cierra la app.
        if resultado == "galeria":
            self.root.deiconify()
            self.mostrar_galeria()
        else:
            self.root.destroy()
