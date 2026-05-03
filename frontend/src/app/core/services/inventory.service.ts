import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { ApiService } from './api.service';

/** Shape returned by the backend GET /inventory endpoint. */
interface InventoryLevelDTO {
  id: string;
  product_id: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  low_stock_threshold: number;
  last_replenished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InventoryItem {
  product_id: string;
  product_name?: string;
  current_stock: number;
  low_stock_threshold: number;
  depletion_date?: string | null;
  last_updated: string;
}

export interface StockMovement {
  id: string;
  product_id: string;
  product_name?: string;
  movement_type: string;
  quantity_change: number;
  quantity_after?: number;
  reference_id: string | null;
  reason: string | null;
  created_at: string;
}

export interface StockAdjustment {
  quantity_change: number;
  movement_type: 'manual_add' | 'manual_remove' | 'damaged' | 'order_received';
  reason: string;
}

@Injectable({ providedIn: 'root' })
export class InventoryService {
  private readonly api = inject(ApiService);

  getCurrent(): Observable<InventoryItem[]> {
    return this.api.get<InventoryLevelDTO[]>('/inventory').pipe(
      map((levels) =>
        levels.map((l) => ({
          product_id: l.product_id,
          current_stock: l.quantity_on_hand,
          low_stock_threshold: l.low_stock_threshold,
          last_updated: l.updated_at,
        })),
      ),
    );
  }

  getMovements(limit = 50): Observable<StockMovement[]> {
    return this.api.get<StockMovement[]>('/inventory/movements', { limit: String(limit) });
  }

  getProductMovements(productId: string): Observable<StockMovement[]> {
    return this.api.get<StockMovement[]>(`/inventory/${productId}/movements`);
  }

  adjust(productId: string, data: StockAdjustment): Observable<unknown> {
    return this.api.post(`/inventory/${productId}/adjust`, data);
  }

  getBatches(productId: string): Observable<InventoryBatch[]> {
    return this.api.get<InventoryBatch[]>('/inventory/batches', { product_id: productId });
  }

  updateThreshold(productId: string, threshold: number): Observable<unknown> {
    return this.api.put(`/inventory/${productId}/threshold`, { low_stock_threshold: threshold });
  }

  getLiquidationCandidates(targetNgn = 500000): Observable<LiquidationCandidate[]> {
    return this.api.get<LiquidationCandidate[]>('/inventory/batches/liquidation-candidates', {
      target_ngn: String(targetNgn),
    });
  }
}

export interface InventoryBatch {
  id: string;
  product_id: string;
  order_id: string;
  quantity_received: number;
  quantity_remaining: number;
  unit_cost_usd: number;
  fx_rate_at_arrival: number;
  logistics_allocation_per_unit: number;
  landed_cost_per_unit: number;
  received_at: string;
  created_at: string;
}

export interface LiquidationCandidate {
  batch_id: string;
  product_id: string;
  quantity_remaining: number;
  landed_cost_per_unit: number;
  total_batch_value: number;
  discount_pct_needed: number;
}
