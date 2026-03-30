from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the Cashflow domain:
#
# --- 6-Month Cashflow Projection ---
# GET    /cashflow/projection                     - Get 6-month forward cashflow projection (monthly buckets)
# POST   /cashflow/projection/refresh             - Recalculate projection from latest sales, orders, and FX data
# GET    /cashflow/projection/assumptions          - View current projection assumptions (growth rate, seasonality)
# PUT    /cashflow/projection/assumptions          - Update projection assumptions
#
# --- DSCR Calculation ---
# GET    /cashflow/dscr                            - Get current Debt Service Coverage Ratio
# GET    /cashflow/dscr/history                    - Historical DSCR values (monthly trend)
# GET    /cashflow/dscr/threshold                  - Get DSCR alert threshold configuration
# PUT    /cashflow/dscr/threshold                  - Update DSCR alert threshold (e.g. warn below 1.25)
#
# --- Cash Runway ---
# GET    /cashflow/runway                          - Calculate months of cash runway remaining
# GET    /cashflow/runway/history                  - Historical runway trend
# POST   /cashflow/runway/what-if                  - What-if scenario: adjust burn rate and see runway impact
#
# --- Loan Obligations ---
# POST   /cashflow/loans                           - Register a loan obligation (principal, rate, term, schedule)
# GET    /cashflow/loans                           - List all active loan obligations
# GET    /cashflow/loans/{loan_id}                 - Get a specific loan with amortization schedule
# PUT    /cashflow/loans/{loan_id}                 - Update loan details
# DELETE /cashflow/loans/{loan_id}                 - Mark a loan as settled / remove
# GET    /cashflow/loans/schedule                  - Combined debt service schedule across all loans
#
# --- Stress Scenarios ---
# POST   /cashflow/stress                          - Run a stress scenario (revenue drop %, FX shock %, cost increase %)
# GET    /cashflow/stress/{scenario_id}            - Retrieve results of a saved stress scenario
# GET    /cashflow/stress                          - List all saved stress scenarios
# DELETE /cashflow/stress/{scenario_id}            - Delete a saved stress scenario
