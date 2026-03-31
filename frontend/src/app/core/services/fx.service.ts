import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface FxRate {
  id: string;
  rate: number;
  rate_date: string;
  rate_type: string;
  source: string;
  created_at: string;
}

export interface FxForecast {
  date: string;
  base: number;
  best_case: number;
  worst_case: number;
}

export interface ManualRateEntry {
  rate: number;
  rate_date: string;
  rate_type: string;
  source: string;
}

@Injectable({ providedIn: 'root' })
export class FxService {
  private readonly api = inject(ApiService);

  getLatest(): Observable<FxRate> {
    return this.api.get<FxRate>('/fx/rates/latest');
  }

  getHistory(days = 90): Observable<FxRate[]> {
    return this.api.get<FxRate[]>('/fx/rates/history', { days: String(days) });
  }

  getForecast(days = 30): Observable<FxForecast[]> {
    return this.api.get<FxForecast[]>('/fx/forecast', { days: String(days) });
  }

  addManualRate(data: ManualRateEntry): Observable<FxRate> {
    return this.api.post<FxRate>('/fx/rates/manual', data);
  }
}
