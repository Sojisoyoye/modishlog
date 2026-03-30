from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the FX domain:
#
# --- FX Rate Ingestion ---
# POST   /fx/rates/ingest                     - Manually ingest or update an FX rate (pair, rate, source, timestamp)
# GET    /fx/rates/current                     - Get current rates for all tracked pairs (e.g. USD/NGN, EUR/NGN)
# GET    /fx/rates/{pair}                      - Get current rate for a specific pair (e.g. "USDNGN")
# GET    /fx/rates/{pair}/history              - Historical rate data for a pair (with date range filter)
# POST   /fx/rates/sync                        - Trigger sync from external rate providers (CBN, parallel market)
#
# --- Exposure Engine ---
# GET    /fx/exposure                          - Current FX exposure summary (locked vs floating breakdown)
# GET    /fx/exposure/detail                   - Detailed exposure by order / liability
# POST   /fx/exposure/lock                     - Lock a portion of exposure at a specific rate (create a forward/hedge)
# PUT    /fx/exposure/config                   - Update exposure split config (default: 30% locked / 70% floating)
# GET    /fx/exposure/config                   - Get current exposure split configuration
#
# --- FX Alerts ---
# POST   /fx/alerts                            - Create a rate alert (pair, direction, threshold)
# GET    /fx/alerts                            - List all active FX alerts
# PUT    /fx/alerts/{alert_id}                 - Update an alert (threshold, enabled/disabled)
# DELETE /fx/alerts/{alert_id}                 - Remove an alert
# GET    /fx/alerts/triggered                  - List recently triggered alerts
#
# --- Monte Carlo Simulation ---
# POST   /fx/simulate                          - Run Monte Carlo simulation for FX impact on cashflow
#                                                (inputs: horizon_days, num_simulations, confidence_level)
# GET    /fx/simulate/{sim_id}                 - Retrieve results of a previous simulation run
# GET    /fx/simulate/{sim_id}/distribution     - Get probability distribution data for charting
