import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

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
}

export interface LocationListResponse {
  items: Location[];
  total: number;
}

@Injectable({ providedIn: 'root' })
export class LocationsService {
  private readonly api = inject(ApiService);

  getAll(search?: string, activeOnly?: boolean): Observable<LocationListResponse> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    if (activeOnly) params['active_only'] = 'true';
    return this.api.get<LocationListResponse>('/locations', params);
  }

  get(id: string): Observable<Location> {
    return this.api.get<Location>(`/locations/${id}`);
  }

  create(data: LocationCreate): Observable<Location> {
    return this.api.post<Location>('/locations', data);
  }

  update(id: string, data: Partial<LocationCreate & { is_active: boolean }>): Observable<Location> {
    return this.api.patch<Location>(`/locations/${id}`, data);
  }
}
