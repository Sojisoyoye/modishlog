import { Injectable, inject } from '@angular/core';
import { Observable, forkJoin, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { ApiService } from './api.service';

export interface LiquiditySnapshot {
  runway_months: number;
  dscr: number;
  risk_rating: string;
}

export interface OrdersSummary {
  total_orders: number;
  total_value: string;
  by_status: Record<string, number>;
  active_orders: number;
}

export interface Recommendation {
  id: string;
  category: string;
  title: string;
  description: string;
  priority: string;
  confidence: number;
  expected_impact: Record<string, unknown> | null;
  action_type: string;
  status: string;
  created_at: string;
  expires_at: string;
}

export interface ProfitMargin {
  blended_margin: number;
  target_margin: number;
  margin_gap: number;
}

export interface DashboardData {
  liquidity: LiquiditySnapshot;
  ordersSummary: OrdersSummary;
  profitMargin: ProfitMargin;
  lowStockCount: number;
  recommendations: Recommendation[];
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiService);

  loadDashboard(): Observable<DashboardData> {
    return forkJoin({
      liquidity: forkJoin({
        runway: this.api.get<{ runway_months: string }>('/cashflow/cash-runway'),
        dscr: this.api.get<{ dscr: string; color: string }>('/cashflow/dscr'),
      }).pipe(
        map(({ runway, dscr }) => ({
          runway_months: Number(runway.runway_months),
          dscr: Number(dscr.dscr),
          risk_rating: dscr.color === 'green' ? 'LOW' : dscr.color === 'yellow' ? 'MEDIUM' : 'HIGH',
        })),
        catchError(() => of({ runway_months: 0, dscr: 0, risk_rating: 'UNKNOWN' })),
      ),
      ordersSummary: this.api
        .get<{ total_orders: number; total_value: string; by_status: Record<string, number> }>(
          '/orders/summary',
        )
        .pipe(
          map((s) => ({
            ...s,
            active_orders: Object.entries(s.by_status)
              .filter(([k]) => !['DELIVERED', 'CANCELLED'].includes(k))
              .reduce((sum, [, v]) => sum + v, 0),
          })),
          catchError(() => of({ total_orders: 0, total_value: '0', by_status: {}, active_orders: 0 })),
        ),
      profitMargin: this.api
        .get<{ blended_margin: string; target_margin: string; margin_gap: string }>(
          '/pricing/portfolio-margin',
        )
        .pipe(
          map((m) => ({
            blended_margin: Number(m.blended_margin),
            target_margin: Number(m.target_margin),
            margin_gap: Number(m.margin_gap),
          })),
          catchError(() => of({ blended_margin: 0, target_margin: 35, margin_gap: -35 })),
        ),
      lowStockCount: this.api.get<unknown[]>('/inventory/low-stock').pipe(
        map((items) => items.length),
        catchError(() => of(0)),
      ),
      recommendations: this.api
        .get<{ items: Recommendation[] }>('/ai/recommendations', { limit: '3' })
        .pipe(
          map((r) => r.items ?? []),
          catchError(() => of([])),
        ),
    });
  }
}
