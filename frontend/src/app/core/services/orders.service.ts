import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface Order {
  id: string;
  order_number: string;
  supplier: string;
  total_usd: number;
  total_ngn: number;
  status: string;
  order_date: string;
  estimated_arrival_date: string | null;
  locked_fx_rate: number | null;
  locked_amount_usd: number;
  floating_amount_usd: number;
  items: OrderItem[];
}

export interface OrderItem {
  id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_cost_usd: number;
  total_usd: number;
}

export interface CreateOrderPayload {
  supplier: string;
  items: { product_id: string; quantity: number; unit_cost_usd: number }[];
  production_days: number;
  shipping_days: number;
  clearing_days: number;
}

export interface ProfitProjection {
  base: ScenarioResult;
  best_case: ScenarioResult;
  worst_case: ScenarioResult;
}

export interface ScenarioResult {
  fx_rate: number;
  total_cost_ngn: number;
  total_revenue_ngn: number;
  total_profit_ngn: number;
  margin_pct: number;
}

@Injectable({ providedIn: 'root' })
export class OrdersService {
  private readonly api = inject(ApiService);

  getAll(params?: Record<string, string>): Observable<Order[]> {
    return this.api.get<Order[]>('/orders', params);
  }

  getById(id: string): Observable<Order> {
    return this.api.get<Order>(`/orders/${id}`);
  }

  create(data: CreateOrderPayload): Observable<Order> {
    return this.api.post<Order>('/orders', data);
  }

  updateStatus(id: string, newStatus: string): Observable<Order> {
    return this.api.put<Order>(`/orders/${id}/status`, { status: newStatus });
  }

  getPipeline(): Observable<Record<string, number>> {
    return this.api.get<Record<string, number>>('/orders/pipeline');
  }

  getProfitProjection(id: string): Observable<ProfitProjection> {
    return this.api.get<ProfitProjection>(`/orders/${id}/profit-projection`);
  }

  getLogisticsEfficiency(): Observable<LogisticsEfficiency> {
    return this.api.get<LogisticsEfficiency>('/orders/logistics-efficiency');
  }
}

export interface LogisticsEfficiency {
  per_order: OrderLogistics[];
  rolling_90d_avg_pct: number;
  amber_threshold_pct: number;
  red_threshold_pct: number;
  status: string;
}

export interface OrderLogistics {
  order_id: string;
  order_number: string;
  logistics_pct: number;
  logistics_ngn: number;
  total_cogs_ngn: number;
}
