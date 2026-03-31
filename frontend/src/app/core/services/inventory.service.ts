import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface InventoryItem {
  product_id: string;
  product_name: string;
  current_stock: number;
  low_stock_threshold: number;
  depletion_date: string | null;
  last_updated: string;
}

export interface StockMovement {
  id: string;
  product_id: string;
  product_name: string;
  movement_type: string;
  quantity: number;
  reference_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface StockAdjustment {
  product_id: string;
  adjustment_type: string;
  quantity: number;
  notes: string;
}

@Injectable({ providedIn: 'root' })
export class InventoryService {
  private readonly api = inject(ApiService);

  getCurrent(): Observable<InventoryItem[]> {
    return this.api.get<InventoryItem[]>('/inventory/current');
  }

  getMovements(params?: Record<string, string>): Observable<StockMovement[]> {
    return this.api.get<StockMovement[]>('/inventory/movements', params);
  }

  adjust(data: StockAdjustment): Observable<unknown> {
    return this.api.post('/inventory/adjust', data);
  }
}
