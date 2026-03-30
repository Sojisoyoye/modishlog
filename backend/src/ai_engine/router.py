from fastapi import APIRouter

router = APIRouter()

# TODO: Planned endpoints for the AI Engine domain:
#
# --- Unified Recommendation Engine ---
# GET    /ai/recommendations                       - Get all current AI recommendations (pricing, inventory, FX, cashflow)
# GET    /ai/recommendations/{category}             - Get recommendations filtered by category
#                                                     (categories: "pricing", "inventory", "fx", "cashflow", "orders")
# POST   /ai/recommendations/{rec_id}/accept        - Accept and apply a recommendation
# POST   /ai/recommendations/{rec_id}/dismiss       - Dismiss a recommendation with reason
# GET    /ai/recommendations/impact                 - Projected impact summary if all pending recommendations are applied
# GET    /ai/recommendations/history                - History of accepted/dismissed recommendations and measured outcomes
#
# --- USD Accumulation Strategy ---
# GET    /ai/usd-strategy                           - Get current USD accumulation strategy and recommendations
# GET    /ai/usd-strategy/schedule                  - Optimal USD purchase schedule (when to buy, how much)
# POST   /ai/usd-strategy/config                    - Configure strategy parameters (target USD balance, risk tolerance)
# GET    /ai/usd-strategy/config                    - View current strategy configuration
# GET    /ai/usd-strategy/performance               - Track strategy performance vs naive approach (benchmark)
# POST   /ai/usd-strategy/simulate                  - Simulate a strategy over historical data
#
# --- AI-Driven Reorder Suggestions ---
# GET    /ai/reorder                                - Get reorder suggestions for all products
# GET    /ai/reorder/{product_id}                   - Get reorder suggestion for a specific product
# POST   /ai/reorder/{product_id}/approve           - Approve and convert suggestion to a purchase order draft
# GET    /ai/reorder/config                         - View reorder model configuration (lead times, safety stock params)
# PUT    /ai/reorder/config                         - Update reorder model configuration
# GET    /ai/reorder/performance                    - Track reorder model accuracy (predicted vs actual stockouts)
