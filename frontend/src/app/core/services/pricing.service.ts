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
}
