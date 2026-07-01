import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  Sale,
  SaleListResponse,
  SellReturn,
  SellReturnCreate,
  SellReturnListResponse,
  PurchaseReturnListResponse,
} from '../models/return.model';

@Injectable({ providedIn: 'root' })
export class ReturnsService {
  private readonly api = inject(ApiService);

  getRecentSales(pageSize = 50): Observable<SaleListResponse> {
    return this.api.get<SaleListResponse>('/sales', { page: '1', page_size: String(pageSize) });
  }

  getSellReturns(params?: Record<string, string>): Observable<SellReturnListResponse> {
    return this.api.get<SellReturnListResponse>('/sales/returns/sells', params);
  }

  createSellReturn(saleId: string, data: SellReturnCreate): Observable<SellReturn> {
    return this.api.post<SellReturn>(`/sales/${saleId}/returns`, data);
  }

  getPurchaseReturns(params?: Record<string, string>): Observable<PurchaseReturnListResponse> {
    return this.api.get<PurchaseReturnListResponse>('/orders/returns/purchases', params);
  }
}
