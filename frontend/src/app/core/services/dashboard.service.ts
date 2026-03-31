import { Injectable, inject } from '@angular/core';
import { Observable, forkJoin, map, catchError, of } from 'rxjs';
import { ApiService } from './api.service';

export interface DashboardData {
  liquidity: LiquiditySnapshot;
  fxExposure: FxExposureSummary;
  portfolioMargin: PortfolioMargin;
  ordersPipeline: OrdersPipeline;
  inventoryAlerts: InventoryAlert[];
  recommendations: Recommendation[];
}

export interface LiquiditySnapshot {
  cash_runway_days: number;
  dscr: number;
  risk_rating: string;
}

export interface FxExposureSummary {
  total_locked_usd: number;
  total_floating_usd: number;
  total_locked_ngn: number;
  total_floating_ngn: number;
}

export interface PortfolioMargin {
  blended_margin: number;
  target_margin: number;
  gap: number;
}

export interface OrdersPipeline {
  [status: string]: number;
}

export interface InventoryAlert {
  product_id: string;
  product_name: string;
  current_stock: number;
  low_stock_threshold: number;
  estimated_stockout_date: string | null;
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

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiService);

  loadDashboard(): Observable<DashboardData> {
    return forkJoin({
      liquidity: this.api
        .get<LiquiditySnapshot>('/cashflow/liquidity')
        .pipe(catchError(() => of({ cash_runway_days: 0, dscr: 0, risk_rating: 'UNKNOWN' }))),
      fxExposure: this.api.get<FxExposureSummary>('/fx/exposure/summary').pipe(
        catchError(() =>
          of({
            total_locked_usd: 0,
            total_floating_usd: 0,
            total_locked_ngn: 0,
            total_floating_ngn: 0,
          }),
        ),
      ),
      portfolioMargin: this.api
        .get<PortfolioMargin>('/pricing/portfolio-margin')
        .pipe(catchError(() => of({ blended_margin: 0, target_margin: 35, gap: -35 }))),
      ordersPipeline: this.api
        .get<OrdersPipeline>('/orders/pipeline')
        .pipe(catchError(() => of({}))),
      inventoryAlerts: this.api
        .get<InventoryAlert[]>('/inventory/alerts')
        .pipe(catchError(() => of([]))),
      recommendations: this.api
        .get<{ items: Recommendation[] }>('/ai/recommendations', { limit: '3' })
        .pipe(
          map((r) => r.items ?? []),
          catchError(() => of([])),
        ),
    });
  }
}
