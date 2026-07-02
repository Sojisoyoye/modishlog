import { Injectable, inject } from '@angular/core';
import { Observable, shareReplay } from 'rxjs';
import { tap } from 'rxjs/operators';
import { ApiService } from './api.service';

export type LocationType = 'retail' | 'warehouse' | 'online';

export interface Location {
  id: string;
  name: string;
  location_code: string;
  mobile: string | null;
  alternate_number: string | null;
  email: string | null;
  website: string | null;
  landmark: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  zip_code: string | null;
  is_active: boolean;
  timezone: string;
  currency: string;
  tax_number: string | null;
  location_type: LocationType | null;
  is_pos_location: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface LocationCreate {
  name: string;
  location_code: string;
  mobile?: string | null;
  alternate_number?: string | null;
  email?: string | null;
  website?: string | null;
  landmark?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  zip_code?: string | null;
  timezone?: string;
  currency?: string;
  tax_number?: string | null;
  location_type?: LocationType | null;
}

export interface LocationListResponse {
  items: Location[];
  total: number;
}

@Injectable({ providedIn: 'root' })
export class LocationsService {
  private readonly api = inject(ApiService);

  // Cache the active-only list (used by Sales, Dashboard, etc.)
  private activeCache$: Observable<LocationListResponse> | null = null;

  private invalidateCache(): void {
    this.activeCache$ = null;
  }

  getAll(search?: string, activeOnly?: boolean): Observable<LocationListResponse> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    if (activeOnly) params['active_only'] = 'true';

    // Only cache the active-only no-search variant (the hot path)
    if (activeOnly && !search) {
      if (!this.activeCache$) {
        this.activeCache$ = this.api
          .get<LocationListResponse>('/locations', params)
          .pipe(shareReplay(1));
      }
      return this.activeCache$;
    }
    return this.api.get<LocationListResponse>('/locations', params);
  }

  get(id: string): Observable<Location> {
    return this.api.get<Location>(`/locations/${id}`);
  }

  create(data: LocationCreate): Observable<Location> {
    return this.api.post<Location>('/locations', data).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  update(id: string, data: Partial<LocationCreate & { is_active: boolean }>): Observable<Location> {
    return this.api.patch<Location>(`/locations/${id}`, data).pipe(
      tap(() => this.invalidateCache()),
    );
  }
}
