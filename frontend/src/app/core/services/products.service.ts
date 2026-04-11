import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

export interface Product {
  id: string;
  name: string;
  sku: string;
  description?: string;
  category_id: string | null;
  unit_cost: number;
  selling_price: number;
  currency: string;
  is_active: boolean;
  image_url?: string | null;
}

export interface Category {
  id: string;
  name: string;
  description?: string;
}

export interface CategoryCreate {
  name: string;
  description?: string;
}

export interface ProductCreate {
  name: string;
  sku?: string;
  description?: string;
  category_id?: string;
  unit_cost: number;
  selling_price: number;
  currency?: string;
}

export interface ProductUpdate {
  name?: string;
  description?: string;
  category_id?: string;
  unit_cost?: number;
  selling_price?: number;
  is_active?: boolean;
}

interface ProductListResponse {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
}

@Injectable({ providedIn: 'root' })
export class ProductsService {
  private readonly api = inject(ApiService);
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl;

  getAll(): Observable<Product[]> {
    return this.api
      .get<ProductListResponse>('/products')
      .pipe(map((resp) => resp.items ?? []));
  }

  getById(id: string): Observable<Product> {
    return this.api.get<Product>(`/products/${id}`);
  }

  getCategories(): Observable<Category[]> {
    return this.api.get<Category[]>('/products/categories');
  }

  createCategory(body: CategoryCreate): Observable<Category> {
    return this.api.post<Category>('/products/categories', body);
  }

  deleteCategory(id: string): Observable<void> {
    return this.api.delete<void>(`/products/categories/${id}`);
  }

  create(body: ProductCreate): Observable<Product> {
    return this.api.post<Product>('/products', body);
  }

  update(id: string, body: ProductUpdate): Observable<Product> {
    return this.api.put<Product>(`/products/${id}`, body);
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/products/${id}`);
  }

  uploadImage(id: string, file: File): Observable<Product> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<Product>(`${this.baseUrl}/products/${id}/image`, formData);
  }
}
