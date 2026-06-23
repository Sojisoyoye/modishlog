import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import { DashboardKpiSummary } from '../models/dashboard-kpi.model';

@Injectable({ providedIn: 'root' })
export class DashboardKpiService {
  private readonly api = inject(ApiService);

  getSummary(
    locationId: string | null,
    dateFrom: string | null,
    dateTo: string | null,
  ): Observable<DashboardKpiSummary> {
    const params: Record<string, string> = {};
    if (locationId) params['location_id'] = locationId;
    if (dateFrom) params['date_from'] = dateFrom;
    if (dateTo) params['date_to'] = dateTo;

    return this.api.get<DashboardKpiSummary>('/dashboard/summary', params);
  }
}
