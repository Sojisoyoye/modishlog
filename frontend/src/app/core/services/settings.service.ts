import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface ApiKeyStatus {
  key_name: string;
  is_configured: boolean;
}

export interface FiscalYearStart {
  fiscal_year_start_month: number | null;
  fiscal_year_start_day: number | null;
}

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly api = inject(ApiService);

  saveApiKey(keyName: string, keyValue: string): Observable<ApiKeyStatus> {
    return this.api.post<ApiKeyStatus>('/settings/api-key', {
      key_name: keyName,
      key_value: keyValue,
    });
  }

  getApiKeyStatus(keyName: string): Observable<ApiKeyStatus> {
    return this.api.get<ApiKeyStatus>(`/settings/api-key/${keyName}`);
  }

  getFiscalYearStart(): Observable<FiscalYearStart> {
    return this.api.get<FiscalYearStart>('/settings/fiscal-year');
  }
}
