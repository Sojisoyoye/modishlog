from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the Products domain:
#
# POST   /products/              - Create a new product (name, SKU, category, unit cost, selling price)
# GET    /products/              - List all products with filtering (by category, active status, price range)
# GET    /products/{product_id}  - Retrieve a single product by ID
# PUT    /products/{product_id}  - Update product details (name, category, pricing, active status)
# DELETE /products/{product_id}  - Soft-delete a product (mark inactive, preserve historical references)
#
# --- SKU Management ---
# POST   /products/{product_id}/sku        - Generate or assign a unique SKU to a product
# GET    /products/sku/{sku}               - Look up a product by its SKU code
# PUT    /products/{product_id}/sku        - Update / reassign a product's SKU
#
# --- Product Categories ---
# POST   /categories/            - Create a new product category
# GET    /categories/            - List all product categories
# PUT    /categories/{cat_id}    - Update a category name or description
# DELETE /categories/{cat_id}    - Remove a category (only if no products are linked)
#
# --- Price / Cost Tracking ---
# GET    /products/{product_id}/price-history  - Retrieve historical price and cost changes for a product
# POST   /products/{product_id}/price          - Record a new price or cost update (effective date, reason)
# GET    /products/margin-report               - Aggregate margin report across all products
