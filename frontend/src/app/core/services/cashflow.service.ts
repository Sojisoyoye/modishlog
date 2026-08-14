import { Injectable, inject } from '@angular/core';
import { Observable, forkJoin } from 'rxjs';
import { map } from 'rxjs/operators';
import { ApiService } from './api.service';

export interface CashflowMonth {
  month: string;
  inflows: number;
  loan_payment: number;
  operating_costs: number;
  fx_obligations: number;
  net_cashflow: number;
  cumulative: number;
  dscr: number;
  dscr_is_finite: boolean;
}

export interface LiquidityInfo {
  cash_runway_days: number;
  runway_is_finite: boolean;
  runway_trend: 'up' | 'down' | 'flat' | null;
  dscr: number;
  dscr_is_finite: boolean;
  dscr_trend: 'up' | 'down' | 'flat' | null;
  risk_rating: string;
  alerts: LiquidityAlert[];
}

export interface LiquidityAlert {
  severity: string;
  message: string;
}

export interface ScenarioInput {
  fx_shock_pct: number;
  demand_drop_pct: number;
}

export interface ScenarioResult {
  label: string;
  months: CashflowMonth[];
  worst_dscr: number;
  worst_dscr_is_finite: boolean;
  cash_runway_days: number;
  cash_runway_is_finite: boolean;
  risk_rating: string;
  margin_pct: number;
}

export interface SavedScenario {
  id: string;
  name: string;
  revenue_shock_pct: number;
  fx_shock_pct: number;
  cost_shock_pct: number;
  stressed_dscr: number;
  stressed_dscr_is_finite: boolean;
  stressed_runway_months: number;
  stressed_runway_is_finite: boolean;
  created_at: string;
}

export interface GlobalExposure {
  eur_loan_balance_eur: number;
  eur_usd_rate: number;
  eur_usd_rate_available: boolean;
  eur_ngn_derived_rate: number;
  open_order_usd_obligations: number;
  ngn_usd_rate: number;
  total_global_exposure_ngn: number;
  debt_to_trade_ratio: number;
}

export interface PaymentCalendarEntry {
  date: string;
  type: string;
  amount: number;
  description: string;
  cumulative_balance: number;
}

export interface PaymentCalendarResponse {
  entries: PaymentCalendarEntry[];
  has_shortfall: boolean;
  first_shortfall_date: string | null;
  total_shortfall: number;
}

export interface TriageStatusResponse {
  id: string;
  trigger_date: string;
  shortfall_amount: number;
  horizon_days: number;
  status: string;
  resolution_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface TriageCheckResponse {
  triage_active: boolean;
  triage: TriageStatusResponse | null;
  message: string;
}

interface MonthlyBucket {
  month: string;
  projected_revenue: number;
  projected_loan_payment: number;
  projected_operating_costs: number;
  projected_fx_obligations: number;
  net_cashflow: number;
  cumulative_cashflow: number;
  dscr: number;
  dscr_is_finite: boolean;
  cash_runway_months: number;
  risk_rating: string;
}

interface ProjectionRead {
  monthly_buckets: MonthlyBucket[] | null;
}

interface RunwayResponse {
  runway_months: number;
  runway_months_is_finite: boolean;
  avg_monthly_burn: number;
  runway_trend: 'up' | 'down' | 'flat' | null;
}

interface DSCRResponse {
  dscr: number;
  dscr_is_finite: boolean;
  net_operating_income: number;
  total_debt_service: number;
  color: string;
  dscr_trend: 'up' | 'down' | 'flat' | null;
}

interface AlertResponse {
  month: string;
  type: string;
  severity: string;
  message: string;
}

interface ScenarioSummary {
  cash_runway: number;
  cash_runway_is_finite: boolean;
  avg_dscr: number;
  avg_dscr_is_finite: boolean;
  risk_rating: string;
  margin_pct: number;
}

interface ScenarioComparisonResponse {
  base: ScenarioSummary;
  stressed: ScenarioSummary;
}

@Injectable({ providedIn: 'root' })
export class CashflowService {
  private readonly api = inject(ApiService);

  getProjection(months = 6): Observable<CashflowMonth[]> {
    return this.api.get<ProjectionRead>('/cashflow/projection').pipe(
      map((proj) =>
        (proj.monthly_buckets ?? []).map((b) => ({
          month: b.month,
          inflows: Number(b.projected_revenue),
          loan_payment: Number(b.projected_loan_payment),
          operating_costs: Number(b.projected_operating_costs),
          fx_obligations: Number(b.projected_fx_obligations),
          net_cashflow: Number(b.net_cashflow),
          cumulative: Number(b.cumulative_cashflow),
          dscr: Number(b.dscr),
          dscr_is_finite: b.dscr_is_finite,
        }))
      )
    );
  }

  getLiquidity(): Observable<LiquidityInfo> {
    return forkJoin({
      runway: this.api.get<RunwayResponse>('/cashflow/cash-runway'),
      dscr: this.api.get<DSCRResponse>('/cashflow/dscr'),
      alerts: this.api.get<AlertResponse[]>('/cashflow/alerts'),
    }).pipe(
      map(({ runway, dscr, alerts }) => ({
        cash_runway_days: Math.round(Number(runway.runway_months) * 30),
        runway_is_finite: runway.runway_months_is_finite,
        runway_trend: runway.runway_trend,
        dscr: Number(dscr.dscr),
        dscr_is_finite: dscr.dscr_is_finite,
        dscr_trend: dscr.dscr_trend,
        risk_rating: this.colorToRiskRating(dscr.color),
        alerts: alerts.map((a) => ({ severity: a.severity, message: a.message })),
      }))
    );
  }

  simulateScenario(data: ScenarioInput): Observable<ScenarioResult> {
    const scenario_type = this.toScenarioType(data);
    return this.api
      .post<ScenarioComparisonResponse>('/cashflow/run-scenario', { scenario_type })
      .pipe(
        map((res) => ({
          label: scenario_type.replace(/_/g, ' '),
          months: [],
          worst_dscr: Number(res.stressed.avg_dscr),
          worst_dscr_is_finite: res.stressed.avg_dscr_is_finite,
          cash_runway_days: Math.round(Number(res.stressed.cash_runway) * 30),
          cash_runway_is_finite: res.stressed.cash_runway_is_finite,
          risk_rating: res.stressed.risk_rating,
          margin_pct: Number(res.stressed.margin_pct),
        }))
      );
  }

  getScenarios(): Observable<SavedScenario[]> {
    return this.api.get<SavedScenario[]>('/cashflow/scenarios').pipe(
      map((scenarios) =>
        scenarios.map((s) => ({
          id: s.id,
          name: s.name,
          revenue_shock_pct: Number(s.revenue_shock_pct),
          fx_shock_pct: Number(s.fx_shock_pct),
          cost_shock_pct: Number(s.cost_shock_pct),
          stressed_dscr: Number(s.stressed_dscr),
          stressed_dscr_is_finite: s.stressed_dscr_is_finite,
          stressed_runway_months: Number(s.stressed_runway_months),
          stressed_runway_is_finite: s.stressed_runway_is_finite,
          created_at: s.created_at,
        }))
      )
    );
  }

  getGlobalExposure(): Observable<GlobalExposure> {
    return this.api.get<GlobalExposure>('/cashflow/global-exposure').pipe(
      map((d) => ({
        eur_loan_balance_eur: Number(d.eur_loan_balance_eur),
        eur_usd_rate: Number(d.eur_usd_rate),
        eur_usd_rate_available: d.eur_usd_rate_available,
        eur_ngn_derived_rate: Number(d.eur_ngn_derived_rate),
        open_order_usd_obligations: Number(d.open_order_usd_obligations),
        ngn_usd_rate: Number(d.ngn_usd_rate),
        total_global_exposure_ngn: Number(d.total_global_exposure_ngn),
        debt_to_trade_ratio: Number(d.debt_to_trade_ratio),
      }))
    );
  }

  // -----------------------------------------------------------------------
  // Triage Mode
  // -----------------------------------------------------------------------

  getPaymentCalendar(horizonDays = 90): Observable<PaymentCalendarResponse> {
    return this.api.get<PaymentCalendarResponse>('/cashflow/payment-calendar', {
      horizon_days: String(horizonDays),
    });
  }

  getTriageStatus(): Observable<TriageStatusResponse | null> {
    return this.api.get<TriageStatusResponse | null>('/cashflow/triage-status');
  }

  checkTriage(horizonDays = 90): Observable<TriageCheckResponse> {
    return this.api.post<TriageCheckResponse>(
      `/cashflow/triage-check?horizon_days=${horizonDays}`, null
    );
  }

  private colorToRiskRating(color: string): string {
    if (color === 'green') return 'LOW';
    // Backend's get_current_dscr() returns 'amber' for the 1.0-1.49 band
    // (matching its own color-coding, cashflow/service.py) — this used to
    // check 'yellow', which never matched, so a medium-risk DSCR silently
    // fell through to 'UNKNOWN' (task 187).
    if (color === 'amber') return 'MEDIUM';
    if (color === 'red') return 'HIGH';
    return 'UNKNOWN';
  }

  private toScenarioType(data: ScenarioInput): string {
    if (data.fx_shock_pct >= 20 && data.demand_drop_pct >= 20) return 'COMBINED_STRESS';
    if (data.fx_shock_pct >= 20) return 'FX_SHOCK_20';
    if (data.fx_shock_pct >= 10) return 'FX_SHOCK_10';
    if (data.demand_drop_pct >= 20) return 'DEMAND_DROP_20';
    if (data.demand_drop_pct >= 10) return 'DEMAND_DROP_10';
    return 'FX_SHOCK_10';
  }
}
