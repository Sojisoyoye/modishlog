"""Products domain exceptions."""


class ProductNotFoundError(Exception):
    """Raised when a product lookup yields no result."""

    def __init__(self, product_id=None, sku=None):
        self.product_id = product_id
        self.sku = sku
        identifier = sku or str(product_id)
        super().__init__(f"Product not found: {identifier}")


class DuplicateSKUError(Exception):
    """Raised when a SKU already exists."""

    def __init__(self, sku: str):
        self.sku = sku
        super().__init__(f"SKU already exists: {sku}")


class CategoryNotFoundError(Exception):
    """Raised when a category does not exist."""

    def __init__(self, category_id):
        self.category_id = category_id
        super().__init__(f"Category not found: {category_id}")


class CategoryInUseError(Exception):
    """Raised when deleting a category that has linked products."""

    def __init__(self, category_id, product_count: int):
        self.category_id = category_id
        self.product_count = product_count
        super().__init__(
            f"Category {category_id} has {product_count} linked products"
        )


class InvalidPriceError(Exception):
    """Raised when a price value is invalid."""

    def __init__(self, field_name: str, value, reason: str):
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid {field_name}={value}: {reason}")
