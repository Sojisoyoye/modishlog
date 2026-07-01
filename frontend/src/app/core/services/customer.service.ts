import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { shareReplay, tap } from 'rxjs/operators';
import { ApiService } from './api.service';

export interface Customer {
  id: string;
  name: string;
  contact_number: string | null;
  email: string | null;
  address: string | null;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerCreate {
  name: string;
  contact_number?: string | null;
  email?: string | null;
  address?: string | null;
  notes?: string | null;
}

export interface CustomerListResponse {
  items: Customer[];
  total: number;
}

@Injectable({ providedIn: 'root' })
export class CustomerService {
  private readonly api = inject(ApiService);

  // Cache the no-search variant (the hot path for dropdowns)
  private allCache$: Observable<CustomerListResponse> | null = null;

  private invalidateCache(): void {
    this.allCache$ = null;
  }

  getAll(search?: string): Observable<CustomerListResponse> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;

    if (!search) {
      if (!this.allCache$) {
        this.allCache$ = this.api
          .get<CustomerListResponse>('/customers', params)
          .pipe(shareReplay(1));
      }
      return this.allCache$;
    }
    return this.api.get<CustomerListResponse>('/customers', params);
  }

  create(data: CustomerCreate): Observable<Customer> {
    return this.api.post<Customer>('/customers', data).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  update(id: string, data: Partial<CustomerCreate>): Observable<Customer> {
    return this.api.put<Customer>(`/customers/${id}`, data).pipe(
      tap(() => this.invalidateCache()),
    );
  }
}
