# TODO: Async service functions for the Cashflow domain
#
# --- 6-Month Cashflow Projection ---
# async def generate_projection(db, user_id: UUID) -> CashflowProjection
#   - Fetch recent sales data (last 6 months) for revenue baseline
#   - Fetch pending/in-progress orders for planned outflows
#   - Fetch loan payment schedules for debt service outflows
#   - Apply projection assumptions (growth rate, seasonality, FX rate)
#   - Build monthly buckets for next 6 months
#   - Compute cumulative balance
#   - Store and return CashflowProjection
#
# async def get_latest_projection(db) -> CashflowProjection
#   - Return the most recent projection
#   - Raise ProjectionNotFoundError if none exist
#
# async def get_assumptions(db) -> ProjectionAssumptions
# async def update_assumptions(db, assumptions_in: AssumptionsUpdate, user_id: UUID) -> ProjectionAssumptions
#
# --- DSCR Calculation ---
# async def calculate_dscr(db, period: str) -> DSCRRecord
#   - Compute Net Operating Income = Revenue - Operating Expenses (excl. debt service)
#   - Compute Total Debt Service = sum of all loan payments in the period
#   - DSCR = NOI / Total Debt Service
#   - Flag if below threshold
#   - Store DSCRRecord
#
# async def get_current_dscr(db) -> DSCRRecord
#   - Return DSCR for the current period
#
# async def get_dscr_history(db, months: int = 12) -> list[DSCRRecord]
#   - Return monthly DSCR trend
#
# async def get_dscr_threshold(db) -> DSCRThreshold
# async def update_dscr_threshold(db, threshold: DSCRThreshold) -> DSCRThreshold
#
# --- Cash Runway ---
# async def calculate_runway(db) -> RunwayRead
#   - Fetch current cash balance (from latest projection or manual input)
#   - Compute average monthly burn rate from last 3-6 months
#   - Runway = cash_balance / avg_monthly_burn
#   - Determine trend by comparing to previous period
#
# async def get_runway_history(db, months: int = 12) -> list[RunwayRead]
#
# async def what_if_runway(db, request: WhatIfRequest) -> RunwayWhatIf
#   - Apply burn rate adjustment
#   - Apply one-time cash events
#   - Recalculate runway and compare to baseline
#
# --- Loan Obligations ---
# async def create_loan(db, loan_in: LoanCreate, user_id: UUID) -> LoanObligation
#   - Compute monthly_payment using amortization formula
#   - Generate LoanPaymentSchedule entries
#   - Compute end_date from start_date + term_months
#
# async def get_loan(db, loan_id: UUID) -> LoanObligation
# async def list_loans(db) -> list[LoanObligation]
# async def update_loan(db, loan_id: UUID, loan_in: LoanUpdate) -> LoanObligation
# async def settle_loan(db, loan_id: UUID) -> LoanObligation
#
# async def get_amortization_schedule(db, loan_id: UUID) -> list[PaymentScheduleEntry]
# async def get_combined_debt_schedule(db, months: int = 6) -> list[DebtServiceSchedule]
#   - Aggregate all loan payments by month
#
# --- Stress Scenarios ---
# async def run_stress_scenario(db, request: StressRequest, user_id: UUID) -> StressScenario
#   - Fetch base projection
#   - Apply shocks: revenue * (1 + revenue_shock_pct/100)
#   - Apply FX shock to USD-denominated outflows
#   - Apply cost increase to operating expenses
#   - Recompute monthly buckets, DSCR, runway under stressed conditions
#   - Store and return StressScenario
#
# async def get_stress_scenario(db, scenario_id: UUID) -> StressScenario
# async def list_stress_scenarios(db) -> list[StressScenario]
# async def delete_stress_scenario(db, scenario_id: UUID) -> None
