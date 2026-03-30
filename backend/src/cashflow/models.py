# TODO: SQLAlchemy models for the Cashflow domain
#
# CashflowProjection
#   - id: UUID primary key
#   - projection_date: Date (when the projection was generated)
#   - horizon_months: Integer, default 6
#   - monthly_buckets: JSON (list of {month, inflows, outflows, net_cashflow, cumulative_balance})
#   - total_inflows: Numeric(14, 2)
#   - total_outflows: Numeric(14, 2)
#   - net_cashflow: Numeric(14, 2)
#   - assumptions: JSON (growth_rate, seasonality_factors, fx_rate_assumption)
#   - generated_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
#
# ProjectionAssumptions
#   - id: UUID primary key
#   - revenue_growth_rate: Numeric(5, 2) - monthly growth assumption (%)
#   - seasonality_factors: JSON (dict of month -> multiplier, e.g. {"12": 1.3, "1": 0.8})
#   - fx_rate_assumption: Numeric(14, 4) - assumed USD/NGN rate
#   - cost_inflation_rate: Numeric(5, 2) - monthly cost increase assumption (%)
#   - updated_by: ForeignKey -> User.id
#   - updated_at: DateTime with timezone
#
# DSCRRecord
#   - id: UUID primary key
#   - period: String (e.g. "2026-03")
#   - net_operating_income: Numeric(14, 2)
#   - total_debt_service: Numeric(14, 2)
#   - dscr_value: Numeric(6, 3) - ratio (e.g. 1.450)
#   - is_below_threshold: Boolean
#   - created_at: DateTime with timezone
#
# LoanObligation
#   - id: UUID primary key
#   - lender_name: String, required
#   - principal_amount: Numeric(14, 2)
#   - outstanding_balance: Numeric(14, 2)
#   - interest_rate: Numeric(5, 2) - annual rate (%)
#   - term_months: Integer
#   - start_date: Date
#   - end_date: Date
#   - payment_frequency: String ("monthly", "quarterly")
#   - monthly_payment: Numeric(14, 2) - computed or fixed
#   - currency: String(3), default "NGN"
#   - status: String ("active", "settled", "defaulted")
#   - notes: Text, optional
#   - created_at: DateTime with timezone
#   - updated_at: DateTime with timezone
#
# LoanPaymentSchedule
#   - id: UUID primary key
#   - loan_id: ForeignKey -> LoanObligation.id
#   - due_date: Date
#   - principal_portion: Numeric(14, 2)
#   - interest_portion: Numeric(14, 2)
#   - total_payment: Numeric(14, 2)
#   - is_paid: Boolean, default False
#   - paid_date: Date, nullable
#
# StressScenario
#   - id: UUID primary key
#   - name: String (e.g. "30% Revenue Drop + FX Shock")
#   - revenue_shock_pct: Numeric(5, 2) - e.g. -30.00 (%)
#   - fx_shock_pct: Numeric(5, 2) - e.g. +20.00 (%)
#   - cost_shock_pct: Numeric(5, 2) - e.g. +15.00 (%)
#   - base_projection_id: ForeignKey -> CashflowProjection.id
#   - stressed_buckets: JSON (same structure as monthly_buckets with shocked values)
#   - stressed_dscr: Numeric(6, 3)
#   - stressed_runway_months: Integer
#   - created_by: ForeignKey -> User.id
#   - created_at: DateTime with timezone
