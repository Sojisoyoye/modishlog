import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { DashboardKpiSummary } from '../models/dashboard-kpi.model';

@Injectable({ providedIn: 'root' })
export class DashboardKpiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/dashboard';

  getSummary(
    locationId: string | null,
    dateFrom: string | null,
    dateTo: string | null,
  ): Observable<DashboardKpiSummary> {
    let params = new HttpParams();
    if (locationId) params = params.set('location_id', locationId);
    if (dateFrom) params = params.set('date_from', dateFrom);
    if (dateTo) params = params.set('date_to', dateTo);

    return this.http
      .get<DashboardKpiSummary>(`${this.base}/summary`, { params })
      .pipe(catchError((err) => throwError(() => err)));
  }
}
