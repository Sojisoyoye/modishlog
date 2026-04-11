import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface DailyEntry {
  product_id: string;
  quantity: number;
  sale_date: string;
}

export interface SaleRecord {
  id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  total_amount: number;
  sale_date: string;
  created_at: string;
}

export interface SalesHistoryResponse {
  items: SaleRecord[];
  total: number;
}

export interface VelocityPoint {
  date: string;
  product_name: string;
  quantity: number;
}

export interface QuickQuote {
  product_id: string;
  quantity: number;
  fifo_landed_cost_per_unit: number;
  floor_margin_pct: number;
  min_sell_price_per_unit: number;
  total_min_price: number;
}

@Injectable({ providedIn: 'root' })
export class SalesService {
  private readonly api = inject(ApiService);

  createDailyEntry(entries: DailyEntry[]): Observable<SaleRecord[]> {
    return this.api.post<SaleRecord[]>('/sales/daily-entry', { entries });
  }

  getHistory(params?: Record<string, string>): Observable<SalesHistoryResponse> {
    return this.api.get<SalesHistoryResponse>('/sales/history', params);
  }

  getVelocity(days = 30): Observable<VelocityPoint[]> {
    return this.api.get<VelocityPoint[]>('/sales/velocity', { days: String(days) });
  }

  deleteSale(id: string): Observable<void> {
    return this.api.delete<void>(`/sales/${id}`);
  }

  quickQuote(productId: string, quantity: number): Observable<QuickQuote> {
    return this.api.post<QuickQuote>('/sales/quick-quote', {
      product_id: productId,
      quantity,
    });
  }
}
