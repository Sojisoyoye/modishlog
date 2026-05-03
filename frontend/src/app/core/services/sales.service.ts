import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

export interface DailyEntry {
  product_id: string;
  quantity: number;
  sale_date: string;
  discount_amount?: number | null;
}

export interface SaleRecord {
  id: string;
  product_id: string;
  product_name?: string;
  quantity: number;
  unit_price: number;
  total_amount: number;
  discount_amount?: number | null;
  currency: string;
  sale_date: string;
  channel: string;
  status: string;
  notes: string | null;
  recorded_by: string;
  created_at: string;
  updated_at: string;
}

export interface SaleListResponse {
  items: SaleRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface SalesHistoryResponse {
  items: SaleRecord[];
  total: number;
}

export interface SaleUpdatePayload {
  quantity?: number;
  unit_price?: number;
  sale_date?: string;
  channel?: string;
  notes?: string;
}

export interface AuditEntry {
  id: string;
  sale_id: string;
  action: string;
  field_changes: Record<string, { old: string; new: string }> | null;
  performed_by: string;
  reason: string | null;
  created_at: string;
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

export interface BulkUploadResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface SaleTransactionItem {
  id: string;
  product_id: string;
  quantity: number;
  unit_price: number;
  discount_amount?: number | null;
  total_amount: number;
  currency: string;
  status: string;
  notes: string | null;
}

export interface SaleTransaction {
  transaction_id: string;
  sale_date: string;
  item_count: number;
  total_amount: number;
  currency: string;
  status: string;
  items: SaleTransactionItem[];
  created_at: string;
}

export interface SaleTransactionListResponse {
  items: SaleTransaction[];
  total: number;
  page: number;
  page_size: number;
}

@Injectable({ providedIn: 'root' })
export class SalesService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  createDailyEntry(entries: DailyEntry[]): Observable<SaleRecord[]> {
    return this.api.post<SaleRecord[]>('/sales/daily-entry', { entries });
  }

  listSales(params?: Record<string, string>): Observable<SaleListResponse> {
    return this.api.get<SaleListResponse>('/sales', params);
  }

  getHistory(params?: Record<string, string>): Observable<SalesHistoryResponse> {
    return this.api.get<SalesHistoryResponse>('/sales/history', params);
  }

  getVelocity(days = 30): Observable<VelocityPoint[]> {
    return this.api.get<VelocityPoint[]>('/sales/velocity', { days: String(days) });
  }

  update(id: string, body: SaleUpdatePayload): Observable<SaleRecord> {
    return this.api.put<SaleRecord>(`/sales/${id}`, body);
  }

  voidSale(id: string, reason: string): Observable<SaleRecord> {
    return this.api.delete<SaleRecord>(`/sales/${id}?reason=${encodeURIComponent(reason)}`);
  }

  getAuditTrail(saleId: string): Observable<AuditEntry[]> {
    return this.api.get<AuditEntry[]>(`/sales/${saleId}/audit`);
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

  getTransactions(params?: Record<string, string>): Observable<SaleTransactionListResponse> {
    return this.api.get<SaleTransactionListResponse>('/sales/transactions', params);
  }

  getTransaction(transactionId: string): Observable<SaleTransaction> {
    return this.api.get<SaleTransaction>(`/sales/transactions/${transactionId}`);
  }

  uploadCsv(file: File): Observable<BulkUploadResponse> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<BulkUploadResponse>(
      `${environment.apiBaseUrl}/sales/upload`,
      formData,
    );
  }
}
