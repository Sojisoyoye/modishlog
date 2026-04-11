import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface PortfolioMarginData {
  blended_margin: number;
  target_margin: number;
  gap: number;
  products: ProductMargin[];
}

export interface ProductMargin {
  product_id: string;
  product_name: string;
  current_margin: number;
  target_margin: number;
  gap: number;
  cost_price: number;
  selling_price: number;
}

export interface MixTargetCreate {
  category_id: string;
  target_pct: number;
}

export interface MixTargetRead {
  id: string;
  category_id: string;
  target_pct: number;
  created_at: string;
  updated_at: string;
}

export interface MixCategoryStatus {
  category_id: string;
  category_name: string;
  actual_pct: number;
  target_pct: number;
  variance_pct: number;
}

export interface MixStatusResponse {
  categories: MixCategoryStatus[];
}

export interface SensitivityCalcRequest {
  product_id?: string;
  selling_price_override: number;
  fx_rate_override: number;
  quantity: number;
  unit_cost_usd?: number;
}

export interface SensitivityCalcResponse {
  unit_cost_usd: number;
  fx_rate: number;
  landed_cost_ngn: number;
  selling_price: number;
  margin_pct: number;
  quantity: number;
  total_revenue: number;
  total_cost: number;
  gross_profit: number;
}

export interface ScenarioCreate {
  name: string;
  product_id?: string;
  selling_price: number;
  fx_rate: number;
  quantity: number;
  results?: Record<string, unknown>;
}

export interface ScenarioRead {
  id: string;
  name: string;
  product_id?: string;
  selling_price: number;
  fx_rate: number;
  quantity: number;
  results?: Record<string, unknown>;
  created_by: string;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class PricingService {
  private readonly api = inject(ApiService);

  getPortfolioMargin(): Observable<PortfolioMarginData> {
    return this.api.get<PortfolioMarginData>('/pricing/portfolio-margin');
  }

  getMixStatus(days: number = 90): Observable<MixStatusResponse> {
    return this.api.get<MixStatusResponse>('/pricing/mix-status', {
      days: days.toString(),
    });
  }

  setMixTargets(targets: MixTargetCreate[]): Observable<MixTargetRead[]> {
    return this.api.post<MixTargetRead[]>('/pricing/mix-targets', { targets });
  }

  sensitivityCalc(
    request: SensitivityCalcRequest,
  ): Observable<SensitivityCalcResponse> {
    return this.api.post<SensitivityCalcResponse>(
      '/pricing/sensitivity-calc',
      request,
    );
  }

  saveScenario(scenario: ScenarioCreate): Observable<ScenarioRead> {
    return this.api.post<ScenarioRead>('/pricing/scenarios', scenario);
  }

  getScenarios(): Observable<ScenarioRead[]> {
    return this.api.get<ScenarioRead[]>('/pricing/scenarios');
  }
}
