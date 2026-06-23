INSERT INTO users (id, user_name, city, channel, registered_at, status) VALUES
(1, 'alice', 'Shanghai', 'organic', '2024-05-01 09:10:00', 'active'),
(2, 'bob', 'Beijing', 'ad', '2024-05-03 10:20:00', 'active'),
(3, 'carol', 'Shenzhen', 'organic', '2024-05-05 11:30:00', 'active'),
(4, 'dave', 'Shanghai', 'referral', '2024-05-10 08:00:00', 'inactive'),
(5, 'erin', 'Hangzhou', 'ad', '2024-05-12 13:15:00', 'active'),
(6, 'frank', 'Beijing', 'referral', '2024-06-01 14:00:00', 'active');

INSERT INTO categories (id, category_name) VALUES
(1, 'Phone'),
(2, 'Laptop'),
(3, 'Accessory');

INSERT INTO products (id, category_id, product_name, list_price, stock_quantity, status, created_at) VALUES
(1, 1, 'Phone Mini', 3999.00, 30, 'active', '2024-04-01 00:00:00'),
(2, 1, 'Phone Pro', 6999.00, 12, 'active', '2024-04-02 00:00:00'),
(3, 2, 'Laptop Air', 8999.00, 8, 'active', '2024-04-03 00:00:00'),
(4, 2, 'Laptop Max', 12999.00, 4, 'active', '2024-04-04 00:00:00'),
(5, 3, 'USB Cable', 49.00, 200, 'active', '2024-04-05 00:00:00'),
(6, 3, 'Wireless Charger', 199.00, 60, 'inactive', '2024-04-06 00:00:00');

INSERT INTO coupons (id, coupon_code, discount_amount, channel) VALUES
(1, 'AD50', 50.00, 'ad'),
(2, 'ORG30', 30.00, 'organic'),
(3, 'REF20', 20.00, 'referral');

INSERT INTO orders (id, user_id, coupon_id, order_status, total_amount, created_at, paid_at) VALUES
(101, 1, 2, 'paid', 4048.00, '2024-06-01 09:00:00', '2024-06-01 09:05:00'),
(102, 1, NULL, 'completed', 6999.00, '2024-06-02 10:00:00', '2024-06-02 10:06:00'),
(103, 2, 1, 'paid', 8999.00, '2024-06-03 11:00:00', '2024-06-03 11:03:00'),
(104, 2, NULL, 'cancelled', 49.00, '2024-06-03 12:00:00', NULL),
(105, 3, 2, 'completed', 13048.00, '2024-06-04 13:00:00', '2024-06-04 13:05:00'),
(106, 4, 3, 'paid', 199.00, '2024-06-05 14:00:00', '2024-06-05 14:04:00'),
(107, 5, 1, 'paid', 9048.00, '2024-06-06 15:00:00', '2024-06-06 15:05:00'),
(108, 5, NULL, 'completed', 49.00, '2024-06-07 16:00:00', '2024-06-07 16:01:00'),
(109, 6, 3, 'paid', 3999.00, '2024-06-08 17:00:00', '2024-06-08 17:02:00'),
(110, 6, NULL, 'pending', 6999.00, '2024-06-09 18:00:00', NULL);

INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES
(1001, 101, 1, 1, 3999.00),
(1002, 101, 5, 1, 49.00),
(1003, 102, 2, 1, 6999.00),
(1004, 103, 3, 1, 8999.00),
(1005, 104, 5, 1, 49.00),
(1006, 105, 4, 1, 12999.00),
(1007, 105, 5, 1, 49.00),
(1008, 106, 6, 1, 199.00),
(1009, 107, 3, 1, 8999.00),
(1010, 107, 5, 1, 49.00),
(1011, 108, 5, 1, 49.00),
(1012, 109, 1, 1, 3999.00),
(1013, 110, 2, 1, 6999.00);

INSERT INTO payments (id, order_id, payment_method, payment_status, paid_amount, paid_at) VALUES
(201, 101, 'wechat', 'success', 4048.00, '2024-06-01 09:05:00'),
(202, 102, 'alipay', 'success', 6999.00, '2024-06-02 10:06:00'),
(203, 103, 'card', 'success', 8999.00, '2024-06-03 11:03:00'),
(204, 105, 'wechat', 'success', 13048.00, '2024-06-04 13:05:00'),
(205, 106, 'alipay', 'success', 199.00, '2024-06-05 14:04:00'),
(206, 107, 'card', 'success', 9048.00, '2024-06-06 15:05:00'),
(207, 108, 'wechat', 'success', 49.00, '2024-06-07 16:01:00'),
(208, 109, 'wechat', 'success', 3999.00, '2024-06-08 17:02:00');

INSERT INTO refunds (id, order_id, refund_amount, refund_status, created_at) VALUES
(301, 106, 199.00, 'approved', '2024-06-06 09:00:00'),
(302, 107, 100.00, 'rejected', '2024-06-07 10:00:00'),
(303, 108, 49.00, 'approved', '2024-06-08 11:00:00');

INSERT INTO user_events (id, user_id, event_name, product_id, event_time) VALUES
(401, 1, 'view_product', 1, '2024-06-01 08:50:00'),
(402, 1, 'add_to_cart', 1, '2024-06-01 08:55:00'),
(403, 2, 'view_product', 3, '2024-06-03 10:40:00'),
(404, 3, 'view_product', 4, '2024-06-04 12:30:00'),
(405, 3, 'add_to_cart', 4, '2024-06-04 12:40:00'),
(406, 5, 'view_product', 3, '2024-06-06 14:30:00'),
(407, 5, 'add_to_cart', 3, '2024-06-06 14:40:00'),
(408, 6, 'view_product', 1, '2024-06-08 16:40:00');

