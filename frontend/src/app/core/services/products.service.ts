import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, forkJoin, shareReplay } from 'rxjs';
import { map, switchMap, tap } from 'rxjs/operators';
import { ApiService } from './api.service';
import { environment } from '../../../environments/environment';

export interface ProductVariant {
  id: string;
  product_id: string;
  business_id: string;
  name: string;
  sku: string | null;
  barcode: string | null;
  attributes: Record<string, string>;
  price_override: number | null;
  cost_price_override: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProductVariantCreate {
  name: string;
  sku?: string;
  attributes?: Record<string, string>;
  price_override?: number | null;
  cost_price_override?: number | null;
}

export interface ProductVariantUpdate {
  name?: string;
  sku?: string;
  attributes?: Record<string, string>;
  price_override?: number | null;
  cost_price_override?: number | null;
  is_active?: boolean;
}

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
  has_variants?: boolean;
  variants?: ProductVariant[];
}

export interface Category {
  id: string;
  name: string;
  description?: string;
  parent_id?: string | null;
  default_margin_pct?: number | null;
  children?: Category[];
}

export interface CategoryCreate {
  name: string;
  description?: string;
  parent_id?: string | null;
  default_margin_pct?: number | null;
}

export interface CategoryUpdate {
  name?: string;
  description?: string | null;
  default_margin_pct?: number | null;
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
  has_variants?: boolean;
}

export interface BulkUploadResult {
  total_rows: number;
  successful: number;
  failed: number;
  errors: { row: number; error: string }[];
  created_ids: string[];
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

  private allCache$: Observable<Product[]> | null = null;
  private categoriesCache$: Observable<Category[]> | null = null;

  private invalidateCache(): void {
    this.allCache$ = null;
    this.categoriesCache$ = null;
  }

  getAll(): Observable<Product[]> {
    if (!this.allCache$) {
      this.allCache$ = this.api
        .get<ProductListResponse>('/products', { page_size: '100', page: '1' })
        .pipe(
          switchMap((first) => {
            const items = first.items ?? [];
            const total = first.total ?? items.length;
            if (total <= 100) return [items];
            const pageCount = Math.ceil(total / 100);
            const rest$ = Array.from({ length: pageCount - 1 }, (_, i) =>
              this.api
                .get<ProductListResponse>('/products', { page_size: '100', page: String(i + 2) })
                .pipe(map((r) => r.items ?? [])),
            );
            return forkJoin(rest$).pipe(map((pages) => [...items, ...pages.flat()]));
          }),
          shareReplay(1),
        );
    }
    return this.allCache$;
  }

  getById(id: string): Observable<Product> {
    return this.api.get<Product>(`/products/${id}`);
  }

  getCategories(): Observable<Category[]> {
    if (!this.categoriesCache$) {
      this.categoriesCache$ = this.api
        .get<Category[]>('/products/categories')
        .pipe(shareReplay(1));
    }
    return this.categoriesCache$;
  }

  createCategory(body: CategoryCreate): Observable<Category> {
    return this.api.post<Category>('/products/categories', body).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  deleteCategory(id: string): Observable<void> {
    return this.api.delete<void>(`/products/categories/${id}`).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  updateCategory(id: string, body: CategoryUpdate): Observable<Category> {
    return this.api.patch<Category>(`/products/categories/${id}`, body).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  create(body: ProductCreate): Observable<Product> {
    return this.api.post<Product>('/products', body).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  update(id: string, body: ProductUpdate): Observable<Product> {
    return this.api.put<Product>(`/products/${id}`, body).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  delete(id: string): Observable<void> {
    return this.api.delete<void>(`/products/${id}`).pipe(
      tap(() => this.invalidateCache()),
    );
  }

  bulkUpload(file: File): Observable<BulkUploadResult> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<BulkUploadResult>(`${this.baseUrl}/products/bulk-upload`, formData);
  }

  uploadImage(id: string, file: File): Observable<Product> {
    const formData = new FormData();
    formData.append('file', file);
    return this.http.post<Product>(`${this.baseUrl}/products/${id}/image`, formData);
  }

  getVariants(productId: string): Observable<ProductVariant[]> {
    return this.api.get<ProductVariant[]>(`/products/${productId}/variants`);
  }

  createVariant(productId: string, body: ProductVariantCreate): Observable<ProductVariant> {
    return this.api.post<ProductVariant>(`/products/${productId}/variants`, body).pipe(
      tap(() => { this.allCache$ = null; })
    );
  }

  updateVariant(productId: string, variantId: string, body: ProductVariantUpdate): Observable<ProductVariant> {
    return this.api.put<ProductVariant>(`/products/${productId}/variants/${variantId}`, body).pipe(
      tap(() => { this.allCache$ = null; })
    );
  }

  deleteVariant(productId: string, variantId: string): Observable<void> {
    return this.api.delete<void>(`/products/${productId}/variants/${variantId}`).pipe(
      tap(() => { this.allCache$ = null; })
    );
  }
}
