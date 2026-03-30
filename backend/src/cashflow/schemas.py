# TODO: Pydantic schemas for the Cashflow domain
#
# --- Projection Schemas ---
# MonthlyBucket
#   - month: str (e.g. "2026-04")
#   - inflows: Decimal (sales revenue, receivables)
#   - outflows: Decimal (COGS, operating expenses, debt service, order payments)
#   - net_cashflow: Decimal (inflows - outflows)
#   - cumulative_balance: Decimal
#
# ProjectionRead
#   - id: UUID
#   - projection_date: date
#   - horizon_months: int
#   - monthly_buckets: list[MonthlyBucket]
#   - total_inflows, total_outflows, net_cashflow: Decimal
#   - assumptions: AssumptionsRead
#   - created_at: datetime
#
# AssumptionsRead
#   - revenue_growth_rate: Decimal
#   - seasonality_factors: dict[str, float]
#   - fx_rate_assumption: Decimal
#   - cost_inflation_rate: Decimal
#   - updated_at: datetime
#
# AssumptionsUpdate
#   - revenue_growth_rate: Decimal | None
#   - seasonality_factors: dict[str, float] | None
#   - fx_rate_assumption: Decimal | None
#   - cost_inflation_rate: Decimal | None
#
# --- DSCR Schemas ---
# DSCRRead
#   - period: str
#   - net_operating_income: Decimal
#   - total_debt_service: Decimal
#   - dscr_value: Decimal
#   - is_below_threshold: bool
#   - status: str ("healthy" | "warning" | "critical")
#
# DSCRThreshold
#   - warning_level: Decimal (e.g. 1.25)
#   - critical_level: Decimal (e.g. 1.00)
#
# --- Runway Schemas ---
# RunwayRead
#   - current_cash_balance: Decimal
#   - avg_monthly_burn: Decimal
#   - runway_months: int
#   - estimated_zero_date: date | None
#   - trend: str ("improving" | "stable" | "declining")
#
# RunwayWhatIf
#   - adjusted_monthly_burn: Decimal
#   - adjusted_runway_months: int
#   - adjusted_zero_date: date | None
#   - delta_months: int (change vs current)
#
# WhatIfRequest
#   - burn_rate_change_pct: Decimal (e.g. -10.0 for 10% cut)
#   - one_time_inflow: Decimal | None
#   - one_time_outflow: Decimal | None
#
# --- Loan Schemas ---
# LoanCreate
#   - lender_name: str
#   - principal_amount: Decimal
#   - interest_rate: Decimal
#   - term_months: int
#   - start_date: date
#   - payment_frequency: str ("monthly" | "quarterly")
#   - currency: str = "NGN"
#   - notes: str | None
#
# LoanUpdate
#   - All fields optional
#   - outstanding_balance: Decimal | None
#   - status: str | None
#   - notes: str | None
#
# LoanRead
#   - id: UUID
#   - lender_name, principal_amount, outstanding_balance, interest_rate
#   - term_months, start_date, end_date, payment_frequency
#   - monthly_payment, currency, status, notes
#   - next_payment_date: date | None
#   - remaining_payments: int
#   - created_at, updated_at: datetime
#
# PaymentScheduleEntry
#   - due_date: date
#   - principal_portion: Decimal
#   - interest_portion: Decimal
#   - total_payment: Decimal
#   - is_paid: bool
#
# DebtServiceSchedule
#   - month: str
#   - total_principal: Decimal
#   - total_interest: Decimal
#   - total_payment: Decimal
#   - by_loan: list[dict] (loan_id, lender_name, payment)
#
# --- Stress Scenario Schemas ---
# StressRequest
#   - name: str
#   - revenue_shock_pct: Decimal (e.g. -30.0)
#   - fx_shock_pct: Decimal (e.g. +20.0)
#   - cost_shock_pct: Decimal (e.g. +15.0)
#
# StressResultRead
#   - id: UUID
#   - name: str
#   - revenue_shock_pct, fx_shock_pct, cost_shock_pct
#   - stressed_buckets: list[MonthlyBucket]
#   - stressed_dscr: Decimal
#   - stressed_runway_months: int
#   - base_vs_stressed_delta: dict (net_cashflow_delta, dscr_delta, runway_delta)
#   - created_at: datetime
