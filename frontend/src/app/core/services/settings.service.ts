import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface ApiKeyStatus {
  key_name: string;
  is_configured: boolean;
}

export interface ApiKeyTestResult {
  success: boolean;
  message: string;
  latency_ms: number | null;
}

export interface FiscalYearStart {
  fiscal_year_start_month: number | null;
  fiscal_year_start_day: number | null;
}

export interface BusinessProfile {
  id: string;
  business_name: string | null;
  address_line_1: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  zip_code: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  tax_number: string | null;
  registration_number: string | null;
  currency: string;
  timezone: string;
  updated_at: string;
}

export type BusinessProfileUpdate = Partial<Omit<BusinessProfile, 'id' | 'updated_at'>>;

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

  testApiKey(keyName: string): Observable<ApiKeyTestResult> {
    return this.api.get<ApiKeyTestResult>(`/settings/api-key/${keyName}/test`);
  }

  getFiscalYearStart(): Observable<FiscalYearStart> {
    return this.api.get<FiscalYearStart>('/settings/fiscal-year');
  }

  updateFiscalYearStart(month: number | null, day: number | null): Observable<FiscalYearStart> {
    return this.api.put<FiscalYearStart>('/settings/fiscal-year', {
      fiscal_year_start_month: month,
      fiscal_year_start_day: day,
    });
  }

  getBusinessProfile(): Observable<BusinessProfile> {
    return this.api.get<BusinessProfile>('/settings/business-profile');
  }

  updateBusinessProfile(data: BusinessProfileUpdate): Observable<BusinessProfile> {
    return this.api.put<BusinessProfile>('/settings/business-profile', data);
  }

  getAppSettings(): Observable<Record<string, string | null>> {
    return this.api.get<Record<string, string | null>>('/settings/app');
  }

  updateAppSetting(key: string, value: string): Observable<void> {
    return this.api.put<void>(`/settings/app/${key}`, { value });
  }
}
