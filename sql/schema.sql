-- Electronics shop with circular-economy data.
-- Products are built from components; components contain materials;
-- some materials are hazardous or critical raw materials.
-- SQLite. Re-running this file drops and recreates every table.

PRAGMA foreign_keys = OFF;
DROP TABLE IF EXISTS bill_item;
DROP TABLE IF EXISTS bill;
DROP TABLE IF EXISTS customer;
DROP TABLE IF EXISTS component_material;
DROP TABLE IF EXISTS product_component;
DROP TABLE IF EXISTS material;
DROP TABLE IF EXISTS component;
DROP TABLE IF EXISTS product;
DROP TABLE IF EXISTS manufacturer;
PRAGMA foreign_keys = ON;

CREATE TABLE manufacturer (
    manufacturer_id VARCHAR(10)  PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    country         CHAR(2)      NOT NULL          -- ISO 3166-1 alpha-2
);

CREATE TABLE product (
    product_id      VARCHAR(10)   PRIMARY KEY,
    name            VARCHAR(100)  NOT NULL,
    category        VARCHAR(30)   NOT NULL,        -- Smartphone, Laptop, ...
    manufacturer_id VARCHAR(10)   NOT NULL,
    unit_price      DECIMAL(10,2) NOT NULL CHECK (unit_price >= 0),
    stock_qty       INT           NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    release_year    SMALLINT      NOT NULL,
    item_condition  TEXT          NOT NULL DEFAULT 'new' CHECK (item_condition IN ('new','refurbished')),
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturer(manufacturer_id)
);

CREATE TABLE component (
    component_id    VARCHAR(10)  PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    component_type  VARCHAR(30)  NOT NULL,         -- battery, display, pcb, casing, ...
    manufacturer_id VARCHAR(10),
    recyclable      BOOLEAN      NOT NULL DEFAULT TRUE,
    FOREIGN KEY (manufacturer_id) REFERENCES manufacturer(manufacturer_id)
);

CREATE TABLE material (
    material_id     VARCHAR(10)  PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    cas_number      VARCHAR(20),                   -- Chemical Abstracts Service id
    is_hazardous    BOOLEAN      NOT NULL DEFAULT FALSE,
    is_critical_raw BOOLEAN      NOT NULL DEFAULT FALSE,  -- EU critical raw material
    regulation      VARCHAR(200)                   -- why it is hazardous / restricted
);

-- Bill of materials, level 1: which components a product contains
CREATE TABLE product_component (
    product_id   VARCHAR(10) NOT NULL,
    component_id VARCHAR(10) NOT NULL,
    quantity     INT         NOT NULL DEFAULT 1 CHECK (quantity > 0),
    PRIMARY KEY (product_id, component_id),
    FOREIGN KEY (product_id)   REFERENCES product(product_id)   ON DELETE CASCADE,
    FOREIGN KEY (component_id) REFERENCES component(component_id)
);

-- Bill of materials, level 2: which materials a component contains (grams per unit)
CREATE TABLE component_material (
    component_id VARCHAR(10)   NOT NULL,
    material_id  VARCHAR(10)   NOT NULL,
    mass_g       DECIMAL(10,3) NOT NULL CHECK (mass_g > 0),
    PRIMARY KEY (component_id, material_id),
    FOREIGN KEY (component_id) REFERENCES component(component_id) ON DELETE CASCADE,
    FOREIGN KEY (material_id)  REFERENCES material(material_id)
);

CREATE TABLE customer (
    customer_id INTEGER      PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    phone_no    VARCHAR(20),
    city        VARCHAR(50)
);

CREATE TABLE bill (
    bill_id     INTEGER PRIMARY KEY,
    customer_id INT  NOT NULL,
    bill_date   DATE NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);

CREATE TABLE bill_item (
    bill_id    INT           NOT NULL,
    product_id VARCHAR(10)   NOT NULL,
    quantity   INT           NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL CHECK (unit_price >= 0),  -- price at time of sale
    PRIMARY KEY (bill_id, product_id),
    FOREIGN KEY (bill_id)    REFERENCES bill(bill_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES product(product_id)
);
