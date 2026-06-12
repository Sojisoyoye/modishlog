import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  CreateStockCountRequest,
  StockCount,
  StockCountItem,
  StockCountListItem,
} from '../models/stock-count.model';

@Injectable({ providedIn: 'root' })
export class StockCountService {
  private readonly api = inject(ApiService);

  list(): Observable<StockCountListItem[]> {
    return this.api.get<StockCountListItem[]>('/stockcount/');
  }

  create(body: CreateStockCountRequest): Observable<StockCount> {
    return this.api.post<StockCount>('/stockcount/', body);
  }

  get(id: string): Observable<StockCount> {
    return this.api.get<StockCount>(`/stockcount/${id}`);
  }

  updateItem(stockCountId: string, itemId: string, countedQuantity: number): Observable<StockCountItem> {
    return this.api.patch<StockCountItem>(`/stockcount/${stockCountId}/items/${itemId}`, {
      counted_quantity: countedQuantity,
    });
  }

  finalize(id: string): Observable<StockCount> {
    return this.api.post<StockCount>(`/stockcount/${id}/finalize`, {});
  }
}
