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
  actual_delivery_date: string | null;
  notes: string | null;
  currency: string;
  updated_at: string;
  order_date: string | null;
  payment_status: string | null;
  location_id: string | null;
  total_paid: number;
  balance_remaining: number;
  additional_expense_key_1: string | null;
  additional_expense_value_1: number | null;
  additional_expense_key_2: string | null;
  additional_expense_value_2: number | null;
  additional_expense_key_3: string | null;
  additional_expense_value_3: number | null;
  additional_expense_key_4: string | null;
  additional_expense_value_4: number | null;
  line_items: OrderItem[];
}

export interface OrderItem {
  id: string;
  product_id: string;
  quantity: number;
  unit_cost: number;
  unit_cost_ngn: number | null;
  sell_price_ngn: number | null;
  units_remaining: number | null;
  line_total: number;
}

export interface CreateOrderPayload {
  supplier_name: string;
  supplier_id?: string | null;
  is_purchase_order?: boolean;
  line_items: { product_id: string; quantity: number; unit_cost: number; variant_id?: string }[];
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

function coerceOrderDetail(o: OrderDetail): OrderDetail {
  const raw = o as unknown as Record<string, unknown>;
  const numFields = [
    'total_amount', 'shipping_cost', 'clearing_cost', 'discount_amount',
    'tax_amount', 'fx_rate_at_creation', 'fx_rate_at_delivery', 'pay_term_number',
    'additional_expense_value_1', 'additional_expense_value_2',
    'additional_expense_value_3', 'additional_expense_value_4',
  ];
  const coerced = { ...raw };
  for (const f of numFields) {
    if (coerced[f] != null) coerced[f] = Number(coerced[f]);
  }
  coerced['line_items'] = ((o.line_items ?? []) as OrderItem[]).map((item) => ({
    ...item,
    quantity: Number(item.quantity),
    unit_cost: Number(item.unit_cost),
    unit_cost_ngn: item.unit_cost_ngn != null ? Number(item.unit_cost_ngn) : null,
    sell_price_ngn: item.sell_price_ngn != null ? Number(item.sell_price_ngn) : null,
    units_remaining: item.units_remaining != null ? Number(item.units_remaining) : null,
    line_total: Number(item.line_total),
  }));
  if (o.payment_summary) {
    coerced['payment_summary'] = {
      ...o.payment_summary,
      total_due: Number(o.payment_summary.total_due),
      total_paid: Number(o.payment_summary.total_paid),
      balance_remaining: Number(o.payment_summary.balance_remaining),
      payment_count: Number(o.payment_summary.payment_count),
    };
  }
  return coerced as unknown as OrderDetail;
}

@Injectable({ providedIn: 'root' })
export class OrdersService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  getAll(params?: Record<string, string>): Observable<{ items: Order[]; total: number }> {
    return this.api.get<{ items: Order[]; total: number }>('/orders', params).pipe(
      map((resp) => ({
        items: resp.items.map((o) => ({
          ...o,
          total_amount: Number(o.total_amount),
          total_paid: Number(o.total_paid ?? 0),
          balance_remaining: Number(o.balance_remaining ?? 0),
        })),
        total: resp.total,
      })),
    );
  }

  getStatusCounts(): Observable<Record<string, number>> {
    return this.api.get<Record<string, number>>('/orders/status-counts');
  }

  getById(id: string): Observable<OrderDetail> {
    return this.api.get<OrderDetail>(`/orders/${id}`).pipe(map(coerceOrderDetail));
  }

  update(id: string, data: UpdateOrderPayload): Observable<OrderDetail> {
    return this.api.put<OrderDetail>(`/orders/${id}`, data).pipe(map(coerceOrderDetail));
  }

  create(data: CreateOrderPayload): Observable<Order> {
    return this.api.post<Order>('/orders', data);
  }

  updateStatus(id: string, newStatus: string, fxRateAtDelivery?: number): Observable<OrderDetail> {
    const body: Record<string, unknown> = { new_status: newStatus };
    if (fxRateAtDelivery != null) body['fx_rate_at_delivery'] = fxRateAtDelivery;
    return this.api.put<OrderDetail>(`/orders/${id}/status`, body).pipe(map(coerceOrderDetail));
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

  getProductsTemplateUrl(): string {
    return `${environment.apiBaseUrl}/orders/parse-products/template`;
  }

  parseProducts(file: File): Observable<ParseProductsResult> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<ParseProductsResult>(
      `${environment.apiBaseUrl}/orders/parse-products`,
      formData,
    );
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

  listPayments(orderId: string): Observable<OrderPayment[]> {
    return this.api.get<OrderPayment[]>(`/orders/${orderId}/payments`);
  }

  recordPayment(orderId: string, data: RecordPaymentPayload): Observable<OrderPayment> {
    return this.api.post<OrderPayment>(`/orders/${orderId}/payments`, data);
  }

  voidPayment(orderId: string, paymentId: string): Observable<OrderPayment> {
    return this.api.delete<OrderPayment>(`/orders/${orderId}/payments/${paymentId}`);
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

export interface ParsedLineItem {
  product_id: string;
  sku: string;
  product_name: string;
  quantity: number;
  unit_cost: number;
}

export interface ParseProductsResult {
  items: ParsedLineItem[];
  errors: ImportRowError[];
}

export interface OrderPayment {
  id: string;
  order_id: string;
  amount: number;
  currency: string;
  fx_rate: number | null;
  original_amount: number | null;
  original_currency: string | null;
  payment_date: string;
  payment_method: string;
  reference: string | null;
  status: string;
  notes: string | null;
  recorded_by: string;
  created_at: string;
}

export interface RecordPaymentPayload {
  amount: number;
  currency: string;
  fx_rate?: number | null;
  payment_date: string;
  payment_method: string;
  reference?: string | null;
  notes?: string | null;
}

export interface UpdateOrderPayload {
  supplier_name?: string | null;
  supplier_contact?: string | null;
  expected_delivery_date?: string | null;
  notes?: string | null;
  shipping_cost?: number | null;
  shipping_details?: string | null;
  fx_rate_at_creation?: number | null;
  supplier_invoice_number?: string | null;
  supplier_invoice_date?: string | null;
  pay_term_number?: number | null;
  pay_term_type?: string | null;
  line_items?: { product_id: string; quantity: number; unit_cost: number; unit_cost_ngn?: number | null; sell_price_ngn?: number | null }[] | null;
  order_date?: string | null;
  payment_status?: string | null;
  location_id?: string | null;
}

export interface PaymentSummary {
  total_due: number;
  total_paid: number;
  balance_remaining: number;
  payment_count: number;
  is_fully_paid: boolean;
}

export interface OrderDetail extends Order {
  payment_summary: PaymentSummary | null;
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
