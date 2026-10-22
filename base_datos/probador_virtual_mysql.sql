-- ============================================================
-- PROBADOR VIRTUAL INTELIGENTE
-- Script para MySQL / MySQL Workbench
-- Requiere MySQL 8.0.16 o más nuevo (en versiones anteriores los CHECK se ignoran).
--
-- Después de ejecutarlo, cargar las prendas de la carpeta prendas/ con:
--     .venv\Scripts\python.exe cargar_prendas_mysql.py
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

-- 2. Prendas del catálogo
-- codigo: identificador que usa el programa (el nombre del PNG sin extensión).
-- imagen_url: ruta del PNG relativa a la carpeta del proyecto (ej. prendas/remera_roja.png).
-- calce, margenes, rotacion y volteos: datos que necesita el probador para dibujar la prenda.
-- El color no se guarda acá: cada variante de color está en inventario.
CREATE TABLE IF NOT EXISTS prendas (
    id_prenda INT AUTO_INCREMENT PRIMARY KEY,
    codigo VARCHAR(80) NOT NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    categoria VARCHAR(80) NOT NULL,
    genero ENUM('mujer', 'hombre', 'unisex', 'infantil') NOT NULL DEFAULT 'unisex',
    precio DECIMAL(10,2) NOT NULL,
    imagen_url VARCHAR(500) NOT NULL,
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
    INDEX idx_prendas_categoria (categoria)
) ENGINE=InnoDB;

-- 3. Talles disponibles
CREATE TABLE IF NOT EXISTS talles (
    id_talle INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(20) NOT NULL UNIQUE,
    orden INT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

-- 4. Colores (un solo nombre por color, así no hay "Rojo" y "rojo" por separado)
CREATE TABLE IF NOT EXISTS colores (
    id_color INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
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
-- Las selecciones y compras apuntan a esta tabla, así sólo se pueden registrar
-- combinaciones que existen.
CREATE TABLE IF NOT EXISTS inventario (
    id_inventario INT AUTO_INCREMENT PRIMARY KEY,
    id_prenda INT NOT NULL,
    id_talle INT NOT NULL,
    id_color INT NOT NULL,
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

-- 10. Compras: tabla preparada para una futura integración con ventas.
-- id_sesion (opcional) permite medir cuántas pruebas terminan en compra.
CREATE TABLE IF NOT EXISTS compras (
    id_compra INT AUTO_INCREMENT PRIMARY KEY,
    id_tienda INT NULL,
    id_sesion INT NULL,
    id_inventario INT NOT NULL,
    cantidad INT NOT NULL DEFAULT 1,
    precio_unitario DECIMAL(10,2) NOT NULL,
    fecha_compra DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado ENUM('pendiente', 'pagada', 'cancelada', 'entregada') NOT NULL DEFAULT 'pendiente',
    CONSTRAINT chk_compras_cantidad CHECK (cantidad > 0),
    CONSTRAINT chk_compras_precio CHECK (precio_unitario >= 0),
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

-- ============================================================
-- CONSULTAS DE PRUEBA (ejecutarlas después de crear las tablas)
-- ============================================================

-- Ver todas las prendas:
-- SELECT * FROM prendas;

-- Ver stock disponible:
-- SELECT p.nombre, t.nombre AS talle, c.nombre AS color, i.stock
-- FROM inventario i
-- JOIN prendas p ON p.id_prenda = i.id_prenda
-- JOIN talles t ON t.id_talle = i.id_talle
-- JOIN colores c ON c.id_color = i.id_color
-- WHERE i.stock > 0;

-- Ver prendas seleccionadas en cada sesión:
-- SELECT s.id_sesion, ps.fecha_seleccion, p.nombre, t.nombre AS talle, c.nombre AS color
-- FROM prendas_seleccionadas ps
-- JOIN sesiones_prueba s ON s.id_sesion = ps.id_sesion
-- JOIN inventario i ON i.id_inventario = ps.id_inventario
-- JOIN prendas p ON p.id_prenda = i.id_prenda
-- JOIN talles t ON t.id_talle = i.id_talle
-- JOIN colores c ON c.id_color = i.id_color;

-- Sesiones que terminaron en compra:
-- SELECT COUNT(DISTINCT s.id_sesion) AS sesiones,
--        COUNT(DISTINCT c.id_sesion) AS con_compra
-- FROM sesiones_prueba s
-- LEFT JOIN compras c ON c.id_sesion = s.id_sesion AND c.estado <> 'cancelada';
