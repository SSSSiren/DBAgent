SET NAMES utf8mb4;
SET sql_mode = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

DROP TABLE IF EXISTS user_events;
DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS coupons;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id BIGINT PRIMARY KEY,
  user_name VARCHAR(64) NOT NULL,
  city VARCHAR(64) NOT NULL,
  channel VARCHAR(32) NOT NULL,
  registered_at DATETIME NOT NULL,
  status VARCHAR(20) NOT NULL
);

CREATE TABLE categories (
  id BIGINT PRIMARY KEY,
  category_name VARCHAR(64) NOT NULL
);

CREATE TABLE products (
  id BIGINT PRIMARY KEY,
  category_id BIGINT NOT NULL,
  product_name VARCHAR(128) NOT NULL,
  list_price DECIMAL(10,2) NOT NULL,
  stock_quantity INT NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_products_category (category_id)
);

CREATE TABLE coupons (
  id BIGINT PRIMARY KEY,
  coupon_code VARCHAR(32) NOT NULL,
  discount_amount DECIMAL(10,2) NOT NULL,
  channel VARCHAR(32) NOT NULL
);

CREATE TABLE orders (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  coupon_id BIGINT NULL,
  order_status VARCHAR(20) NOT NULL,
  total_amount DECIMAL(10,2) NOT NULL,
  created_at DATETIME NOT NULL,
  paid_at DATETIME NULL,
  INDEX idx_orders_user (user_id),
  INDEX idx_orders_created_at (created_at),
  INDEX idx_orders_status_paid_at (order_status, paid_at)
);

CREATE TABLE order_items (
  id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  product_id BIGINT NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  INDEX idx_order_items_order (order_id),
  INDEX idx_order_items_product (product_id)
);

CREATE TABLE payments (
  id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  payment_method VARCHAR(32) NOT NULL,
  payment_status VARCHAR(20) NOT NULL,
  paid_amount DECIMAL(10,2) NOT NULL,
  paid_at DATETIME NOT NULL,
  INDEX idx_payments_order (order_id)
);

CREATE TABLE refunds (
  id BIGINT PRIMARY KEY,
  order_id BIGINT NOT NULL,
  refund_amount DECIMAL(10,2) NOT NULL,
  refund_status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_refunds_order (order_id)
);

CREATE TABLE user_events (
  id BIGINT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  event_name VARCHAR(64) NOT NULL,
  product_id BIGINT NULL,
  event_time DATETIME NOT NULL,
  INDEX idx_user_events_user_time (user_id, event_time),
  INDEX idx_user_events_name_time (event_name, event_time)
);

