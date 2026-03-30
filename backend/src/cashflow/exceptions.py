# TODO: Domain-specific exceptions for the Cashflow domain
#
# ProjectionNotFoundError(Exception)
#   - Raised when no cashflow projection exists or the requested projection ID is not found.
#   - Attributes: projection_id (optional)
#
# InsufficientDataForProjectionError(Exception)
#   - Raised when there is not enough historical data to generate a meaningful projection.
#   - Attributes: required_months, available_months, missing_data (str description)
#
# LoanNotFoundError(Exception)
#   - Raised when a loan obligation lookup by ID yields no result.
#   - Attributes: loan_id
#
# LoanAlreadySettledError(Exception)
#   - Raised when attempting to modify or make payments on a loan that is already settled.
#   - Attributes: loan_id
#
# InvalidStressParameterError(Exception)
#   - Raised when stress scenario parameters are out of valid range.
#   - Attributes: parameter_name, value, valid_range
#
# StressScenarioNotFoundError(Exception)
#   - Raised when a stress scenario lookup by ID yields no result.
#   - Attributes: scenario_id
#
# DSCRThresholdError(Exception)
#   - Raised when DSCR threshold values are invalid (e.g. critical > warning).
#   - Attributes: warning_level, critical_level, reason
