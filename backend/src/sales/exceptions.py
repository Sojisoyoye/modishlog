# TODO: Domain-specific exceptions for the Sales domain
#
# SaleNotFoundError(Exception)
#   - Raised when a sale lookup by ID yields no result.
#   - Attributes: sale_id
#
# SaleAlreadyVoidedError(Exception)
#   - Raised when attempting to update or void a sale that has already been voided.
#   - Attributes: sale_id
#
# BulkUploadJobNotFoundError(Exception)
#   - Raised when referencing a bulk upload job that does not exist.
#   - Attributes: job_id
#
# InvalidCSVFormatError(Exception)
#   - Raised when the uploaded CSV has missing/invalid headers or cannot be parsed.
#   - Attributes: filename, details (str describing the format issue)
#
# SaleValidationError(Exception)
#   - Raised when sale data fails validation (e.g. invalid product, negative quantity).
#   - Attributes: field, value, reason
