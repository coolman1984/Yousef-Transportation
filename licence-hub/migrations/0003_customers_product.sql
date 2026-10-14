-- Customers keyed by (product, device). Existing rows use the DEFAULT product id below.
-- Prefer: node scripts/apply-migrations.mjs [--default-product <id>] [--local] <sqlite-path> (guarded).
-- For wrangler one-shot: substitute __DEFAULT_PRODUCT__ with your LICENCE_DEFAULT_PRODUCT (or first LICENCE_PRODUCTS id).
ALTER TABLE customers ADD COLUMN product TEXT NOT NULL DEFAULT '__DEFAULT_PRODUCT__';
CREATE UNIQUE INDEX IF NOT EXISTS customers_product_device ON customers(product, device);
