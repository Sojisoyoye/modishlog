import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

export interface Order {
  id: string;
  order_number: string;
  supplier_id: string | null;
  supplier_name: string;
  supplier_contact: string | null;
  is_purchase_order: boolean;
  total_amount: number;
  status: string;
  created_at: string;
  expected_delivery_date: string | null;
  fx_rate_at_creation: number | null;
  fx_rate_at_delivery: number | null;
  shipping_cost: number;
  clearing_cost: number;
  pay_term_number: number | null;
  pay_term_type: string | null;
  shipping_details: string | null;
  discount_type: string | null;
  discount_amount: number;
  tax_rate: number | null;
  tax_amount: number;
  supplier_invoice_number: string | null;
  supplier_invoice_date: string | null;
  line_items: OrderItem[];
}

export interface OrderItem {
  id: string;
  product_id: string;
  quantity: number;
  unit_cost: number;
  line_total: number;
}

export interface CreateOrderPayload {
  supplier_name: string;
  supplier_id?: string | null;
  is_purchase_order?: boolean;
  line_items: { product_id: string; quantity: number; unit_cost: number }[];
  production_days?: number;
  shipping_days?: number;
  clearing_days?: number;
  shipping_cost?: number;
  clearing_cost?: number;
  pay_term_number?: number | null;
  pay_term_type?: string | null;
  shipping_details?: string | null;
  discount_type?: string | null;
  discount_amount?: number;
  tax_rate?: number | null;
  additional_expense_key_1?: string | null;
  additional_expense_value_1?: number | null;
  additional_expense_key_2?: string | null;
  additional_expense_value_2?: number | null;
  additional_expense_key_3?: string | null;
  additional_expense_value_3?: number | null;
  additional_expense_key_4?: string | null;
  additional_expense_value_4?: number | null;
  supplier_invoice_number?: string | null;
  supplier_invoice_date?: string | null;
}

export interface PurchaseReturnPayload {
  original_order_id: string;
  notes?: string | null;
  line_items: { product_id: string; quantity: number }[];
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
  private readonly http = inject(HttpClient);

  getAll(params?: Record<string, string>): Observable<Order[]> {
    return this.api.get<{ items: Order[]; total: number }>('/orders', params).pipe(
      map((resp) => resp.items),
    );
  }

  getById(id: string): Observable<Order> {
    return this.api.get<Order>(`/orders/${id}`);
  }

  create(data: CreateOrderPayload): Observable<Order> {
    return this.api.post<Order>('/orders', data);
  }

  updateStatus(id: string, newStatus: string, fxRateAtDelivery?: number): Observable<Order> {
    const body: Record<string, unknown> = { new_status: newStatus };
    if (fxRateAtDelivery != null) body['fx_rate_at_delivery'] = fxRateAtDelivery;
    return this.api.put<Order>(`/orders/${id}/status`, body);
  }

  convertPoToPurchase(id: string): Observable<Order> {
    return this.api.post<Order>(`/orders/${id}/convert-to-purchase`, {});
  }

  createReturn(data: PurchaseReturnPayload): Observable<unknown> {
    return this.api.post<unknown>('/orders/returns', data);
  }

  getProfitProjection(id: string): Observable<ProfitProjection> {
    return this.api.get<ProfitProjection>(`/orders/${id}/profit-projection`);
  }

  getLogisticsEfficiency(): Observable<LogisticsEfficiency> {
    return this.api.get<LogisticsEfficiency>('/orders/logistics-efficiency');
  }

  exportCsv(params?: Record<string, string>): Observable<Blob> {
    let queryString = '';
    if (params) {
      const parts = Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
      if (parts.length > 0) queryString = '?' + parts.join('&');
    }
    return this.http.get(`${environment.apiBaseUrl}/orders/export.csv${queryString}`, {
      responseType: 'blob',
    });
  }

  getImportTemplateUrl(): string {
    return `${environment.apiBaseUrl}/orders/import/template`;
  }

  importOrders(file: File): Observable<BulkImportResult> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<BulkImportResult>(
      `${environment.apiBaseUrl}/orders/import`,
      formData,
    );
  }
}

export interface ImportRowError {
  row: number;
  message: string;
}

export interface BulkImportResult {
  created: number;
  orders: Order[];
  errors: ImportRowError[];
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
