import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
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

  getAll(search?: string): Observable<CustomerListResponse> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    return this.api.get<CustomerListResponse>('/customers', params);
  }

  create(data: CustomerCreate): Observable<Customer> {
    return this.api.post<Customer>('/customers', data);
  }

  update(id: string, data: Partial<CustomerCreate>): Observable<Customer> {
    return this.api.put<Customer>(`/customers/${id}`, data);
  }
}
