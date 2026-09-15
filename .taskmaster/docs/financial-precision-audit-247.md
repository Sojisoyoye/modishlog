# Financial calculation precision audit (task #247)

Dedicated pass, 2026-09-15, per the task's three-point implementation plan.

## 1. Every money column uses Decimal/Numeric, not Float

Exhaustive grep (not a sample) across every domain's `models.py`:

```
grep -rn "Float\b" backend/src/*/models.py   →  zero matches
```

Also checked for raw Python `float` type hints on schemas that could
represent money: the only hits (`avg_daily_depletion`, `demand`,
`demand_lower`, `demand_upper`, `total_projected_demand`) are unit-quantity
forecasts (Prophet/statistical outputs), not currency — confirmed correct,
matching the original spot-check's conclusion, now verified exhaustively
rather than by sample.

## 2. Found and fixed a real precision mismatch: `Sale.payment_amount`

Every money column on `Sale` uses `NUMERIC(18, 6)` — **except**
`payment_amount`, which was `NUMERIC(18, 2)`. `reports/service.py`'s
`sales_due` calculation does `Sale.total_amount - Sale.payment_amount`
directly in SQL.

**Empirically reproduced against real Postgres** before fixing:

```sql
-- total_amount NUMERIC(18,6), payment_amount NUMERIC(18,2)
INSERT INTO precision_test VALUES (1234.567891, 1234.567891);
SELECT total_amount, payment_amount, total_amount - payment_amount AS residual;
--  1234.567891 |        1234.57 | -0.002109
```

A sale marked fully paid, with a `total_amount` carrying genuine sub-cent
precision (routine for FX-converted pricing — this app explicitly supports
NGN/USD via FX, and FX-derived unit costs are quantized to 6dp throughout
`pricing/service.py`), would get its `payment_amount` **silently rounded to
2dp on insert** by Postgres's column-scale enforcement. The result: a
permanent phantom -0.002109 "amount due" for a sale that was actually paid
in full, showing up in the `sales_due` report figure indefinitely. This is
exactly the "no silent rounding drift... reports reconcile exactly" failure
mode this task was scoped to find.

**Fix**: widened `payment_amount` to `NUMERIC(18, 6)`, matching every other
money column on `Sale` (migration `5baae79a6c06`). Re-verified against real
Postgres after the fix — residual is now exactly `0.000000`.

A regression test (`TestSaleMoneyColumnPrecision`, `backend/tests/
test_sales.py`) asserts `payment_amount`'s column scale/precision matches
`total_amount`'s programmatically, so this can't silently drift back.

No other money-field precision mismatches exist anywhere else in the
codebase — checked every non-`NUMERIC(18,6)` scale found (`5,2`, `8,4`,
`6,3`, `5,4`, `8,2`, `6,1`, `4,2`) and confirmed each belongs to a genuine
non-money field (percentages, elasticity coefficients, multipliers, a
runway-in-months duration) that's never subtracted/compared against an
`18,6` money column.

## 3. FX conversion rounding boundaries

Checked every FX/landed-cost calculation in `pricing/service.py` and
`inventory/service.py` (FIFO COGS). All consistently `.quantize(Decimal
("0.000001"), rounding=ROUND_HALF_UP)` (or the shorthand `Decimal("0.01")`
for percentage-style outputs) **before** the value is stored in its
`NUMERIC(18,6)` column — so no additional silent rounding happens at
insert time beyond what's already been deliberately, explicitly applied in
Python. No `float()` conversions exist anywhere in the reports or
dashboard aggregation layers (`reports/service.py`, `dashboard/
service.py`) — money stays in `Decimal`/`NUMERIC` end-to-end from
calculation through storage through report aggregation.

## Live end-to-end reconciliation check

Ran a one-off scenario (not committed — a throwaway script, cleaned up
after running, same pattern as this session's other verification passes)
directly against the real dev Postgres: one business, one product priced
at a genuinely 6dp-significant unit price (`1975.309426`, simulating
FX-converted pricing), three sales (quantities 3, 5, 2), one sell return.
Compared the real `get_profit_loss_report()` and `get_dashboard_summary()`
service functions' output against manual SQL aggregation of the raw rows:

| | Manual SQL sum | Report/dashboard value |
|---|---|---|
| Revenue (3 sales) | 19753.094260 | 19753.094260 (both P&L and dashboard) |
| Sell returns | 1975.309426 | 1975.309426 (dashboard) |
| `payment_amount` residual (fully-paid sale) | — | `0.000000` (post-fix) |

All reconciled exactly — zero drift at 6dp, including through a genuinely
fractional price that would have triggered the `payment_amount` bug if it
weren't fixed.

**Note on P&L methodology** (observation, not a bug): this codebase's P&L
report computes `gross_profit` from `total_sales - total_purchase_excl_tax`
(a purchase-order-based COGS proxy), not from `Sale.fifo_cogs`/
`fifo_gross_profit` per sale — those FIFO fields exist on the `Sale` model
and are correctly computed at sale time, but aren't consumed by the P&L
report itself. This looks like a deliberate cash/accrual-purchase costing
choice (the schema field is literally named `total_purchase_excl_tax`) and
verifying which costing methodology is intended is a product decision
beyond this precision-and-rounding audit's scope — flagged here so it's a
known, deliberate observation rather than something discovered later and
mistaken for a new bug.

## Summary

- Zero Float columns for money, confirmed exhaustively.
- One real precision bug found (`Sale.payment_amount`), reproduced against
  real Postgres, fixed, and covered by a regression test.
- FX/FIFO rounding boundaries checked and confirmed consistent.
- Live end-to-end reconciliation against real report/dashboard service
  functions confirmed zero drift, including through the exact class of
  fractional-price scenario that would have surfaced the bug above.
