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

@Injectable({ providedIn: 'root' })
export class PricingService {
  private readonly api = inject(ApiService);

  getPortfolioMargin(): Observable<PortfolioMarginData> {
    return this.api.get<PortfolioMarginData>('/pricing/portfolio-margin');
  }
}
