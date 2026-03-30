"""Tests for SQLAlchemy model instantiation and field types.

NOTE: mapped_column(default=X) sets the INSERT default, not the Python __init__
default. In-memory objects without a session will have None for those fields.
These tests verify field assignment, enum constraints, and Decimal precision.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from src.ai_engine.models import (
    AIRecommendation,
    ActionType,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationStatus,
    ReorderConfig,
    ReorderSuggestion,
    ReorderStatus,
    RiskTolerance,
    USDPurchaseSchedule,
    USDStrategyConfig,
)
from src.auth.models import User
from src.cashflow.models import (
    CashflowProjection,
    DSCRRecord,
    LoanObligation,
    LoanPaymentSchedule,
    LoanStatus,
    PaymentFrequency,
    StressScenario,
)
from src.fx.models import (
    AlertDirection,
    FXAlert,
    FXExposure,
    FXExposureConfig,
    FXRate,
    FXSimulationRun,
    RateSource,
)
from src.inventory.models import (
    AlertStatus,
    InventoryLevel,
    LowStockAlert,
    MovementType,
    StockMovement,
)
from src.orders.models import (
    OrderLineItem,
    OrderPayment,
    OrderStatus,
    OrderStatusHistory,
    PaymentMethod,
    PaymentStatus,
    PurchaseOrder,
)
from src.pricing.models import (
    CrossSubsidyAnalysis,
    DemandElasticity,
    MarginTarget,
    PricingRecommendation,
    RecommendationStatus as PricingRecStatus,
)
from src.products.models import PriceHistory, Product, ProductCategory
from src.sales.models import Sale, SaleAuditEntry, SaleBulkUploadJob, SaleChannel, SaleStatus


_NOW = datetime.now(timezone.utc)
_TODAY = date.today()
_UUID = uuid.uuid4()


# ---------- Auth ----------


class TestUserModel:
    def test_instantiation(self):
        user = User(
            email="test@modishlog.com",
            hashed_password="hashed",
            full_name="Test User",
            is_active=True,
        )
        assert user.email == "test@modishlog.com"
        assert user.is_active is True
        assert user.hashed_password == "hashed"

    def test_repr(self):
        user = User(email="a@b.com", hashed_password="x", full_name="A")
        assert "a@b.com" in repr(user)


# ---------- Products ----------


class TestProductModels:
    def test_product_category(self):
        cat = ProductCategory(name="Electronics", description="Gadgets")
        assert cat.name == "Electronics"

    def test_product(self):
        product = Product(
            name="Widget",
            sku="WDG-001",
            category_id=_UUID,
            unit_cost=Decimal("150.500000"),
            selling_price=Decimal("250.000000"),
            currency="NGN",
            is_active=True,
        )
        assert product.sku == "WDG-001"
        assert isinstance(product.unit_cost, Decimal)
        assert product.is_active is True

    def test_price_history(self):
        ph = PriceHistory(
            product_id=_UUID,
            old_unit_cost=Decimal("100.000000"),
            new_unit_cost=Decimal("120.000000"),
            old_selling_price=Decimal("200.000000"),
            new_selling_price=Decimal("240.000000"),
            effective_date=_TODAY,
            changed_by=_UUID,
        )
        assert ph.reason is None
        assert isinstance(ph.old_unit_cost, Decimal)


# ---------- Inventory ----------


class TestInventoryModels:
    def test_inventory_level(self):
        inv = InventoryLevel(
            product_id=_UUID,
            quantity_on_hand=50,
            quantity_reserved=5,
            low_stock_threshold=10,
        )
        assert inv.quantity_on_hand == 50
        assert inv.low_stock_threshold == 10

    def test_stock_movement(self):
        sm = StockMovement(
            product_id=_UUID,
            movement_type=MovementType.ORDER_RECEIVED,
            quantity_change=100,
            quantity_before=50,
            quantity_after=150,
            performed_by=_UUID,
        )
        assert sm.movement_type == MovementType.ORDER_RECEIVED
        assert sm.quantity_after == 150

    def test_movement_type_values(self):
        assert MovementType.SALE_DEPLETION.value == "sale_depletion"
        assert MovementType.DAMAGED.value == "damaged"

    def test_low_stock_alert(self):
        alert = LowStockAlert(
            product_id=_UUID,
            threshold=10,
            current_quantity=3,
            status=AlertStatus.ACTIVE,
            triggered_at=_NOW,
        )
        assert alert.status == AlertStatus.ACTIVE
        assert alert.current_quantity == 3


# ---------- Sales ----------


class TestSalesModels:
    def test_sale(self):
        sale = Sale(
            product_id=_UUID,
            quantity=10,
            unit_price=Decimal("250.000000"),
            total_amount=Decimal("2500.000000"),
            sale_date=_TODAY,
            channel=SaleChannel.RETAIL,
            status=SaleStatus.COMPLETED,
            currency="NGN",
            recorded_by=_UUID,
        )
        assert sale.status == SaleStatus.COMPLETED
        assert sale.currency == "NGN"
        assert isinstance(sale.total_amount, Decimal)

    def test_sale_channel_enum(self):
        assert SaleChannel.ONLINE.value == "online"
        assert SaleChannel.WHOLESALE.value == "wholesale"

    def test_bulk_upload_job(self):
        job = SaleBulkUploadJob(
            filename="sales_jan.csv",
            total_rows=100,
            processed_rows=0,
            uploaded_by=_UUID,
            created_at=_NOW,
        )
        assert job.processed_rows == 0
        assert job.filename == "sales_jan.csv"

    def test_sale_audit_entry(self):
        entry = SaleAuditEntry(
            sale_id=_UUID,
            action="created",
            performed_by=_UUID,
            created_at=_NOW,
        )
        assert entry.field_changes is None


# ---------- Orders ----------


class TestOrderModels:
    def test_purchase_order(self):
        po = PurchaseOrder(
            order_number="PO-2026-00001",
            supplier_name="AcmeCorp",
            total_amount=Decimal("5000.000000"),
            status=OrderStatus.PENDING,
            currency="USD",
            created_by=_UUID,
        )
        assert po.status == OrderStatus.PENDING
        assert po.currency == "USD"

    def test_order_status_enum(self):
        assert OrderStatus.IN_PRODUCTION.value == "In Production"
        assert OrderStatus.DELIVERED.value == "Delivered"

    def test_order_line_item(self):
        item = OrderLineItem(
            order_id=_UUID,
            product_id=_UUID,
            quantity=100,
            unit_cost=Decimal("50.000000"),
            line_total=Decimal("5000.000000"),
        )
        assert item.quantity == 100
        assert isinstance(item.line_total, Decimal)

    def test_order_payment(self):
        pmt = OrderPayment(
            order_id=_UUID,
            amount=Decimal("2500.000000"),
            currency="USD",
            payment_date=_TODAY,
            payment_method=PaymentMethod.BANK_TRANSFER,
            status=PaymentStatus.COMPLETED,
            recorded_by=_UUID,
            created_at=_NOW,
        )
        assert pmt.status == PaymentStatus.COMPLETED
        assert pmt.payment_method == PaymentMethod.BANK_TRANSFER

    def test_order_status_history(self):
        hist = OrderStatusHistory(
            order_id=_UUID,
            to_status="Shipping",
            transitioned_by=_UUID,
            created_at=_NOW,
        )
        assert hist.from_status is None


# ---------- FX ----------


class TestFXModels:
    def test_fx_rate(self):
        rate = FXRate(
            pair="USDNGN",
            rate=Decimal("1550.500000"),
            source=RateSource.PARALLEL_MARKET,
            timestamp=_NOW,
            created_at=_NOW,
        )
        assert rate.pair == "USDNGN"
        assert isinstance(rate.rate, Decimal)

    def test_rate_source_enum(self):
        assert RateSource.CBN_OFFICIAL.value == "cbn_official"

    def test_fx_exposure(self):
        exp = FXExposure(
            pair="USDNGN",
            total_exposure_amount=Decimal("100000.000000"),
            locked_amount=Decimal("30000.000000"),
            locked_rate=Decimal("1500.000000"),
            floating_amount=Decimal("70000.000000"),
        )
        assert exp.reference_id is None

    def test_fx_exposure_config(self):
        cfg = FXExposureConfig(
            locked_pct=Decimal("30.00"),
            floating_pct=Decimal("70.00"),
            updated_by=_UUID,
            updated_at=_NOW,
        )
        assert cfg.locked_pct == Decimal("30.00")

    def test_fx_alert(self):
        alert = FXAlert(
            pair="USDNGN",
            direction=AlertDirection.ABOVE,
            threshold_rate=Decimal("1600.000000"),
            is_enabled=True,
            is_triggered=False,
            created_by=_UUID,
            created_at=_NOW,
        )
        assert alert.is_enabled is True
        assert alert.is_triggered is False

    def test_fx_simulation_run(self):
        sim = FXSimulationRun(
            pair="USDNGN",
            horizon_days=30,
            num_simulations=10000,
            confidence_level=Decimal("95.00"),
            current_rate=Decimal("1550.000000"),
            mean_projected_rate=Decimal("1560.000000"),
            p5_rate=Decimal("1500.000000"),
            p50_rate=Decimal("1555.000000"),
            p95_rate=Decimal("1620.000000"),
            var_amount=Decimal("500000.000000"),
            run_by=_UUID,
            created_at=_NOW,
        )
        assert sim.num_simulations == 10000


# ---------- Cashflow ----------


class TestCashflowModels:
    def test_cashflow_projection(self):
        proj = CashflowProjection(
            projection_date=_TODAY,
            horizon_months=6,
            total_inflows=Decimal("1000000.000000"),
            total_outflows=Decimal("800000.000000"),
            net_cashflow=Decimal("200000.000000"),
            generated_by=_UUID,
            created_at=_NOW,
        )
        assert proj.horizon_months == 6
        assert isinstance(proj.net_cashflow, Decimal)

    def test_loan_obligation(self):
        loan = LoanObligation(
            lender_name="First Bank",
            principal_amount=Decimal("5000000.000000"),
            outstanding_balance=Decimal("4500000.000000"),
            interest_rate=Decimal("18.50"),
            term_months=24,
            start_date=_TODAY,
            end_date=_TODAY,
            payment_frequency=PaymentFrequency.MONTHLY,
            monthly_payment=Decimal("250000.000000"),
            status=LoanStatus.ACTIVE,
            currency="NGN",
        )
        assert loan.status == LoanStatus.ACTIVE
        assert loan.currency == "NGN"

    def test_dscr_record(self):
        dscr = DSCRRecord(
            period="2026-03",
            net_operating_income=Decimal("500000.000000"),
            total_debt_service=Decimal("350000.000000"),
            dscr_value=Decimal("1.429"),
            is_below_threshold=False,
            created_at=_NOW,
        )
        assert dscr.dscr_value == Decimal("1.429")

    def test_loan_payment_schedule(self):
        sched = LoanPaymentSchedule(
            loan_id=_UUID,
            due_date=_TODAY,
            principal_portion=Decimal("200000.000000"),
            interest_portion=Decimal("50000.000000"),
            total_payment=Decimal("250000.000000"),
            is_paid=False,
        )
        assert sched.is_paid is False

    def test_stress_scenario(self):
        stress = StressScenario(
            name="30% Revenue Drop",
            revenue_shock_pct=Decimal("-30.00"),
            fx_shock_pct=Decimal("20.00"),
            cost_shock_pct=Decimal("15.00"),
            base_projection_id=_UUID,
            stressed_dscr=Decimal("0.850"),
            stressed_runway_months=3,
            created_by=_UUID,
            created_at=_NOW,
        )
        assert stress.stressed_runway_months == 3

    def test_payment_frequency_enum(self):
        assert PaymentFrequency.MONTHLY.value == "monthly"
        assert PaymentFrequency.QUARTERLY.value == "quarterly"


# ---------- Pricing ----------


class TestPricingModels:
    def test_demand_elasticity(self):
        de = DemandElasticity(
            product_id=_UUID,
            elasticity_coefficient=Decimal("-1.5000"),
            r_squared=Decimal("0.8500"),
            data_points_used=120,
            calculation_date=_TODAY,
            price_range_min=Decimal("100.000000"),
            price_range_max=Decimal("500.000000"),
            created_at=_NOW,
        )
        assert de.data_points_used == 120

    def test_margin_target(self):
        mt = MarginTarget(
            target_margin_pct=Decimal("35.00"),
            min_margin_pct=Decimal("20.00"),
            priority=1,
            set_by=_UUID,
        )
        assert mt.priority == 1
        assert mt.target_margin_pct == Decimal("35.00")

    def test_pricing_recommendation(self):
        rec = PricingRecommendation(
            product_id=_UUID,
            current_price=Decimal("250.000000"),
            recommended_price=Decimal("275.000000"),
            expected_demand_change_pct=Decimal("-5.00"),
            expected_revenue_change_pct=Decimal("4.50"),
            expected_margin_change_pct=Decimal("8.00"),
            confidence=Decimal("85.00"),
            reasoning="FX cost increase warrants price adjustment",
            status=PricingRecStatus.PENDING,
            created_at=_NOW,
        )
        assert rec.status == PricingRecStatus.PENDING

    def test_cross_subsidy_analysis(self):
        csa = CrossSubsidyAnalysis(
            analysis_date=_TODAY,
            portfolio_total_margin=Decimal("500000.000000"),
            created_at=_NOW,
        )
        assert csa.subsidy_matrix is None

    def test_recommendation_status_enum(self):
        assert PricingRecStatus.APPLIED.value == "applied"
        assert PricingRecStatus.EXPIRED.value == "expired"


# ---------- AI Engine ----------


class TestAIEngineModels:
    def test_ai_recommendation(self):
        rec = AIRecommendation(
            category=RecommendationCategory.PRICING,
            title="Increase Widget price by 10%",
            description="FX depreciation has eroded margins",
            priority=RecommendationPriority.HIGH,
            confidence=Decimal("92.00"),
            action_type=ActionType.PRICE_CHANGE,
            status=RecommendationStatus.PENDING,
            created_at=_NOW,
            expires_at=_NOW,
        )
        assert rec.status == RecommendationStatus.PENDING

    def test_recommendation_category_enum(self):
        assert RecommendationCategory.FX.value == "fx"
        assert RecommendationCategory.INVENTORY.value == "inventory"

    def test_action_type_enum(self):
        assert ActionType.PRICE_CHANGE.value == "price_change"
        assert ActionType.USD_PURCHASE.value == "usd_purchase"

    def test_usd_strategy_config(self):
        cfg = USDStrategyConfig(
            target_usd_balance=Decimal("50000.000000"),
            current_usd_balance=Decimal("20000.000000"),
            risk_tolerance=RiskTolerance.MODERATE,
            max_single_purchase_pct=Decimal("25.00"),
            preferred_rate_percentile=Decimal("30.00"),
            lookback_days=90,
            updated_by=_UUID,
            updated_at=_NOW,
        )
        assert cfg.risk_tolerance == RiskTolerance.MODERATE

    def test_usd_purchase_schedule(self):
        sched = USDPurchaseSchedule(
            strategy_config_id=_UUID,
            recommended_date=_TODAY,
            recommended_amount_usd=Decimal("5000.000000"),
            recommended_rate_ceiling=Decimal("1550.000000"),
            reasoning="Rate below 30th percentile",
            created_at=_NOW,
        )
        assert sched.executed_rate is None

    def test_reorder_suggestion(self):
        rs = ReorderSuggestion(
            product_id=_UUID,
            current_stock=15,
            reorder_point=20,
            suggested_order_quantity=100,
            economic_order_quantity=80,
            safety_stock=10,
            lead_time_days=30,
            avg_daily_demand=Decimal("5.50"),
            demand_variability=Decimal("0.2500"),
            confidence=Decimal("88.00"),
            reasoning="Stock below reorder point with 30-day lead time",
            status=ReorderStatus.PENDING,
            created_at=_NOW,
        )
        assert rs.status == ReorderStatus.PENDING
        assert rs.current_stock == 15

    def test_reorder_config(self):
        cfg = ReorderConfig(
            default_lead_time_days=30,
            safety_stock_multiplier=Decimal("1.50"),
            service_level_target=Decimal("95.00"),
            demand_lookback_days=90,
            holding_cost_pct=Decimal("12.00"),
            updated_by=_UUID,
            updated_at=_NOW,
        )
        assert cfg.default_lead_time_days == 30
        assert cfg.service_level_target == Decimal("95.00")
