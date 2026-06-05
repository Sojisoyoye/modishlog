import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

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

interface FXRateRead {
  id: string;
  pair: string;
  rate: number;
  source: string;
  timestamp: string;
  created_at: string;
}

interface FXRateHistory {
  pair: string;
  rates: FXRateRead[];
}

interface ForecastRead {
  id: string;
  pair: string;
  forecast_date: string;
  base_rate: number;
  best_case_rate: number;
  worst_case_rate: number;
}

interface ForecastRangeResponse {
  pair: string;
  forecasts: ForecastRead[];
  model_version: string;
}

export interface FXAlertCreate {
  pair: string;
  direction: 'above' | 'below';
  threshold_rate: number;
}

export interface FXAlertRead {
  id: string;
  pair: string;
  direction: string;
  threshold_rate: number;
  is_enabled: boolean;
  is_triggered: boolean;
  triggered_at: string | null;
  triggered_rate: number | null;
  created_by: string;
  created_at: string;
}

export interface FXAlertUpdate {
  threshold_rate?: number;
  is_enabled?: boolean;
}

@Injectable({ providedIn: 'root' })
export class FxService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);

  getLatest(): Observable<FxRate> {
    return this.api.get<FXRateRead[]>('/fx/rates/current').pipe(
      map((rates) => {
        const rate = rates.find((r) => r.pair === 'USDNGN') ?? rates[0];
        return rate
          ? {
              id: rate.id,
              rate: Number(rate.rate),
              rate_date: rate.timestamp,
              rate_type: rate.pair,
              source: rate.source,
              created_at: rate.created_at,
            }
          : {
              id: '',
              rate: 0,
              rate_date: new Date().toISOString(),
              rate_type: 'USDNGN',
              source: '-',
              created_at: new Date().toISOString(),
            };
      })
    );
  }

  getHistory(days = 90): Observable<FxRate[]> {
    const dateTo = new Date();
    const dateFrom = new Date(dateTo.getTime() - days * 24 * 60 * 60 * 1000);
    return this.api
      .get<FXRateHistory>('/fx/rates/USDNGN/history', {
        date_from: dateFrom.toISOString().split('T')[0],
        date_to: dateTo.toISOString().split('T')[0],
      })
      .pipe(
        map((history) =>
          history.rates.map((r) => ({
            id: r.id,
            rate: Number(r.rate),
            rate_date: r.timestamp,
            rate_type: r.pair,
            source: r.source,
            created_at: r.created_at,
          }))
        )
      );
  }

  getForecast(days = 30): Observable<FxForecast[]> {
    const dateFrom = new Date();
    const dateTo = new Date(dateFrom.getTime() + days * 24 * 60 * 60 * 1000);
    return this.api
      .get<ForecastRangeResponse>('/fx/forecast/USDNGN', {
        date_from: dateFrom.toISOString().split('T')[0],
        date_to: dateTo.toISOString().split('T')[0],
      })
      .pipe(
        map((resp) =>
          resp.forecasts.map((f) => ({
            date: f.forecast_date,
            base: Number(f.base_rate),
            best_case: Number(f.best_case_rate),
            worst_case: Number(f.worst_case_rate),
          }))
        )
      );
  }

  addManualRate(data: ManualRateEntry): Observable<FxRate> {
    return this.api
      .post<FXRateRead>('/fx/rates/ingest', {
        pair: data.rate_type || 'USDNGN',
        rate: data.rate,
        source: data.source.toLowerCase(),
        timestamp: data.rate_date ? `${data.rate_date}T00:00:00Z` : undefined,
      })
      .pipe(
        map((r) => ({
          id: r.id,
          rate: Number(r.rate),
          rate_date: r.timestamp,
          rate_type: r.pair,
          source: r.source,
          created_at: r.created_at,
        }))
      );
  }

  getAlerts(): Observable<FXAlertRead[]> {
    return this.api.get<FXAlertRead[]>('/fx/alerts');
  }

  createAlert(body: FXAlertCreate): Observable<FXAlertRead> {
    return this.api.post<FXAlertRead>('/fx/alerts', body);
  }

  updateAlert(id: string, body: FXAlertUpdate): Observable<FXAlertRead> {
    return this.api.put<FXAlertRead>(`/fx/alerts/${id}`, body);
  }

  deleteAlert(id: string): Observable<void> {
    return this.api.delete<void>(`/fx/alerts/${id}`);
  }

  getLatestEurUsd(): Observable<FxRate | null> {
    return this.api.get<FXRateRead[]>('/fx/rates/current').pipe(
      map((rates) => {
        const rate = rates.find((r) => r.pair === 'EURUSD');
        return rate
          ? {
              id: rate.id,
              rate: Number(rate.rate),
              rate_date: rate.timestamp,
              rate_type: rate.pair,
              source: rate.source,
              created_at: rate.created_at,
            }
          : null;
      })
    );
  }

  exportCsv(params?: Record<string, string>): Observable<Blob> {
    let queryString = '';
    if (params) {
      const parts = Object.entries(params)
        .filter(([, v]) => v !== undefined && v !== '')
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`);
      if (parts.length > 0) queryString = '?' + parts.join('&');
    }
    return this.http.get(`${environment.apiBaseUrl}/fx/export.csv${queryString}`, {
      responseType: 'blob',
    });
  }
}
