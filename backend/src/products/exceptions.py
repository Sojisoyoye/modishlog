# TODO: Domain-specific exceptions for the Products domain
#
# ProductNotFoundError(Exception)
#   - Raised when a product lookup by ID or SKU yields no result.
#   - Attributes: product_id or sku (whichever was used for the lookup)
#
# DuplicateSKUError(Exception)
#   - Raised when attempting to create or update a product with a SKU that already exists.
#   - Attributes: sku (the conflicting SKU string)
#
# CategoryNotFoundError(Exception)
#   - Raised when referencing a product category that does not exist.
#   - Attributes: category_id
#
# CategoryInUseError(Exception)
#   - Raised when attempting to delete a category that still has products linked to it.
#   - Attributes: category_id, product_count (number of linked products)
#
# InvalidPriceError(Exception)
#   - Raised when a price or cost value is invalid (e.g. negative, selling_price < unit_cost).
#   - Attributes: field_name, value, reason
