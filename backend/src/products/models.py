# TODO: SQLAlchemy models for the Products domain
#
# Product
#   - id: UUID primary key
#   - name: String, required, indexed
#   - sku: String, unique, indexed (auto-generated or manually assigned)
#   - description: Text, optional
#   - category_id: ForeignKey -> ProductCategory.id
#   - unit_cost: Numeric(12, 2) - cost price per unit
#   - selling_price: Numeric(12, 2) - current selling price
#   - currency: String(3), default "NGN"
#   - is_active: Boolean, default True (supports soft-delete)
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#
# ProductCategory
#   - id: UUID primary key
#   - name: String, unique, required
#   - description: Text, optional
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#   - Relationship: products (one-to-many -> Product)
#
# PriceHistory
#   - id: UUID primary key
#   - product_id: ForeignKey -> Product.id
#   - old_unit_cost: Numeric(12, 2)
#   - new_unit_cost: Numeric(12, 2)
#   - old_selling_price: Numeric(12, 2)
#   - new_selling_price: Numeric(12, 2)
#   - reason: String, optional (e.g. "FX adjustment", "supplier increase")
#   - effective_date: Date
#   - changed_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
