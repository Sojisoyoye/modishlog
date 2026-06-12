import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export interface ApiKeyStatus {
  key_name: string;
  is_configured: boolean;
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
}
