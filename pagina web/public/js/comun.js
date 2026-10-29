// ==========================================================
// PROBADOR VIRTUAL INTELIGENTE - PÁGINA WEB
// Funciones compartidas por la tienda y el probador: API, catálogo, sesión y avisos.
// ==========================================================

const Comun = (() => {
  const CLAVE_SESION = "vestidor.cliente";

  async function api(ruta, datos) {
    const opciones = datos === undefined ? {} : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos),
    };
    let respuesta;
    try {
      respuesta = await fetch(`/api/${ruta}`, opciones);
    } catch (e) {
      throw new Error("No hay conexión con la tienda.");
    }
    let cuerpo = null;
    try { cuerpo = await respuesta.json(); } catch (e) { /* respuesta vacía */ }
    if (!respuesta.ok) {
      throw new Error((cuerpo && cuerpo.detail && typeof cuerpo.detail === "string")
        ? cuerpo.detail : "La tienda no pudo responder. Probá de nuevo.");
    }
    return cuerpo;
  }

  // Catálogo = fotos y malla (datos/catalogo.json, exportado del probador) + precio y
  // stock en vivo de la base (API). Si la API no tiene base, queda el stock exportado
  // y la tienda funciona como vidriera (sin compras).
  async function cargarCatalogo() {
    const estatico = await (await fetch("datos/catalogo.json")).json();
    let enVivo = null;
    try {
      enVivo = await api("prendas");
    } catch (e) {
      console.info("Catálogo sin base en vivo:", e.message);
    }
    const porCodigo = new Map((enVivo ? enVivo.prendas : []).map(p => [p.codigo, p]));
    const prendas = estatico.prendas
      .filter(p => !enVivo || porCodigo.has(p.codigo))
      .map(p => ({ ...p, ...(porCodigo.get(p.codigo) || {}) }));
    return { prendas, ventas: Boolean(enVivo) };
  }

  function precio(valor) {
    return "$" + Math.round(Number(valor) || 0).toLocaleString("es-AR");
  }

  function stockDe(prenda, color, talle) {
    return Number((prenda.stock || {})[`${color}|${talle}`] || 0);
  }

  function stockTotal(prenda) {
    return Object.values(prenda.stock || {}).reduce((a, b) => a + Number(b), 0);
  }

  // La sesión del cliente vive en este navegador (como "Mi cuenta" del programa)
  function cliente() {
    try { return JSON.parse(localStorage.getItem(CLAVE_SESION)); } catch (e) { return null; }
  }

  function guardarCliente(datos) {
    try {
      if (datos) localStorage.setItem(CLAVE_SESION, JSON.stringify(datos));
      else localStorage.removeItem(CLAVE_SESION);
    } catch (e) { /* navegador sin almacenamiento: la sesión dura hasta recargar */ }
    window.dispatchEvent(new CustomEvent("cliente-cambio", { detail: datos }));
  }

  function aviso(texto, tipo = "info") {
    let zona = document.querySelector(".avisos");
    if (!zona) {
      zona = document.createElement("div");
      zona.className = "avisos";
      zona.setAttribute("role", "status");
      document.body.appendChild(zona);
    }
    const el = document.createElement("div");
    el.className = `aviso aviso-${tipo}`;
    el.textContent = texto;
    zona.appendChild(el);
    setTimeout(() => el.classList.add("saliendo"), 3800);
    setTimeout(() => el.remove(), 4300);
  }

  function escapar(texto) {
    const d = document.createElement("div");
    d.textContent = texto == null ? "" : String(texto);
    return d.innerHTML;
  }

  return { api, cargarCatalogo, precio, stockDe, stockTotal, cliente, guardarCliente, aviso, escapar };
})();
