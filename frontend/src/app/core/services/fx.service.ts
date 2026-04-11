import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
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

@Injectable({ providedIn: 'root' })
export class FxService {
  private readonly api = inject(ApiService);

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
}
