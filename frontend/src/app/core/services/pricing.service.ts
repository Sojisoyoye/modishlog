import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
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

export interface ElasticityRead {
  id: string;
  product_id: string;
  elasticity_coefficient: number;
  r_squared: number;
  data_points_used: number;
  calculation_date: string;
  price_range_min: number;
  price_range_max: number;
  demand_curve_data: Record<string, unknown> | null;
  created_at: string;
}

export interface ElasticityConfigUpdate {
  elasticity_coefficient: number;
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

export interface DemandForecastDay {
  date: string;
  demand: number;
  demand_lower: number;
  demand_upper: number;
}

export interface DemandForecastResponse {
  product_id: string;
  horizon_days: number;
  forecasts: DemandForecastDay[];
  total_projected_demand: number;
}

export interface PricingOptimizerRec {
  id: string;
  product_id: string;
  current_price: number;
  recommended_price: number;
  expected_demand_change_pct: number;
  expected_revenue_change_pct: number;
  expected_margin_change_pct: number;
  confidence: number;
  reasoning: string;
  status: string;
  created_at: string;
}

export interface SellingPriceSuggestionRequest {
  product_id?: string;
  unit_cost_override?: number;
  currency?: string;
  fx_rate_override?: number;
  min_margin_pct?: number;
}

export interface SellingPriceSuggestionResponse {
  unit_cost: number;
  currency: string;
  fx_rate: number;
  unit_cost_ngn: number;
  min_margin_pct: number;
  min_selling_price: number;
}

@Injectable({ providedIn: 'root' })
export class PricingService {
  private readonly api = inject(ApiService);

  getPortfolioMargin(): Observable<PortfolioMarginData> {
    return this.api.get<any>('/pricing/portfolio-margin').pipe(
      map((r) => ({
        blended_margin: Number(r.blended_margin),
        target_margin: Number(r.target_margin),
        gap: Number(r.margin_gap),
        products: (r.products ?? []).map((p: any) => ({
          product_id: p.product_id,
          product_name: p.product_name,
          current_margin: Number(p.margin_pct),
          target_margin: Number(r.target_margin),
          gap: Number(p.margin_pct) - Number(r.target_margin),
          cost_price: Number(p.unit_cost),
          selling_price: Number(p.selling_price),
        })),
      })),
    );
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

  getElasticity(productId: string): Observable<ElasticityRead> {
    return this.api.get<ElasticityRead>(`/pricing/elasticity/${productId}`);
  }

  updateElasticity(
    productId: string,
    body: ElasticityConfigUpdate,
  ): Observable<ElasticityRead> {
    return this.api.post<ElasticityRead>(
      `/pricing/configure-elasticity/${productId}`,
      body,
    );
  }

  getSellingPriceSuggestion(
    body: SellingPriceSuggestionRequest,
  ): Observable<SellingPriceSuggestionResponse> {
    return this.api.post<SellingPriceSuggestionResponse>(
      '/pricing/selling-price-suggestion',
      body,
    );
  }

  getDemandForecast(
    productId: string,
    horizonDays: number = 90,
  ): Observable<DemandForecastResponse> {
    return this.api.get<DemandForecastResponse>(`/pricing/demand-forecast/${productId}`, {
      horizon_days: horizonDays.toString(),
    });
  }

  getOptimizerRecs(): Observable<PricingOptimizerRec[]> {
    return this.api.get<PricingOptimizerRec[]>('/pricing/recommendations');
  }

  generateOptimizerRecs(targetMargin: number): Observable<PricingOptimizerRec[]> {
    return this.api.post<PricingOptimizerRec[]>('/pricing/recommendations/generate', {
      target_margin: targetMargin,
    });
  }

  applyOptimizerRec(recId: string): Observable<PricingOptimizerRec> {
    return this.api.post<PricingOptimizerRec>(`/pricing/recommendations/${recId}/apply`, {});
  }

  dismissOptimizerRec(recId: string): Observable<PricingOptimizerRec> {
    return this.api.post<PricingOptimizerRec>(`/pricing/recommendations/${recId}/dismiss`, {});
  }
}
