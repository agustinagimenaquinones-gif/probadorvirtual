-- ============================================================
-- PROBADOR VIRTUAL INTELIGENTE - VESTIDOR VIRTUAL
-- Script para MySQL / MySQL Workbench
-- Requiere MySQL 8.0.16 o más nuevo (en versiones anteriores los CHECK se ignoran).
--
-- Instalación nueva: ejecutar este script y después cargar el catálogo con
--     .venv\Scripts\python.exe cargar_prendas_mysql.py --crear-tablas
-- Base ya existente: el mismo comando agrega las columnas y tablas que falten
-- (ver conexion_mysql.migrar_base) sin borrar datos.
-- ============================================================

CREATE DATABASE IF NOT EXISTS probador_virtual
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE probador_virtual;

-- 1. Tiendas físicas que utilizan el sistema
CREATE TABLE IF NOT EXISTS tiendas (
    id_tienda INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    direccion VARCHAR(255),
    ciudad VARCHAR(100),
    telefono VARCHAR(30),
    email VARCHAR(150),
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Colores (un solo nombre por color, así no hay "Rojo" y "rojo" por separado)
-- hex: el color con que el probador "tiñe" la foto para mostrar esa variante.
CREATE TABLE IF NOT EXISTS colores (
    id_color INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    hex CHAR(7) NULL
) ENGINE=InnoDB;

-- 3. Prendas del catálogo
-- codigo: identificador que usa el programa (el nombre del PNG sin extensión).
-- sku: código de identificación comercial de la prenda (ej. VV-0001).
-- imagen_url: ruta del PNG relativa a la carpeta del proyecto (ej. prendas/remera_fitted_negra.png).
-- id_color_foto: color que tiene la prenda en la foto (los demás colores se generan tiñéndola).
-- calce, margenes, rotacion y volteos: datos que necesita el probador para dibujar la prenda.
CREATE TABLE IF NOT EXISTS prendas (
    id_prenda INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(80) NOT NULL UNIQUE,
    sku VARCHAR(20) NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    categoria VARCHAR(80) NOT NULL,
    genero ENUM('mujer', 'hombre', 'unisex', 'infantil') NOT NULL DEFAULT 'unisex',
    precio DECIMAL(10,2) NOT NULL,
    imagen_url VARCHAR(500) NOT NULL,
    id_color_foto INT NULL,
    calce ENUM('entallado', 'regular', 'holgado') NOT NULL DEFAULT 'regular',
    margen_hombros DECIMAL(4,2) NOT NULL DEFAULT 0.38,
    margen_cuello DECIMAL(4,2) NOT NULL DEFAULT 0.20,
    rotacion SMALLINT NOT NULL DEFAULT 0,
    voltear_horizontal BOOLEAN NOT NULL DEFAULT FALSE,
    voltear_vertical BOOLEAN NOT NULL DEFAULT FALSE,
    estado ENUM('activa', 'inactiva') NOT NULL DEFAULT 'activa',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_prendas_precio CHECK (precio >= 0),
    CONSTRAINT chk_prendas_rotacion CHECK (rotacion IN (0, 90, 180, 270)),
    CONSTRAINT fk_prendas_color_foto
        FOREIGN KEY (id_color_foto) REFERENCES colores(id_color)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_prendas_categoria (categoria)
) ENGINE=InnoDB;

-- 4. Talles disponibles
CREATE TABLE IF NOT EXISTS talles (
    id_talle INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(20) NOT NULL UNIQUE,
    orden INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

-- 5. Medidas físicas de cada prenda por talle (en cm)
CREATE TABLE IF NOT EXISTS medidas_talle (
    id_prenda INT NOT NULL,
    id_talle INT NOT NULL,
    pecho SMALLINT NOT NULL,
    cintura SMALLINT NOT NULL,
    cadera SMALLINT NOT NULL,
    hombros SMALLINT NOT NULL,
    largo SMALLINT NOT NULL,
    PRIMARY KEY (id_prenda, id_talle),
    CONSTRAINT chk_medidas_positivas
        CHECK (pecho > 0 AND cintura > 0 AND cadera > 0 AND hombros > 0 AND largo > 0),
    CONSTRAINT fk_medidas_prenda
        FOREIGN KEY (id_prenda) REFERENCES prendas(id_prenda)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_medidas_talle
        FOREIGN KEY (id_talle) REFERENCES talles(id_talle)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 6. Inventario: cada fila es una variante (prenda + talle + color) con su stock.
-- sku: código de la variante (ej. VV-0001-NEG-M).
-- Las selecciones y compras apuntan a esta tabla, así sólo se pueden registrar
-- combinaciones que existen.
CREATE TABLE IF NOT EXISTS inventario (
    id_inventario INT AUTO_INCREMENT PRIMARY KEY,
    id_prenda INT NOT NULL,
    id_talle INT NOT NULL,
    id_color INT NOT NULL,
    sku VARCHAR(40) NULL UNIQUE,
    stock INT NOT NULL DEFAULT 0,
    CONSTRAINT chk_inventario_stock CHECK (stock >= 0),
    CONSTRAINT fk_inventario_prenda
        FOREIGN KEY (id_prenda) REFERENCES prendas(id_prenda)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_inventario_talle
        FOREIGN KEY (id_talle) REFERENCES talles(id_talle)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_inventario_color
        FOREIGN KEY (id_color) REFERENCES colores(id_color)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    -- Este índice también sirve para buscar por id_prenda (no hace falta otro).
    CONSTRAINT uq_inventario_prenda_talle_color
        UNIQUE (id_prenda, id_talle, id_color)
) ENGINE=InnoDB;

-- 7. Dispositivos instalados en cada tienda
CREATE TABLE IF NOT EXISTS dispositivos_tienda (
    id_dispositivo INT AUTO_INCREMENT PRIMARY KEY,
    id_tienda INT NOT NULL,
    tipo ENUM('pantalla', 'camara', 'computadora', 'otro') NOT NULL,
    ubicacion VARCHAR(150),
    estado ENUM('activo', 'inactivo', 'mantenimiento') NOT NULL DEFAULT 'activo',
    fecha_instalacion DATE,
    CONSTRAINT fk_dispositivos_tienda
        FOREIGN KEY (id_tienda) REFERENCES tiendas(id_tienda)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- 8. Sesiones del probador
-- Por privacidad, no se almacenan fotos ni videos de clientes.
-- id_dispositivo: pantalla de la tienda usada (sólo sesiones en tienda).
-- dispositivo: tipo de equipo, sirve también para las sesiones online.
CREATE TABLE IF NOT EXISTS sesiones_prueba (
    id_sesion INT AUTO_INCREMENT PRIMARY KEY,
    id_tienda INT NULL,
    id_dispositivo INT NULL,
    tipo_sesion ENUM('tienda', 'online') NOT NULL,
    dispositivo ENUM('pantalla', 'web', 'movil', 'pc') NULL,
    fecha_inicio DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_fin DATETIME NULL,
    estado ENUM('activa', 'finalizada', 'cancelada') NOT NULL DEFAULT 'activa',
    CONSTRAINT chk_sesiones_fechas CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
    CONSTRAINT fk_sesiones_tienda
        FOREIGN KEY (id_tienda) REFERENCES tiendas(id_tienda)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_sesiones_dispositivo
        FOREIGN KEY (id_dispositivo) REFERENCES dispositivos_tienda(id_dispositivo)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_sesiones_fecha (fecha_inicio)
) ENGINE=InnoDB;

-- 9. Prendas elegidas durante una sesión
CREATE TABLE IF NOT EXISTS prendas_seleccionadas (
    id_seleccion INT AUTO_INCREMENT PRIMARY KEY,
    id_sesion INT NOT NULL,
    id_inventario INT NOT NULL,
    fecha_seleccion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_seleccion_sesion
        FOREIGN KEY (id_sesion) REFERENCES sesiones_prueba(id_sesion)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_seleccion_inventario
        FOREIGN KEY (id_inventario) REFERENCES inventario(id_inventario)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_selecciones_sesion (id_sesion)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- CLIENTES Y PROGRAMA DE FIDELIDAD
-- ------------------------------------------------------------

-- 10. Niveles del programa de fidelidad: se sube de nivel según lo gastado
CREATE TABLE IF NOT EXISTS niveles_fidelidad (
    id_nivel INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL UNIQUE,
    gasto_minimo DECIMAL(12,2) NOT NULL DEFAULT 0,
    descuento_pct DECIMAL(4,1) NOT NULL DEFAULT 0,
    beneficio VARCHAR(255),
    orden INT NOT NULL DEFAULT 0,
    CONSTRAINT chk_niveles_descuento CHECK (descuento_pct BETWEEN 0 AND 50)
) ENGINE=InnoDB;

-- 11. Clientes. Sólo se guardan los datos que la persona elige dar; acepta_promociones
-- registra su consentimiento para recibir novedades.
CREATE TABLE IF NOT EXISTS clientes (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    apellido VARCHAR(80),
    email VARCHAR(150) NOT NULL UNIQUE,
    telefono VARCHAR(30),
    fecha_nacimiento DATE NULL,
    talle_preferido VARCHAR(20) NULL,
    acepta_promociones BOOLEAN NOT NULL DEFAULT FALSE,
    id_nivel INT NOT NULL DEFAULT 1,
    puntos INT NOT NULL DEFAULT 0,
    total_gastado DECIMAL(12,2) NOT NULL DEFAULT 0,
    fecha_alta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultima_visita DATETIME NULL,
    CONSTRAINT chk_clientes_puntos CHECK (puntos >= 0),
    CONSTRAINT fk_clientes_nivel
        FOREIGN KEY (id_nivel) REFERENCES niveles_fidelidad(id_nivel)
        ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 12. Cupones de descuento (de bienvenida, de cumpleaños o generales si id_cliente es NULL)
CREATE TABLE IF NOT EXISTS cupones (
    id_cupon INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    id_cliente INT NULL,
    descripcion VARCHAR(150),
    tipo ENUM('porcentaje', 'monto') NOT NULL DEFAULT 'porcentaje',
    valor DECIMAL(10,2) NOT NULL,
    compra_minima DECIMAL(10,2) NOT NULL DEFAULT 0,
    vence DATE NULL,
    usado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_uso DATETIME NULL,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cupones_valor CHECK (valor > 0),
    CONSTRAINT fk_cupones_cliente
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- 13. Prendas favoritas de cada cliente
CREATE TABLE IF NOT EXISTS favoritos (
    id_cliente INT NOT NULL,
    id_prenda INT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id_cliente, id_prenda),
    CONSTRAINT fk_favoritos_cliente
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_favoritos_prenda
        FOREIGN KEY (id_prenda) REFERENCES prendas(id_prenda)
        ON UPDATE CASCADE ON DELETE CASCADE
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- VENTAS Y STOCK
-- ------------------------------------------------------------

-- 14. Pedidos: una compra completa de un cliente (puede tener varias prendas)
CREATE TABLE IF NOT EXISTS pedidos (
    id_pedido INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NULL,
    id_tienda INT NULL,
    id_sesion INT NULL,
    id_cupon INT NULL,
    subtotal DECIMAL(12,2) NOT NULL,
    descuento_nivel DECIMAL(12,2) NOT NULL DEFAULT 0,
    descuento_cupon DECIMAL(12,2) NOT NULL DEFAULT 0,
    descuento_puntos DECIMAL(12,2) NOT NULL DEFAULT 0,
    total DECIMAL(12,2) NOT NULL,
    puntos_usados INT NOT NULL DEFAULT 0,
    puntos_ganados INT NOT NULL DEFAULT 0,
    estado ENUM('pendiente', 'pagado', 'cancelado', 'entregado') NOT NULL DEFAULT 'pagado',
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_pedidos_total CHECK (total >= 0 AND subtotal >= 0),
    CONSTRAINT fk_pedidos_cliente
        FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_pedidos_tienda
        FOREIGN KEY (id_tienda) REFERENCES tiendas(id_tienda)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_pedidos_sesion
        FOREIGN KEY (id_sesion) REFERENCES sesiones_prueba(id_sesion)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_pedidos_cupon
        FOREIGN KEY (id_cupon) REFERENCES cupones(id_cupon)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_pedidos_fecha (fecha)
) ENGINE=InnoDB;

-- 15. Compras: cada prenda (variante) de un pedido.
-- id_sesion (opcional) permite medir cuántas pruebas terminan en compra.
CREATE TABLE IF NOT EXISTS compras (
    id_compra INT AUTO_INCREMENT PRIMARY KEY,
    id_pedido INT NULL,
    id_tienda INT NULL,
    id_sesion INT NULL,
    id_inventario INT NOT NULL,
    cantidad INT NOT NULL DEFAULT 1,
    precio_unitario DECIMAL(10,2) NOT NULL,
    fecha_compra DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado ENUM('pendiente', 'pagada', 'cancelada', 'entregada') NOT NULL DEFAULT 'pendiente',
    CONSTRAINT chk_compras_cantidad CHECK (cantidad > 0),
    CONSTRAINT chk_compras_precio CHECK (precio_unitario >= 0),
    CONSTRAINT fk_compras_pedido
        FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_compras_tienda
        FOREIGN KEY (id_tienda) REFERENCES tiendas(id_tienda)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_compras_sesion
        FOREIGN KEY (id_sesion) REFERENCES sesiones_prueba(id_sesion)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_compras_inventario
        FOREIGN KEY (id_inventario) REFERENCES inventario(id_inventario)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_compras_sesion (id_sesion)
) ENGINE=InnoDB;

-- 16. Movimientos de stock: cada venta, reposición o ajuste queda registrado
-- (cantidad negativa = sale del stock).
CREATE TABLE IF NOT EXISTS movimientos_stock (
    id_movimiento INT AUTO_INCREMENT PRIMARY KEY,
    id_inventario INT NOT NULL,
    cantidad INT NOT NULL,
    motivo ENUM('venta', 'reposicion', 'ajuste', 'devolucion', 'carga_inicial') NOT NULL,
    id_pedido INT NULL,
    stock_resultante INT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_movimientos_inventario
        FOREIGN KEY (id_inventario) REFERENCES inventario(id_inventario)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_movimientos_pedido
        FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido)
        ON UPDATE CASCADE ON DELETE SET NULL,
    INDEX idx_movimientos_fecha (fecha)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- Reglas que un CHECK no puede validar (MySQL no permite CHECK sobre columnas
-- con ON DELETE SET NULL), así que se validan con triggers:
--   * una sesión 'tienda' tiene que tener id_tienda;
--   * el dispositivo usado tiene que pertenecer a esa tienda.
-- Cuando se borra una tienda, MySQL pone id_tienda en NULL sin ejecutar estos
-- triggers, así que el borrado sigue funcionando.
-- ------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_sesiones_validar_insert;
DROP TRIGGER IF EXISTS trg_sesiones_validar_update;

DELIMITER $$

CREATE TRIGGER trg_sesiones_validar_insert
BEFORE INSERT ON sesiones_prueba
FOR EACH ROW
BEGIN
    IF NEW.tipo_sesion = 'tienda' AND NEW.id_tienda IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Una sesion de tipo tienda necesita id_tienda';
    END IF;
    IF NEW.id_dispositivo IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM dispositivos_tienda d
        WHERE d.id_dispositivo = NEW.id_dispositivo AND d.id_tienda <=> NEW.id_tienda
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'El dispositivo no pertenece a la tienda de la sesion';
    END IF;
END$$

CREATE TRIGGER trg_sesiones_validar_update
BEFORE UPDATE ON sesiones_prueba
FOR EACH ROW
BEGIN
    IF NEW.tipo_sesion = 'tienda' AND NEW.id_tienda IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Una sesion de tipo tienda necesita id_tienda';
    END IF;
    IF NEW.id_dispositivo IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM dispositivos_tienda d
        WHERE d.id_dispositivo = NEW.id_dispositivo AND d.id_tienda <=> NEW.id_tienda
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'El dispositivo no pertenece a la tienda de la sesion';
    END IF;
END$$

DELIMITER ;

-- Talles iniciales
INSERT IGNORE INTO talles (nombre, orden) VALUES
('XS', 1), ('S', 2), ('M', 3), ('L', 4), ('XL', 5), ('XXL', 6), ('Único', 7);

-- Niveles del programa de fidelidad (gasto acumulado en pesos)
INSERT IGNORE INTO niveles_fidelidad (id_nivel, nombre, gasto_minimo, descuento_pct, beneficio, orden) VALUES
(1, 'Bronce',   0,      0,  'Cupón de bienvenida del 15% y 1 punto por cada $100', 1),
(2, 'Plata',    80000,  5,  '5% de descuento en todas tus compras', 2),
(3, 'Oro',      200000, 10, '10% de descuento y acceso anticipado a nuevas colecciones', 3),
(4, 'Diamante', 400000, 15, '15% de descuento, regalo de cumpleaños y asesoría de estilo', 4);

-- Stock legible: prenda, talle, color, SKU y unidades
CREATE OR REPLACE VIEW vista_stock AS
SELECT p.sku AS sku_prenda, i.sku AS sku_variante, p.nombre AS prenda, p.categoria, p.genero,
       t.nombre AS talle, c.nombre AS color, i.stock, p.precio
FROM inventario i
JOIN prendas p ON p.id_prenda = i.id_prenda
JOIN talles t ON t.id_talle = i.id_talle
JOIN colores c ON c.id_color = i.id_color
ORDER BY p.sku, c.nombre, t.orden;

-- ============================================================
-- CONSULTAS DE PRUEBA (ejecutarlas después de crear las tablas)
-- ============================================================

-- Stock de todas las variantes:
-- SELECT * FROM vista_stock;

-- Variantes agotadas:
-- SELECT * FROM vista_stock WHERE stock = 0;

-- Clientes con su nivel y puntos:
-- SELECT c.nombre, c.email, n.nombre AS nivel, c.puntos, c.total_gastado
-- FROM clientes c JOIN niveles_fidelidad n ON n.id_nivel = c.id_nivel;

-- Pedidos con sus prendas:
-- SELECT pe.id_pedido, pe.fecha, cl.email, v.sku_variante, v.prenda, co.cantidad, pe.total
-- FROM pedidos pe
-- LEFT JOIN clientes cl ON cl.id_cliente = pe.id_cliente
-- JOIN compras co ON co.id_pedido = pe.id_pedido
-- JOIN inventario i ON i.id_inventario = co.id_inventario
-- JOIN vista_stock v ON v.sku_variante = i.sku;

-- Movimientos de stock de una variante:
-- SELECT * FROM movimientos_stock WHERE id_inventario = 1 ORDER BY fecha;
