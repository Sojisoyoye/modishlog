import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from './api.service';

export type SchemeType = 'blank' | 'year';

export interface InvoiceScheme {
  id: string;
  name: string;
  scheme_type: SchemeType;
  prefix: string;
  start_number: number;
  total_digits: number;
  next_number: number;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SchemeCreate {
  name: string;
  scheme_type?: SchemeType;
  prefix?: string;
  start_number?: number;
  total_digits?: number;
}

export interface SchemeUpdate {
  name?: string;
  scheme_type?: SchemeType;
  prefix?: string;
  start_number?: number;
  total_digits?: number;
  is_active?: boolean;
}

export interface SchemeListResponse {
  items: InvoiceScheme[];
  total: number;
}

export interface SchemePreview {
  preview: string;
}

@Injectable({ providedIn: 'root' })
export class InvoiceSchemesService {
  private readonly api = inject(ApiService);

  getAll(): Observable<SchemeListResponse> {
    return this.api.get<SchemeListResponse>('/invoice-schemes');
  }

  create(data: SchemeCreate): Observable<InvoiceScheme> {
    return this.api.post<InvoiceScheme>('/invoice-schemes', data);
  }

  update(id: string, data: SchemeUpdate): Observable<InvoiceScheme> {
    return this.api.patch<InvoiceScheme>(`/invoice-schemes/${id}`, data);
  }

  getPreview(id: string): Observable<SchemePreview> {
    return this.api.post<SchemePreview>(`/invoice-schemes/${id}/preview`, {});
  }
}
