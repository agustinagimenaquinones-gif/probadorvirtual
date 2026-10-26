-- ============================================================
-- PROBADOR VIRTUAL INTELIGENTE - VESTIDOR VIRTUAL
-- Script para MySQL / MySQL Workbench
-- Requiere MySQL 8.0.16 o más nuevo (en versiones anteriores los CHECK se ignoran).
--
-- Cinco tablas:
--   tienda    los locales que usan el probador, con su equipo
--   prenda    cada prenda con sus colores, talles (y medidas) y stock
--   clientes  los clientes con su programa de fidelidad (nivel, puntos, cupones, favoritos)
--   prueba    cada vez que alguien se prueba una prenda con la cámara (sin imágenes)
--   compra    cada compra, con sus prendas y sus descuentos
--
-- Lo que se repite dentro de una fila (los colores de una prenda, el stock de cada
-- color y talle, los cupones de un cliente, las prendas de una compra) se guarda en
-- columnas JSON. Los niveles de fidelidad están en tienda.py (NIVELES).
--
-- Instalación nueva: ejecutar este script y después cargar el catálogo con
--     .venv\Scripts\python.exe cargar_prendas_mysql.py --crear-tablas
-- Base con las 16 tablas de la versión anterior: pasar los datos con
--     .venv\Scripts\python.exe migrar_a_5_tablas.py
-- ============================================================

CREATE DATABASE IF NOT EXISTS probador_virtual
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE probador_virtual;

-- 1. Tiendas físicas que usan el sistema.
-- equipos: [{"tipo": "pantalla" | "camara" | "computadora", "ubicacion", "estado"}]
CREATE TABLE IF NOT EXISTS tienda (
    id_tienda INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    direccion VARCHAR(255),
    ciudad VARCHAR(100),
    telefono VARCHAR(30),
    email VARCHAR(150),
    equipos JSON NULL,
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Prendas del catálogo.
-- ajuste_foto: {"margen_hombros", "margen_cuello", "rotacion", "voltear_horizontal", "voltear_vertical"}
-- colores:     [{"nombre", "hex", "es_foto"}]  (el de la foto primero; los demás se tiñen)
-- talles:      [{"talle", "pecho", "cintura", "cadera", "hombros", "largo"}]  (en cm, en orden)
-- stock:       {"Azul Marino|M": {"sku": "VV-0011-AZM-M", "stock": 5}, ...}
CREATE TABLE IF NOT EXISTS prenda (
    id_prenda INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(80) NOT NULL UNIQUE,
    sku VARCHAR(20) NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    categoria VARCHAR(80) NOT NULL,
    genero ENUM('mujer', 'hombre', 'unisex', 'infantil') NOT NULL DEFAULT 'unisex',
    precio DECIMAL(10,2) NOT NULL,
    calce ENUM('entallado', 'regular', 'holgado') NOT NULL DEFAULT 'regular',
    imagen_url VARCHAR(500) NOT NULL,
    ajuste_foto JSON NULL,
    colores JSON NOT NULL,
    talles JSON NOT NULL,
    stock JSON NOT NULL,
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_prenda_precio CHECK (precio >= 0),
    CONSTRAINT chk_prenda_colores CHECK (JSON_TYPE(colores) = 'ARRAY'),
    CONSTRAINT chk_prenda_talles CHECK (JSON_TYPE(talles) = 'ARRAY'),
    CONSTRAINT chk_prenda_stock CHECK (JSON_TYPE(stock) = 'OBJECT'),
    INDEX idx_prenda_categoria (categoria)
) ENGINE=InnoDB;

-- 3. Clientes y su programa de fidelidad.
-- nivel: Bronce, Plata, Oro o Diamante (las reglas de cada uno están en tienda.py)
-- cupones:   [{"codigo", "descripcion", "tipo", "valor", "compra_minima", "vence", "usado", "creado"}]
-- favoritos: [id_prenda, ...]
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    apellido VARCHAR(80),
    email VARCHAR(150) NOT NULL UNIQUE,
    telefono VARCHAR(30),
    fecha_nacimiento DATE NULL,
    talle_preferido VARCHAR(20) NULL,
    acepta_promociones BOOLEAN NOT NULL DEFAULT FALSE,
    nivel ENUM('Bronce', 'Plata', 'Oro', 'Diamante') NOT NULL DEFAULT 'Bronce',
    puntos INT NOT NULL DEFAULT 0,
    total_gastado DECIMAL(12,2) NOT NULL DEFAULT 0,
    cupones JSON NULL,
    favoritos JSON NULL,
    fecha_alta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultima_visita DATETIME NULL,
    CONSTRAINT chk_cliente_puntos CHECK (puntos >= 0)
) ENGINE=InnoDB;

-- 4. Pruebas: cada vez que alguien se prueba una prenda con la cámara.
-- Nunca se guardan fotos ni video: sólo qué prenda, en qué color y talle, cuánto tiempo
-- y si terminó en compra.
CREATE TABLE IF NOT EXISTS prueba (
    id_prueba INT AUTO_INCREMENT PRIMARY KEY,
    id_prenda INT NOT NULL,
    id_cliente INT NULL,
    id_tienda INT NULL,
    tipo ENUM('tienda', 'online') NOT NULL DEFAULT 'online',
    color VARCHAR(50),
    talle VARCHAR(20),
    segundos INT NOT NULL DEFAULT 0,
    compro BOOLEAN NOT NULL DEFAULT FALSE,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_prueba_segundos CHECK (segundos >= 0),
    CONSTRAINT fk_prueba_prenda
        FOREIGN KEY (id_prenda) REFERENCES prenda(id_prenda)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_prueba_cliente
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_prueba_tienda
        FOREIGN KEY (id_tienda) REFERENCES tienda(id_tienda)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_prueba_fecha (fecha)
) ENGINE=InnoDB;

-- 5. Compras: una fila por compra completa.
-- detalle: [{"id_prenda", "sku", "nombre", "color", "talle", "cantidad", "precio"}]
CREATE TABLE IF NOT EXISTS compra (
    id_compra INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NULL,
    id_tienda INT NULL,
    id_prueba INT NULL,
    detalle JSON NOT NULL,
    subtotal DECIMAL(12,2) NOT NULL,
    descuento_nivel DECIMAL(12,2) NOT NULL DEFAULT 0,
    descuento_cupon DECIMAL(12,2) NOT NULL DEFAULT 0,
    descuento_puntos DECIMAL(12,2) NOT NULL DEFAULT 0,
    total DECIMAL(12,2) NOT NULL,
    cupon VARCHAR(30) NULL,
    puntos_usados INT NOT NULL DEFAULT 0,
    puntos_ganados INT NOT NULL DEFAULT 0,
    estado ENUM('pendiente', 'pagada', 'cancelada', 'entregada') NOT NULL DEFAULT 'pagada',
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_compra_total CHECK (total >= 0 AND subtotal >= 0),
    CONSTRAINT chk_compra_detalle CHECK (JSON_TYPE(detalle) = 'ARRAY'),
    CONSTRAINT fk_compra_cliente
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_compra_tienda
        FOREIGN KEY (id_tienda) REFERENCES tienda(id_tienda)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_compra_prueba
        FOREIGN KEY (id_prueba) REFERENCES prueba(id_prueba)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_compra_fecha (fecha)
) ENGINE=InnoDB;

-- ============================================================
-- CONSULTAS DE PRUEBA (ejecutarlas después de cargar el catálogo)
-- ============================================================

-- Stock de cada variante (prenda, color y talle):
-- SELECT p.sku, p.nombre, v.variante, JSON_UNQUOTE(JSON_EXTRACT(p.stock, CONCAT('$."', v.variante, '".sku'))) AS sku_variante,
--        JSON_EXTRACT(p.stock, CONCAT('$."', v.variante, '".stock')) AS unidades
-- FROM prenda p
-- JOIN JSON_TABLE(JSON_KEYS(p.stock), '$[*]' COLUMNS (variante VARCHAR(80) PATH '$')) v
-- ORDER BY p.sku, v.variante;

-- Clientes con su nivel y puntos:
-- SELECT nombre, email, nivel, puntos, total_gastado FROM clientes;

-- Compras con sus prendas:
-- SELECT c.id_compra, c.fecha, cl.email, d.sku, d.nombre, d.cantidad, c.total
-- FROM compra c
-- LEFT JOIN clientes cl ON cl.id_cliente = c.id_cliente
-- JOIN JSON_TABLE(c.detalle, '$[*]' COLUMNS (sku VARCHAR(40) PATH '$.sku', nombre VARCHAR(150) PATH '$.nombre',
--                                           cantidad INT PATH '$.cantidad')) d;

-- Pruebas que terminaron en compra, por prenda:
-- SELECT p.nombre, COUNT(*) AS pruebas, SUM(pr.compro) AS compras, ROUND(AVG(pr.segundos)) AS segundos_promedio
-- FROM prueba pr JOIN prenda p ON p.id_prenda = pr.id_prenda
-- GROUP BY p.id_prenda ORDER BY pruebas DESC;
