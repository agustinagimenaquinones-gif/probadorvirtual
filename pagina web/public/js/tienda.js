// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Tienda: catálogo con filtros, detalle de la prenda, cuenta del cliente y compra.
// ==========================================================

(() => {
  const { api, precio, stockDe, stockTotal, cliente, guardarCliente, aviso, escapar } = Comun;
  const estado = { prendas: [], ventas: false, categoria: "Todas", favoritos: false };

  const $ = (sel) => document.querySelector(sel);
  const dialogoPrenda = $("#dialogo-prenda");
  const dialogoCuenta = $("#dialogo-cuenta");
  const dialogoCompra = $("#dialogo-compra");

  // ---------------------------------------------------------------- catálogo
  function categorias() {
    const lista = ["Todas", ...new Set(estado.prendas.map(p => p.categoria))];
    if (cliente()) lista.push("♥ Favoritos");
    return lista;
  }

  function dibujarFiltros() {
    $("#filtros").innerHTML = categorias().map(c => {
      const activa = c === "♥ Favoritos" ? estado.favoritos : (!estado.favoritos && c === estado.categoria);
      return `<button class="chip" type="button" data-categoria="${escapar(c)}" aria-pressed="${activa}">${escapar(c)}</button>`;
    }).join("");
  }

  function dibujarGrilla() {
    const c = cliente();
    const favoritos = new Set(c ? c.favoritos || [] : []);
    const lista = estado.prendas.filter(p => estado.favoritos
      ? favoritos.has(p.codigo) : (estado.categoria === "Todas" || p.categoria === estado.categoria));
    if (!lista.length) {
      $("#grilla").innerHTML = `<p class="estado-tienda">${estado.favoritos
        ? "Todavía no guardaste favoritos. Tocá ♡ en una prenda para guardarla." : "No hay prendas en esta categoría."}</p>`;
      return;
    }
    $("#grilla").innerHTML = lista.map(p => {
      const color = p.colores[0];
      const sinStock = estado.ventas && stockTotal(p) === 0;
      return `
        <button class="tarjeta" type="button" data-codigo="${escapar(p.codigo)}">
          <div class="tarjeta-foto"><img src="${escapar(p.imagenes[color.nombre])}" alt="${escapar(p.nombre)}" loading="lazy"></div>
          <div class="tarjeta-info">
            <span class="tarjeta-meta">${escapar(p.categoria)}${favoritos.has(p.codigo) ? " · ♥" : ""}</span>
            <h3>${escapar(p.nombre)}</h3>
            <span class="tarjeta-precio">${precio(p.precio)}</span>
            <span class="puntos-color">${p.colores.map(col =>
              `<span class="punto-color" title="${escapar(col.nombre)}" style="background:${escapar(col.hex || "#ccc")}"></span>`).join("")}</span>
            ${sinStock ? `<span class="stock no-hay">Sin stock</span>` : ""}
          </div>
        </button>`;
    }).join("");
  }

  // ---------------------------------------------------------------- detalle
  function abrirPrenda(codigo, colorInicial, talleInicial) {
    const p = estado.prendas.find(x => x.codigo === codigo);
    if (!p) return;
    const c = cliente();
    const sel = {
      color: p.colores.some(x => x.nombre === colorInicial) ? colorInicial : p.colores[0].nombre,
      talle: p.talles.includes(talleInicial) ? talleInicial
        : (c && p.talles.includes(c.talle_preferido) ? c.talle_preferido : (p.talles.includes("M") ? "M" : p.talles[0])),
    };

    function dibujar() {
      const hay = stockDe(p, sel.color, sel.talle);
      const esFavorito = c && (c.favoritos || []).includes(p.codigo);
      const medidas = p.medidas_talles || {};
      const filasMedidas = Object.keys(medidas).length ? `
        <details class="grupo"><summary>Guía de talles (cm)</summary>
          <table class="tabla-medidas"><thead><tr><th>Talle</th><th>Pecho</th><th>Cintura</th><th>Cadera</th><th>Largo</th></tr></thead>
          <tbody>${p.talles.filter(t => medidas[t]).map(t =>
            `<tr><td>${escapar(t)}</td><td>${medidas[t].pecho}</td><td>${medidas[t].cintura}</td><td>${medidas[t].cadera}</td><td>${medidas[t].largo}</td></tr>`).join("")}
          </tbody></table></details>` : "";
      $("#detalle-prenda").innerHTML = `
        <button class="dialogo-cerrar" type="button" data-cerrar aria-label="Cerrar">×</button>
        <div class="detalle">
          <div class="detalle-foto"><img src="${escapar(p.imagenes[sel.color])}" alt="${escapar(p.nombre)} en ${escapar(sel.color)}"></div>
          <div>
            <span class="tarjeta-meta">${escapar(p.categoria)} · Calce ${escapar(p.calce)} · ${escapar(p.sku || "")}</span>
            <h2 id="titulo-prenda">${escapar(p.nombre)}</h2>
            <div class="precio-grande">${precio(p.precio)}</div>
            <p>${escapar(p.descripcion)}</p>
            <div class="grupo"><div class="grupo-titulo">Color: ${escapar(sel.color)}</div>
              <div class="opciones">${p.colores.map(col => `
                <button class="opcion" type="button" data-color="${escapar(col.nombre)}" aria-pressed="${col.nombre === sel.color}">
                  <span class="punto-color" style="display:inline-block;vertical-align:middle;background:${escapar(col.hex || "#ccc")}"></span> ${escapar(col.nombre)}
                </button>`).join("")}</div></div>
            <div class="grupo"><div class="grupo-titulo">Talle</div>
              <div class="opciones">${p.talles.map(t => `
                <button class="opcion" type="button" data-talle="${escapar(t)}" aria-pressed="${t === sel.talle}"
                  ${estado.ventas && stockDe(p, sel.color, t) === 0 ? "disabled" : ""}>${escapar(t)}</button>`).join("")}</div></div>
            <div class="stock ${hay ? "hay" : "no-hay"}">${hay ? `${hay} disponible${hay > 1 ? "s" : ""} en ${escapar(sel.color)}, talle ${escapar(sel.talle)}`
              : `Sin stock en ${escapar(sel.color)}, talle ${escapar(sel.talle)}`}</div>
            ${filasMedidas}
            <div class="fila-botones">
              <a class="boton" href="probador.html?prenda=${encodeURIComponent(p.codigo)}&color=${encodeURIComponent(sel.color)}&talle=${encodeURIComponent(sel.talle)}">Probármela con la cámara</a>
              <button class="boton boton-dorado" type="button" data-comprar ${!estado.ventas || !hay ? "disabled" : ""}>Comprar</button>
              ${c ? `<button class="boton boton-claro" type="button" data-favorito aria-pressed="${Boolean(esFavorito)}">${esFavorito ? "♥ Favorita" : "♡ Favorito"}</button>` : ""}
            </div>
            ${estado.ventas ? "" : `<p class="tarjeta-meta">La tienda está en modo vidriera: las compras se habilitan cuando la página tiene base de datos.</p>`}
          </div>
        </div>`;
    }

    $("#detalle-prenda").onclick = async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.cerrar !== undefined) dialogoPrenda.close();
      else if (b.dataset.color) { sel.color = b.dataset.color; if (!stockDe(p, sel.color, sel.talle) && estado.ventas) sel.talle = p.talles.find(t => stockDe(p, sel.color, t)) || sel.talle; dibujar(); }
      else if (b.dataset.talle) { sel.talle = b.dataset.talle; dibujar(); }
      else if (b.dataset.comprar !== undefined) abrirCompra(p, sel.color, sel.talle);
      else if (b.dataset.favorito !== undefined) {
        try {
          const r = await api("favoritos", { id_cliente: c.id_cliente, id_prenda: p.id_prenda });
          const lista = new Set(c.favoritos || []);
          r.favorito ? lista.add(p.codigo) : lista.delete(p.codigo);
          c.favoritos = [...lista];
          guardarCliente(c);
          dibujar(); dibujarGrilla();
        } catch (error) { aviso(error.message, "error"); }
      }
    };
    dibujar();
    if (!dialogoPrenda.open) dialogoPrenda.showModal();
  }

  // ---------------------------------------------------------------- cuenta
  function abrirCuenta(modo) {
    const c = cliente();
    const caja = $("#detalle-cuenta");
    if (c) {
      caja.innerHTML = `
        <button class="dialogo-cerrar" type="button" data-cerrar aria-label="Cerrar">×</button>
        <h2 id="titulo-cuenta">Hola, ${escapar(c.nombre)}</h2>
        <div class="tarjeta-cliente">
          <div><span class="nivel">${escapar(c.nivel)}</span> · ${escapar(c.beneficio)}</div>
          <div>Puntos: <strong>${c.puntos}</strong> (cada punto vale $1)</div>
          <div>Total comprado: ${precio(c.total_gastado)}</div>
          ${c.siguiente_nivel ? `<div class="tarjeta-meta">Te faltan ${precio(c.falta_para_siguiente)} para llegar a ${escapar(c.siguiente_nivel)}.</div>` : ""}
        </div>
        <div class="grupo"><div class="grupo-titulo">Tus cupones</div>
          ${(c.cupones || []).length ? c.cupones.map(cu => `<div>🎟️ <strong>${escapar(cu.codigo)}</strong> — ${escapar(cu.descripcion)}${cu.vence ? ` (vence ${new Date(cu.vence + "T00:00").toLocaleDateString("es-AR")})` : ""}</div>`).join("")
            : "<div class='tarjeta-meta'>No tenés cupones vigentes.</div>"}
        </div>
        <div class="fila-botones"><button class="boton boton-claro" type="button" data-salir>Cerrar sesión</button></div>`;
    } else {
      const registro = modo === "registro";
      caja.innerHTML = `
        <button class="dialogo-cerrar" type="button" data-cerrar aria-label="Cerrar">×</button>
        <h2 id="titulo-cuenta">${registro ? "Crear mi cuenta" : "Ingresar"}</h2>
        <div class="pestanas">
          <button class="chip" type="button" data-modo="ingreso" aria-pressed="${!registro}">Ya tengo cuenta</button>
          <button class="chip" type="button" data-modo="registro" aria-pressed="${registro}">Soy nueva/o</button>
        </div>
        <form id="form-cuenta">
          ${registro ? `
            <div class="dos-columnas">
              <div class="campo"><label for="c-nombre">Nombre</label><input id="c-nombre" name="nombre" required autocomplete="given-name"></div>
              <div class="campo"><label for="c-apellido">Apellido</label><input id="c-apellido" name="apellido" autocomplete="family-name"></div>
            </div>` : ""}
          <div class="campo"><label for="c-email">Email</label><input id="c-email" name="email" type="email" required autocomplete="email"></div>
          ${registro ? `
            <div class="dos-columnas">
              <div class="campo"><label for="c-nacimiento">Fecha de nacimiento</label><input id="c-nacimiento" name="fecha_nacimiento" type="date"></div>
              <div class="campo"><label for="c-talle">Talle preferido</label>
                <select id="c-talle" name="talle_preferido"><option value="">—</option>${["XS", "S", "M", "L", "XL"].map(t => `<option>${t}</option>`).join("")}</select></div>
            </div>
            <label><input type="checkbox" name="acepta_promociones"> Quiero recibir promociones</label>
            <p class="tarjeta-meta">Al crear tu cuenta recibís un cupón de bienvenida del 15%.</p>` : ""}
          <div class="fila-botones"><button class="boton" type="submit">${registro ? "Crear cuenta" : "Ingresar"}</button></div>
        </form>`;
      caja.querySelector("#form-cuenta").onsubmit = async (e) => {
        e.preventDefault();
        const datos = Object.fromEntries(new FormData(e.target));
        try {
          let nuevo;
          if (registro) {
            nuevo = await api("clientes", {
              nombre: datos.nombre, apellido: datos.apellido || "", email: datos.email,
              fecha_nacimiento: datos.fecha_nacimiento || null, talle_preferido: datos.talle_preferido || null,
              acepta_promociones: Boolean(datos.acepta_promociones),
            });
            aviso("¡Cuenta creada! Te regalamos un cupón del 15%.", "ok");
          } else {
            nuevo = await api("clientes/ingresar", { email: datos.email });
            aviso(`¡Hola, ${nuevo.nombre}!`, "ok");
          }
          guardarCliente(nuevo);
          abrirCuenta();
        } catch (error) { aviso(error.message, "error"); }
      };
    }
    caja.onclick = (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.cerrar !== undefined) dialogoCuenta.close();
      else if (b.dataset.modo) abrirCuenta(b.dataset.modo);
      else if (b.dataset.salir !== undefined) { guardarCliente(null); estado.favoritos = false; abrirCuenta(); }
    };
    if (!dialogoCuenta.open) dialogoCuenta.showModal();
  }

  async function refrescarCliente() {
    const c = cliente();
    if (!c || !estado.ventas) return;
    try { guardarCliente(await api(`clientes/${c.id_cliente}`)); } catch (e) { /* queda la sesión guardada */ }
  }

  // ---------------------------------------------------------------- compra
  function abrirCompra(p, color, talle, idPrueba) {
    const c = cliente();
    const caja = $("#detalle-compra");
    caja.innerHTML = `
      <button class="dialogo-cerrar" type="button" data-cerrar aria-label="Cerrar">×</button>
      <h2 id="titulo-compra">Confirmar compra</h2>
      <p><strong>${escapar(p.nombre)}</strong> · ${escapar(color)} · talle ${escapar(talle)} · ${precio(p.precio)} c/u</p>
      ${c ? "" : `<p class="tarjeta-meta">Comprás como invitada/o. <button class="boton boton-claro boton-chico" type="button" data-cuenta>Ingresar</button> para sumar puntos y usar tus cupones.</p>`}
      <div class="dos-columnas">
        <div class="campo"><label for="compra-cantidad">Cantidad</label>
          <input id="compra-cantidad" type="number" min="1" max="${Math.min(10, stockDe(p, color, talle))}" value="1"></div>
        ${c ? `<div class="campo"><label for="compra-cupon">Cupón</label>
          <select id="compra-cupon"><option value="">Sin cupón</option>${(c.cupones || []).map(cu =>
            `<option value="${escapar(cu.codigo)}">${escapar(cu.codigo)} — ${escapar(cu.descripcion)}</option>`).join("")}</select></div>` : ""}
      </div>
      ${c && c.puntos > 0 ? `<label><input type="checkbox" id="compra-puntos"> Usar mis ${c.puntos} puntos (hasta el 30% del total)</label>` : ""}
      <div class="resumen-compra" id="resumen-compra" aria-live="polite">Calculando…</div>
      <div class="fila-botones"><button class="boton boton-dorado" type="button" data-confirmar>Confirmar compra</button></div>`;

    const pedido = () => ({
      items: [{ id_prenda: p.id_prenda, color, talle, cantidad: Math.max(1, parseInt(caja.querySelector("#compra-cantidad").value, 10) || 1) }],
      id_cliente: c ? c.id_cliente : null,
      cupon: c && caja.querySelector("#compra-cupon") ? caja.querySelector("#compra-cupon").value || null : null,
      usar_puntos: Boolean(caja.querySelector("#compra-puntos") && caja.querySelector("#compra-puntos").checked),
      id_prueba: idPrueba || null,
    });

    async function cotizar() {
      try {
        const d = await api("cotizar", pedido());
        caja.querySelector("#resumen-compra").innerHTML = `
          <div><span>Subtotal</span><span>${precio(d.subtotal)}</span></div>
          ${d.descuento_nivel ? `<div><span>Descuento nivel ${escapar(c.nivel)}</span><span>−${precio(d.descuento_nivel)}</span></div>` : ""}
          ${d.descuento_cupon ? `<div><span>Cupón</span><span>−${precio(d.descuento_cupon)}</span></div>` : ""}
          ${d.descuento_puntos ? `<div><span>Puntos</span><span>−${precio(d.descuento_puntos)}</span></div>` : ""}
          <div class="total"><span>Total</span><span>${precio(d.total)}</span></div>
          ${d.puntos_ganados ? `<div class="tarjeta-meta"><span>Sumás ${d.puntos_ganados} puntos ⭐</span></div>` : ""}`;
      } catch (error) {
        caja.querySelector("#resumen-compra").textContent = error.message;
      }
    }

    caja.oninput = cotizar;
    caja.onclick = async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.cerrar !== undefined) dialogoCompra.close();
      else if (b.dataset.cuenta !== undefined) { dialogoCompra.close(); abrirCuenta(); }
      else if (b.dataset.confirmar !== undefined) {
        b.disabled = true;
        try {
          const r = await api("compras", pedido());
          if (r.cliente) guardarCliente(r.cliente);
          let texto = `¡Gracias por tu compra! Compra #${r.id_compra} por ${precio(r.detalle.total)}.`;
          if (r.detalle.puntos_ganados) texto += ` Sumaste ${r.detalle.puntos_ganados} puntos.`;
          if (r.nivel_nuevo) texto += ` ¡Subiste a nivel ${r.nivel_nuevo}!`;
          aviso(texto, "ok");
          dialogoCompra.close();
          await recargarCatalogo();
          if (dialogoPrenda.open) abrirPrenda(p.codigo, color, talle);
        } catch (error) {
          aviso(error.message, "error");
          b.disabled = false;
        }
      }
    };
    dialogoCompra.showModal();
    cotizar();
  }

  // ---------------------------------------------------------------- arranque
  async function recargarCatalogo() {
    const r = await Comun.cargarCatalogo();
    estado.prendas = r.prendas;
    estado.ventas = r.ventas;
    $("#estado-tienda").textContent = r.ventas
      ? `${r.prendas.length} prendas · stock en vivo`
      : `${r.prendas.length} prendas · modo vidriera (sin base de datos: no se puede comprar)`;
    dibujarFiltros();
    dibujarGrilla();
  }

  $("#filtros").onclick = (e) => {
    const b = e.target.closest("[data-categoria]");
    if (!b) return;
    const c = b.dataset.categoria;
    estado.favoritos = c === "♥ Favoritos";
    if (!estado.favoritos) estado.categoria = c;
    dibujarFiltros();
    dibujarGrilla();
  };
  $("#grilla").onclick = (e) => {
    const t = e.target.closest("[data-codigo]");
    if (t) abrirPrenda(t.dataset.codigo);
  };
  $("#boton-cuenta").onclick = () => abrirCuenta();
  window.addEventListener("cliente-cambio", (e) => {
    $("#boton-cuenta").textContent = e.detail ? `Hola, ${e.detail.nombre}` : "Mi cuenta";
    dibujarFiltros();
    dibujarGrilla();
  });
  // Cerrar las ventanas tocando afuera
  for (const d of [dialogoPrenda, dialogoCuenta, dialogoCompra]) {
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
  }

  (async () => {
    try {
      await recargarCatalogo();
    } catch (error) {
      $("#estado-tienda").textContent = "No se pudo cargar el catálogo.";
      return;
    }
    const c = cliente();
    if (c) $("#boton-cuenta").textContent = `Hola, ${c.nombre}`;
    await refrescarCliente();
    // Al volver del probador se abre la prenda que se estaba probando
    const q = new URLSearchParams(location.search);
    if (q.get("prenda")) {
      abrirPrenda(q.get("prenda"), q.get("color"), q.get("talle"));
      history.replaceState(null, "", "./");
    }
  })();
})();
