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
        super().__init__(f"Category {category_id} has {product_count} linked products")


class CategoryHasChildrenError(Exception):
    """Raised when deleting a category that has sub-categories."""

    def __init__(self, category_id, child_count: int):
        self.category_id = category_id
        self.child_count = child_count
        super().__init__(
            f"Category {category_id} has {child_count} sub-categor{'y' if child_count == 1 else 'ies'}; delete or reassign them first"
        )


class SubcategoryDepthError(Exception):
    """Raised when creating a sub-category under an existing sub-category (max 2 levels)."""

    def __init__(self, parent_id):
        self.parent_id = parent_id
        super().__init__(
            f"Category {parent_id} is already a sub-category; cannot nest further (max 2 levels)"
        )


class DuplicateSlugError(Exception):
    """Raised when a slug already exists."""

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"Slug already exists: {slug}")


class InvalidPriceError(Exception):
    """Raised when a price value is invalid."""

    def __init__(self, field_name: str, value, reason: str):
        self.field_name = field_name
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid {field_name}={value}: {reason}")
