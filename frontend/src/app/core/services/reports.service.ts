import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

export interface ProfitLossReport {
  total_purchase_excl_tax: number;
  purchase_returns_total: number;
  total_sales: number;
  gross_profit: number;
  total_operating_costs: number;
  net_profit: number;
  opening_stock_value: number;
  closing_stock_value: number;
  total_sales_returns: number;
  purchase_due: number;
  sales_due: number;
}

export interface StockReportItem {
  product_id: string;
  sku: string;
  product_name: string;
  category: string | null;
  unit_cost: number;
  selling_price: number;
  quantity_on_hand: number;
  stock_value: number;
  potential_profit: number;
  total_sold: number;
}

export interface StockReport {
  items: StockReportItem[];
  total_stock_value: number;
  total_potential_profit: number;
  total_sold: number;
}

export interface PurchaseSaleReport {
  total_purchase: number;
  total_purchase_returns: number;
  total_sales: number;
  total_sales_returns: number;
  net_position: number;
}

@Injectable({ providedIn: 'root' })
export class ReportsService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  getProfitLoss(startDate?: string, endDate?: string): Observable<ProfitLossReport> {
    const params: Record<string, string> = {};
    if (startDate) params['start_date'] = startDate;
    if (endDate) params['end_date'] = endDate;
    return this.api.get<ProfitLossReport>('/reports/profit-loss', params);
  }

  getStockReport(): Observable<StockReport> {
    return this.api.get<StockReport>('/reports/stock');
  }

  getPurchaseSaleReport(startDate?: string, endDate?: string): Observable<PurchaseSaleReport> {
    const params: Record<string, string> = {};
    if (startDate) params['start_date'] = startDate;
    if (endDate) params['end_date'] = endDate;
    return this.api.get<PurchaseSaleReport>('/reports/purchase-sale', params);
  }

  exportStockCsv(): Observable<Blob> {
    return this.http.get(`${environment.apiBaseUrl}/reports/stock/export-csv`, {
      responseType: 'blob',
    });
  }

  exportProfitLossCsv(startDate?: string, endDate?: string): Observable<Blob> {
    const params: Record<string, string> = {};
    if (startDate) params['start_date'] = startDate;
    if (endDate) params['end_date'] = endDate;
    const query = new URLSearchParams(params).toString();
    const url = `${environment.apiBaseUrl}/reports/profit-loss/export-csv${query ? '?' + query : ''}`;
    return this.http.get(url, { responseType: 'blob' });
  }

  exportPurchaseSaleCsv(startDate?: string, endDate?: string): Observable<Blob> {
    const params: Record<string, string> = {};
    if (startDate) params['start_date'] = startDate;
    if (endDate) params['end_date'] = endDate;
    const query = new URLSearchParams(params).toString();
    const url = `${environment.apiBaseUrl}/reports/purchase-sale/export-csv${query ? '?' + query : ''}`;
    return this.http.get(url, { responseType: 'blob' });
  }
}
