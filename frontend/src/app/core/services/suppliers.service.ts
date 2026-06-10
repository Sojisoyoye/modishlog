import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface Supplier {
  id: string;
  name: string;
  contact_person: string | null;
  email: string | null;
  mobile: string | null;
  alternate_number: string | null;
  tax_number: string | null;
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  zip_code: string | null;
  pay_term_number: number | null;
  pay_term_type: 'days' | 'months' | null;
  opening_balance: number;
  notes: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SupplierUpdate extends Partial<SupplierCreate> {
  is_active?: boolean;
}

export interface SupplierCreate {
  name: string;
  contact_person?: string | null;
  email?: string | null;
  mobile?: string | null;
  alternate_number?: string | null;
  tax_number?: string | null;
  address_line_1?: string | null;
  address_line_2?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  zip_code?: string | null;
  pay_term_number?: number | null;
  pay_term_type?: string | null;
  opening_balance?: number;
  notes?: string | null;
}

export interface LedgerEntry {
  date: string;
  description: string;
  debit: number;
  credit: number;
  balance: number;
}

export interface ActivityEntry {
  timestamp: string;
  event_type: string;
  description: string;
  amount: number | null;
  reference: string | null;
}

export interface SupplierPurchase {
  id: string;
  order_number: string;
  status: string;
  total_amount: number;
  created_at: string;
}

export interface StockReportItem {
  product_id: string;
  sku: string;
  product_name: string;
  quantity_on_hand: number;
  unit_cost: number;
  stock_value: number;
}

@Injectable({ providedIn: 'root' })
export class SuppliersService {
  private readonly api = inject(ApiService);

  getAll(params?: Record<string, string>): Observable<{ items: Supplier[]; total: number }> {
    return this.api.get<{ items: Supplier[]; total: number }>('/suppliers', params);
  }

  get(id: string): Observable<Supplier> {
    return this.api.get<Supplier>(`/suppliers/${id}`);
  }

  create(data: SupplierCreate): Observable<Supplier> {
    return this.api.post<Supplier>('/suppliers', data);
  }

  update(id: string, data: SupplierUpdate): Observable<Supplier> {
    return this.api.patch<Supplier>(`/suppliers/${id}`, data);
  }

  getPurchases(id: string): Observable<{ items: SupplierPurchase[]; total: number }> {
    return this.api.get<{ items: SupplierPurchase[]; total: number }>(`/suppliers/${id}/purchases`);
  }

  getLedger(id: string): Observable<LedgerEntry[]> {
    return this.api.get<LedgerEntry[]>(`/suppliers/${id}/ledger`);
  }

  getStockReport(id: string): Observable<StockReportItem[]> {
    return this.api.get<StockReportItem[]>(`/suppliers/${id}/stock-report`);
  }

  getActivities(id: string): Observable<ActivityEntry[]> {
    return this.api.get<ActivityEntry[]>(`/suppliers/${id}/activities`);
  }
}
