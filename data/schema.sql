-- DataPilot demo database: a small e-commerce dataset (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT    NOT NULL,
    city          TEXT    NOT NULL,
    level         TEXT    NOT NULL,   -- 普通 / 银卡 / 金卡 / 黑卡
    register_date TEXT    NOT NULL    -- YYYY-MM-DD
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name TEXT    NOT NULL,
    category     TEXT    NOT NULL,    -- 数码 / 家电 / 服饰 / 美妆 / 食品
    price        REAL    NOT NULL,
    cost         REAL    NOT NULL,
    status       TEXT    NOT NULL     -- 在售 / 下架
);

CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date  TEXT    NOT NULL,     -- YYYY-MM-DD
    status      TEXT    NOT NULL,     -- 已支付 / 已退款 / 待支付 / 已取消
    channel     TEXT    NOT NULL      -- App / 小程序 / Web
);

CREATE TABLE order_items (
    item_id    INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    quantity   INTEGER NOT NULL,
    unit_price REAL    NOT NULL,
    discount   REAL    NOT NULL       -- 0.9 表示 9 折
);

CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
