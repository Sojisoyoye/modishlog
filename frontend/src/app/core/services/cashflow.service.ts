import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface CashflowMonth {
  month: string;
  inflows: number;
  outflows: number;
  net_cashflow: number;
  cumulative: number;
  dscr: number;
}

export interface LiquidityInfo {
  cash_runway_days: number;
  dscr: number;
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
  cash_runway_days: number;
}

@Injectable({ providedIn: 'root' })
export class CashflowService {
  private readonly api = inject(ApiService);

  getProjection(months = 6): Observable<CashflowMonth[]> {
    return this.api.get<CashflowMonth[]>('/cashflow/projection', { months: String(months) });
  }

  getLiquidity(): Observable<LiquidityInfo> {
    return this.api.get<LiquidityInfo>('/cashflow/liquidity');
  }

  simulateScenario(data: ScenarioInput): Observable<ScenarioResult> {
    return this.api.post<ScenarioResult>('/cashflow/simulate-scenario', data);
  }
}
