import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { shareReplay, tap } from 'rxjs/operators';
import { ApiService } from '../../../core/services/api.service';

export interface Customer {
  id: string;
  name: string;
  contact_number: string | null;
  alternate_number: string | null;
  email: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  zip_code: string | null;
  tax_number: string | null;
  pay_term_number: number | null;
  pay_term_type: 'days' | 'months' | null;
  opening_balance: number;
  credit_limit: number | null;
  is_active: boolean;
  customer_group: string | null;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerCreate {
  name: string;
  contact_number?: string | null;
  alternate_number?: string | null;
  email?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  zip_code?: string | null;
  tax_number?: string | null;
  pay_term_number?: number | null;
  pay_term_type?: string | null;
  opening_balance?: number;
  credit_limit?: number | null;
  is_active?: boolean;
  customer_group?: string | null;
  notes?: string | null;
}

export type CustomerUpdate = Partial<CustomerCreate>;

export interface CustomerListResponse {
  items: Customer[];
  total: number;
}

@Injectable({ providedIn: 'root' })
export class CustomersService {
  private readonly api = inject(ApiService);

  // Cache the no-params variant (full list used for dropdowns/filters)
  private allCache$: Observable<CustomerListResponse> | null = null;

  private invalidateCache(): void {
    this.allCache$ = null;
  }

  getCustomers(params?: Record<string, string>): Observable<CustomerListResponse> {
    if (!params || Object.keys(params).length === 0) {
      if (!this.allCache$) {
        this.allCache$ = this.api
          .get<CustomerListResponse>('/customers')
          .pipe(shareReplay(1));
      }
      return this.allCache$;
    }
    return this.api.get<CustomerListResponse>('/customers', params);
  }

  getCustomer(id: string): Observable<Customer> {
    return this.api.get<Customer>(`/customers/${id}`);
  }

  createCustomer(data: CustomerCreate): Observable<Customer> {
    return this.api.post<Customer>('/customers', data).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  updateCustomer(id: string, data: CustomerUpdate): Observable<Customer> {
    return this.api.put<Customer>(`/customers/${id}`, data).pipe(
      tap(() => this.invalidateCache()),
    );
  }
}
