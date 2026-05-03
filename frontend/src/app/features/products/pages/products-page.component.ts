import { Component, ChangeDetectionStrategy, inject, signal, OnInit, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  ProductsService,
  Product,
  Category,
  CategoryCreate,
  ProductCreate,
  ProductUpdate,
  BulkUploadResult,
} from '../../../core/services/products.service';
import { InventoryService } from '../../../core/services/inventory.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { AlertBannerComponent } from '../../../shared/components/alert-banner/alert-banner.component';

type ProductsTab = 'products' | 'stock-report' | 'add' | 'upload' | 'categories';
type SortDir = 'asc' | 'desc';

interface ColVisibility {
  sku: boolean;
  category: boolean;
  unit_cost: boolean;
  selling_price: boolean;
  stock: boolean;
}

interface ColEntry {
  key: keyof ColVisibility;
  label: string;
  visible: boolean;
}

@Component({
  selector: 'app-products-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, Toast, Dialog, ConfirmDialogComponent, AlertBannerComponent],
  template: `
    <p-toast />

    <!-- Backdrops for floating menus -->
    @if (openActionId()) {
      <div class="fixed inset-0 z-[5]" (click)="closeActionMenu()"></div>
    }
    @if (showColMenu()) {
      <div class="fixed inset-0 z-[5]" (click)="showColMenu.set(false)"></div>
    }

    <!-- Fixed-position action menu (escapes overflow:auto clipping) -->
    @if (openActionId() && actionMenuPos()) {
      <div
        role="menu"
        class="fixed z-[20] w-44 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
        [style.top.px]="actionMenuPos()!.top"
        [style.right.px]="actionMenuPos()!.right"
      >
        <button
          role="menuitem"
          title="Edit product"
          (click)="openEditFromMenu()"
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text hover:bg-gray-50"
        >
          <i class="pi pi-pencil text-xs text-secondary"></i> Edit
        </button>
        <button
          role="menuitem"
          title="Toggle active"
          (click)="toggleActivateFromMenu()"
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text hover:bg-gray-50"
        >
          <i class="pi pi-power-off text-xs text-muted"></i>
          {{ menuProduct()?.is_active ? 'Deactivate' : 'Activate' }}
        </button>
        <div class="my-1 border-t border-gray-100"></div>
        <button
          role="menuitem"
          title="Delete product"
          (click)="confirmDeleteFromMenu()"
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-red-500 hover:bg-red-50"
        >
          <i class="pi pi-trash text-xs"></i> Delete
        </button>
      </div>
    }

    <!-- Page Header -->
    <div class="mb-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-text">Products</h2>
          <p class="mt-1 text-sm text-muted">Manage your product catalog and categories</p>
        </div>
        <button
          (click)="activeTab.set('add')"
          class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
        >
          <i class="pi pi-plus text-sm"></i> New Product
        </button>
      </div>

      <!-- Tabs -->
      <div class="mt-4 flex gap-1 border-b border-gray-200">
        <button
          (click)="activeTab.set('products')"
          [class]="activeTab() === 'products' ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-box mr-1.5 text-xs"></i> All Products
          <span class="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted">{{ products().length }}</span>
        </button>
        <button
          (click)="activeTab.set('stock-report')"
          [class]="activeTab() === 'stock-report' ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-chart-bar mr-1.5 text-xs"></i> Stock Report
        </button>
        <button
          (click)="activeTab.set('add')"
          [class]="activeTab() === 'add' ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-plus-circle mr-1.5 text-xs"></i> Add Product
        </button>
        <button
          (click)="activeTab.set('upload')"
          [class]="activeTab() === 'upload' ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-upload mr-1.5 text-xs"></i> Bulk Upload
        </button>
        <button
          (click)="activeTab.set('categories')"
          [class]="activeTab() === 'categories' ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-tag mr-1.5 text-xs"></i> Categories
          <span class="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted">{{ categories().length }}</span>
        </button>
      </div>
    </div>

    <!-- ── ALL PRODUCTS TAB ──────────────────────────────────────────────── -->
    @if (activeTab() === 'products') {

      <!-- Filter toggle -->
      <div class="mb-3 flex items-center gap-3">
        <button
          (click)="showFilters.update(v => !v)"
          class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
        >
          <i class="pi pi-filter text-xs"></i> Filters
          @if (filterCategoryId() || filterStatus()) {
            <span class="ml-0.5 h-1.5 w-1.5 rounded-full bg-primary"></span>
          }
        </button>
        @if (filterCategoryId() || filterStatus() || searchQuery()) {
          <button (click)="resetFilters()" class="flex items-center gap-1 text-xs text-muted hover:text-danger">
            <i class="pi pi-times text-[10px]"></i> Clear filters
          </button>
        }
      </div>

      <!-- Filter panel -->
      @if (showFilters()) {
        <div class="mb-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div class="flex flex-wrap gap-4">
            <div class="min-w-[160px] flex-1">
              <label for="products-filter-category" class="mb-1 block text-xs font-medium text-muted">Category</label>
              <select
                id="products-filter-category"
                [ngModel]="filterCategoryId()"
                (ngModelChange)="filterCategoryId.set($event); currentPage.set(1)"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">All categories</option>
                @for (cat of categories(); track cat.id) {
                  <option [value]="cat.id">{{ cat.name }}</option>
                }
              </select>
            </div>
            <div class="w-40">
              <label for="products-filter-status" class="mb-1 block text-xs font-medium text-muted">Status</label>
              <select
                id="products-filter-status"
                [ngModel]="filterStatus()"
                (ngModelChange)="filterStatus.set($event); currentPage.set(1)"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">All statuses</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
        </div>
      }

      <!-- Toolbar -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2 text-sm text-muted">
          Show
          <select
            [ngModel]="pageSize()"
            (ngModelChange)="pageSize.set(+$event); currentPage.set(1)"
            class="rounded-lg border border-gray-300 py-1 pl-3 pr-7 text-sm focus:border-primary focus:outline-none"
          >
            <option [value]="25">25</option>
            <option [value]="50">50</option>
            <option [value]="100">100</option>
          </select>
          entries
        </div>

        <div class="ml-auto flex items-center gap-2">
          <!-- Export CSV -->
          <button
            (click)="exportCsv()"
            class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
          >
            <i class="pi pi-download text-xs"></i> Export CSV
          </button>

          <!-- Column visibility -->
          <div class="relative">
            <button
              (click)="showColMenu.update(v => !v)"
              class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
            >
              <i class="pi pi-table text-xs"></i> Columns
            </button>
            @if (showColMenu()) {
              <div class="absolute right-0 top-full z-[10] mt-1 w-44 rounded-lg border border-gray-200 bg-white py-2 shadow-lg">
                <p class="px-3 py-1 text-xs font-semibold uppercase tracking-wider text-muted">Toggle Columns</p>
                @for (entry of colEntries(); track entry.key) {
                  <label class="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-gray-50">
                    <input
                      type="checkbox"
                      [checked]="entry.visible"
                      (change)="toggleCol(entry.key)"
                      class="h-3.5 w-3.5 rounded border-gray-300 text-primary"
                    />
                    <span class="text-sm text-text">{{ entry.label }}</span>
                  </label>
                }
              </div>
            }
          </div>

          <!-- View toggle -->
          <div class="flex items-center rounded-lg border border-gray-200 bg-white p-0.5">
            <button
              (click)="viewMode.set('grid')"
              [class]="viewMode() === 'grid' ? 'rounded-md bg-primary px-3 py-1.5 text-white' : 'rounded-md px-3 py-1.5 text-muted hover:text-text'"
              title="Grid view"
            >
              <i class="pi pi-th-large text-sm"></i>
            </button>
            <button
              (click)="viewMode.set('list')"
              [class]="viewMode() === 'list' ? 'rounded-md bg-primary px-3 py-1.5 text-white' : 'rounded-md px-3 py-1.5 text-muted hover:text-text'"
              title="List view"
            >
              <i class="pi pi-list text-sm"></i>
            </button>
          </div>

          <!-- Search -->
          <div class="relative">
            <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted"></i>
            <input
              type="text"
              [ngModel]="searchQuery()"
              (ngModelChange)="searchQuery.set($event); currentPage.set(1)"
              placeholder="Search products..."
              class="w-52 rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>
      </div>

      <!-- LIST VIEW -->
      @if (viewMode() === 'list') {
        <div class="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table class="min-w-full text-sm">
            <caption class="sr-only">Product catalog</caption>
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <th
                  (click)="toggleSort('name')"
                  class="cursor-pointer whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted hover:text-text"
                >
                  <span class="inline-flex items-center gap-1">Name <i [class]="sortIcon('name')"></i></span>
                </th>
                @if (visibleCols().sku) {
                  <th
                    (click)="toggleSort('sku')"
                    class="cursor-pointer whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted hover:text-text"
                  >
                    <span class="inline-flex items-center gap-1">SKU <i [class]="sortIcon('sku')"></i></span>
                  </th>
                }
                @if (visibleCols().category) {
                  <th
                    (click)="toggleSort('category')"
                    class="cursor-pointer whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted hover:text-text"
                  >
                    <span class="inline-flex items-center gap-1">Category <i [class]="sortIcon('category')"></i></span>
                  </th>
                }
                @if (visibleCols().unit_cost) {
                  <th
                    (click)="toggleSort('unit_cost')"
                    class="cursor-pointer whitespace-nowrap px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted hover:text-text"
                  >
                    <span class="inline-flex items-center justify-end gap-1">Unit Cost <i [class]="sortIcon('unit_cost')"></i></span>
                  </th>
                }
                @if (visibleCols().selling_price) {
                  <th
                    (click)="toggleSort('selling_price')"
                    class="cursor-pointer whitespace-nowrap px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted hover:text-text"
                  >
                    <span class="inline-flex items-center justify-end gap-1">Price <i [class]="sortIcon('selling_price')"></i></span>
                  </th>
                }
                @if (visibleCols().stock) {
                  <th
                    (click)="toggleSort('stock')"
                    class="cursor-pointer whitespace-nowrap px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted hover:text-text"
                  >
                    <span class="inline-flex items-center justify-end gap-1">Stock <i [class]="sortIcon('stock')"></i></span>
                  </th>
                }
                <th class="whitespace-nowrap px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (product of pagedProducts(); track product.id) {
                <tr class="transition-colors hover:bg-gray-50">
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-3">
                      <div class="h-8 w-8 flex-shrink-0 overflow-hidden rounded-lg bg-gray-100">
                        @if (product.image_url) {
                          <img [src]="'http://localhost:8000' + product.image_url" [alt]="product.name" class="h-full w-full object-cover" />
                        } @else {
                          <div class="flex h-full w-full items-center justify-center">
                            <i class="pi pi-image text-xs text-gray-300"></i>
                          </div>
                        }
                      </div>
                      <span class="font-medium text-text">{{ product.name }}</span>
                    </div>
                  </td>
                  @if (visibleCols().sku) {
                    <td class="px-4 py-3 font-mono text-xs text-muted">{{ product.sku }}</td>
                  }
                  @if (visibleCols().category) {
                    <td class="px-4 py-3 text-muted">{{ categoryName(product.category_id) || '—' }}</td>
                  }
                  @if (visibleCols().unit_cost) {
                    <td class="px-4 py-3 text-right text-text">{{ product.unit_cost | number: '1.2-2' }}</td>
                  }
                  @if (visibleCols().selling_price) {
                    <td class="px-4 py-3 text-right font-semibold text-secondary">{{ product.selling_price | number: '1.2-2' }}</td>
                  }
                  @if (visibleCols().stock) {
                    <td class="px-4 py-3 text-right">
                      <span [class]="stockStatus(product.id) === 'out' ? 'font-semibold text-red-600' : stockStatus(product.id) === 'low' ? 'font-semibold text-amber-600' : 'text-text'">
                        {{ stockMap().get(product.id) ?? 0 }}
                      </span>
                    </td>
                  }
                  <td class="px-4 py-3 text-right">
                    <button
                      (click)="toggleActionMenu(product.id, $event)"
                      [attr.aria-expanded]="openActionId() === product.id"
                      aria-haspopup="true"
                      class="rounded-lg p-1.5 text-muted hover:bg-gray-100"
                    >
                      <i class="pi pi-ellipsis-v text-sm"></i>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8" class="py-16 text-center text-muted">
                    <i class="pi pi-box mb-3 block text-4xl text-gray-300"></i>
                    No products found.
                    @if (searchQuery() || filterCategoryId() || filterStatus()) {
                      <button (click)="resetFilters()" class="mt-2 block mx-auto text-primary hover:underline">
                        Clear filters
                      </button>
                    } @else {
                      <button (click)="activeTab.set('add')" class="mt-2 block mx-auto text-primary hover:underline">
                        Add your first product
                      </button>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        @if (filteredProducts().length > 0) {
          <div class="mt-4 flex items-center justify-between text-sm text-muted">
            <span>
              Showing {{ showingFrom() }}–{{ showingTo() }} of {{ filteredProducts().length }} products
              @if (selectedIds().size > 0) {
                · <span class="font-medium text-primary">{{ selectedIds().size }} selected</span>
              }
            </span>
            <div class="flex items-center gap-1">
              <button
                (click)="prevPage()"
                [disabled]="currentPage() === 1"
                class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
              >
                <i class="pi pi-chevron-left text-xs"></i>
              </button>
              @for (n of pageNumbers(); track n) {
                <button
                  (click)="goToPage(n)"
                  [class]="n === currentPage() ? 'rounded bg-primary px-2.5 py-1 text-xs font-semibold text-white' : 'rounded px-2.5 py-1 text-xs hover:bg-gray-100'"
                >
                  {{ n }}
                </button>
              }
              <button
                (click)="nextPage()"
                [disabled]="currentPage() === totalPages()"
                class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
              >
                <i class="pi pi-chevron-right text-xs"></i>
              </button>
            </div>
          </div>
        }
      }

      <!-- GRID VIEW -->
      @if (viewMode() === 'grid') {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          @for (product of pagedProducts(); track product.id) {
            <div class="rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition-all hover:shadow-md">
              <div class="mb-3 flex h-32 items-center justify-center overflow-hidden rounded-lg bg-gray-100">
                @if (product.image_url) {
                  <img [src]="'http://localhost:8000' + product.image_url" [alt]="product.name" class="h-full w-full object-cover" />
                } @else {
                  <i class="pi pi-image text-3xl text-gray-300"></i>
                }
              </div>
              <div class="space-y-1">
                <div class="flex items-start justify-between gap-2">
                  <p class="font-semibold text-text">{{ product.name }}</p>
                  <span [class]="product.is_active ? 'rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700' : 'rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500'">
                    {{ product.is_active ? 'Active' : 'Inactive' }}
                  </span>
                </div>
                <p class="text-xs text-muted">SKU: {{ product.sku }}</p>
                @if (categoryName(product.category_id)) {
                  <p class="text-xs text-muted"><i class="pi pi-tag mr-1 text-[10px]"></i>{{ categoryName(product.category_id) }}</p>
                }
                <div class="mt-2 grid grid-cols-2 gap-1 text-xs">
                  <div>
                    <p class="text-muted">Cost</p>
                    <p class="font-semibold text-text">{{ product.unit_cost | number: '1.2-2' }}</p>
                  </div>
                  <div>
                    <p class="text-muted">Price</p>
                    <p class="font-semibold text-secondary">{{ product.selling_price | number: '1.2-2' }}</p>
                  </div>
                </div>
                <p class="text-xs text-muted">Stock: <span [class]="stockStatus(product.id) === 'out' ? 'font-semibold text-red-600' : stockStatus(product.id) === 'low' ? 'font-semibold text-amber-600' : 'font-semibold text-text'">{{ stockMap().get(product.id) ?? 0 }}</span></p>
              </div>
              <div class="mt-3 flex gap-2 border-t border-gray-100 pt-3">
                <button (click)="openEdit(product)" class="flex-1 rounded-lg px-3 py-1.5 text-xs font-medium text-secondary transition-colors hover:bg-blue-50">
                  <i class="pi pi-pencil mr-1 text-[10px]"></i> Edit
                </button>
                <button (click)="confirmDelete(product)" class="flex-1 rounded-lg px-3 py-1.5 text-xs font-medium text-red-500 transition-colors hover:bg-red-50">
                  <i class="pi pi-trash mr-1 text-[10px]"></i> Delete
                </button>
              </div>
            </div>
          } @empty {
            <div class="col-span-full py-16 text-center">
              <i class="pi pi-box mb-3 block text-4xl text-gray-300"></i>
              <p class="text-muted">No products yet.</p>
            </div>
          }
        </div>
        @if (filteredProducts().length > pageSize()) {
          <div class="mt-4 flex items-center justify-between text-sm text-muted">
            <span>Showing {{ showingFrom() }}–{{ showingTo() }} of {{ filteredProducts().length }}</span>
            <div class="flex items-center gap-1">
              <button (click)="prevPage()" [disabled]="currentPage() === 1" class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"><i class="pi pi-chevron-left text-xs"></i></button>
              @for (n of pageNumbers(); track n) {
                <button (click)="goToPage(n)" [class]="n === currentPage() ? 'rounded bg-primary px-2.5 py-1 text-xs font-semibold text-white' : 'rounded px-2.5 py-1 text-xs hover:bg-gray-100'">{{ n }}</button>
              }
              <button (click)="nextPage()" [disabled]="currentPage() === totalPages()" class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"><i class="pi pi-chevron-right text-xs"></i></button>
            </div>
          </div>
        }
      }
    }

    <!-- ── STOCK REPORT TAB ────────────────────────────────────────────────── -->
    @if (activeTab() === 'stock-report') {
      <div class="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
        <table class="min-w-full text-sm">
          <caption class="sr-only">Stock report</caption>
          <thead>
            <tr class="border-b border-gray-200 bg-gray-50">
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Product</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">SKU</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">Unit Cost</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">Selling Price</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">Stock</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">Margin %</th>
              <th class="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-muted">Stock Status</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            @for (product of products(); track product.id) {
              <tr class="transition-colors hover:bg-gray-50">
                <td class="px-4 py-3 font-medium text-text">{{ product.name }}</td>
                <td class="px-4 py-3 font-mono text-xs text-muted">{{ product.sku }}</td>
                <td class="px-4 py-3 text-right text-text">{{ product.unit_cost | number: '1.2-2' }}</td>
                <td class="px-4 py-3 text-right font-semibold text-secondary">{{ product.selling_price | number: '1.2-2' }}</td>
                <td class="px-4 py-3 text-right text-text">{{ stockMap().get(product.id) ?? 0 }}</td>
                <td class="px-4 py-3 text-right">
                  <span [class]="margin(product) >= 30 ? 'font-semibold text-green-600' : margin(product) >= 15 ? 'font-semibold text-amber-600' : 'font-semibold text-red-500'">
                    {{ margin(product) | number: '1.0-1' }}%
                  </span>
                </td>
                <td class="px-4 py-3 text-center">
                  @if (stockStatus(product.id) === 'out') {
                    <span class="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700">Out of Stock</span>
                  } @else if (stockStatus(product.id) === 'low') {
                    <span class="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">Low Stock</span>
                  } @else {
                    <span class="rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-700">In Stock</span>
                  }
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="7" class="py-12 text-center text-muted">No products to report.</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }

    <!-- ── ADD PRODUCT TAB ────────────────────────────────────────────────── -->
    @if (activeTab() === 'add') {
      <div id="add-product-form" class="mx-auto max-w-lg rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-plus text-sm text-secondary"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Add New Product</h3>
        </div>

        <div class="space-y-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Name *</label>
            <input
              [(ngModel)]="addForm.name"
              placeholder="Product name"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <div class="mb-1.5 flex items-baseline justify-between">
              <label class="text-xs font-medium text-muted">Category</label>
              <button
                type="button"
                (click)="showInlineCategoryForm = !showInlineCategoryForm; inlineCategoryName = ''"
                class="inline-flex items-center gap-1 border-0 bg-transparent p-0 text-xs font-medium text-primary hover:text-primary/70 focus:outline-none"
              >
                @if (showInlineCategoryForm) {
                  <i class="pi pi-times text-[10px]"></i><span>Cancel</span>
                } @else {
                  <i class="pi pi-plus text-[10px]"></i><span>New category</span>
                }
              </button>
            </div>

            @if (!showInlineCategoryForm) {
              <select
                id="add-cat-select"
                [(ngModel)]="addForm.category_id"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="">-- None --</option>
                @for (cat of categories(); track cat.id) {
                  <option [value]="cat.id">{{ cat.name }}</option>
                }
              </select>
            }

            @if (showInlineCategoryForm) {
              <div class="flex gap-2">
                <input
                  [(ngModel)]="inlineCategoryName"
                  placeholder="Category name"
                  class="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  (keydown.enter)="submitInlineCategory()"
                  (keydown.escape)="showInlineCategoryForm = false"
                />
                <button
                  type="button"
                  title="Save category"
                  (click)="submitInlineCategory()"
                  [disabled]="savingInlineCategory() || !inlineCategoryName.trim()"
                  class="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
                >
                  @if (savingInlineCategory()) {
                    <i class="pi pi-spinner pi-spin text-xs"></i>
                  } @else {
                    <i class="pi pi-check text-xs"></i>
                  }
                  Create
                </button>
              </div>
              <p class="mt-1 text-xs text-muted">Press Enter to save, Escape to cancel.</p>
            }
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Unit Cost *</label>
              <input
                type="number"
                [(ngModel)]="addForm.unit_cost"
                min="0"
                step="0.01"
                placeholder="0.00"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Selling Price *</label>
              <input
                type="number"
                [(ngModel)]="addForm.selling_price"
                min="0"
                step="0.01"
                placeholder="0.00"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
          @if (addFormMargin !== null) {
            <p
              data-testid="add-margin"
              class="text-xs font-medium"
              [class.text-green-600]="addFormMargin >= 0"
              [class.text-red-500]="addFormMargin < 0"
            >
              Margin: {{ addFormMargin | number: '1.1-1' }}%
            </p>
          }

          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Description</label>
            <textarea
              [(ngModel)]="addForm.description"
              rows="2"
              placeholder="Optional description"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            ></textarea>
          </div>

          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Product Image</label>
            <input
              type="file"
              accept="image/*"
              (change)="onAddFileChange($event)"
              class="w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-primary/10 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary"
            />
          </div>

          <div class="flex gap-3 pt-2">
            <button
              type="button"
              (click)="cancelAdd()"
              class="rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-muted hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              (click)="submitAdd()"
              [disabled]="savingAdd()"
              class="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
            >
              @if (savingAdd()) {
                <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
              } @else {
                <i class="pi pi-check text-sm"></i> Create Product
              }
            </button>
          </div>
        </div>
      </div>
    }

    <!-- ── BULK UPLOAD TAB ────────────────────────────────────────────────── -->
    @if (activeTab() === 'upload') {
      <div class="mx-auto max-w-2xl">
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-upload text-sm text-secondary"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Bulk Upload Products</h3>
          </div>

          <div class="mb-6 rounded-lg border border-blue-100 bg-blue-50/50 p-4">
            <p class="mb-2 text-sm font-medium text-text">Required columns</p>
            <div class="flex flex-wrap gap-2">
              <span class="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">name</span>
              <span class="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">unit_cost</span>
              <span class="rounded-full bg-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-700">selling_price</span>
            </div>
            <p class="mt-2 text-sm font-medium text-text">Optional columns</p>
            <div class="flex flex-wrap gap-2">
              <span class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-muted">sku</span>
              <span class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-muted">description</span>
              <span class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-muted">category</span>
              <span class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-muted">currency</span>
            </div>
          </div>

          <button
            (click)="downloadBulkTemplate()"
            class="mb-5 flex items-center gap-2 text-sm font-medium text-secondary transition-colors hover:text-primary hover:underline"
          >
            <i class="pi pi-download text-xs"></i> Download CSV template
          </button>

          <div
            class="mb-5 flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 p-8 transition-colors"
            [class.border-primary]="bulkFile"
            [class.bg-primary/5]="bulkFile"
          >
            @if (!bulkFile) {
              <i class="pi pi-cloud-upload mb-2 text-3xl text-gray-300"></i>
              <p class="mb-1 text-sm text-muted">Choose a CSV or Excel file</p>
              <p class="mb-3 text-xs text-gray-400">.csv, .xlsx, or .xls</p>
            } @else {
              <i class="pi pi-file mb-2 text-3xl text-primary"></i>
              <p class="text-sm font-medium text-text">{{ bulkFile.name }}</p>
              <p class="text-xs text-muted">{{ (bulkFile.size / 1024).toFixed(1) }} KB</p>
            }
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              (change)="onBulkFileChange($event)"
              class="mt-3 text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-primary/10 file:px-4 file:py-2 file:text-sm file:font-medium file:text-primary"
            />
          </div>

          <button
            (click)="submitBulkUpload()"
            [disabled]="!bulkFile || uploadingBulk()"
            class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
          >
            @if (uploadingBulk()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Uploading...
            } @else {
              <i class="pi pi-upload text-sm"></i> Upload Products
            }
          </button>

          @if (bulkResult()) {
            <div class="mt-5 rounded-lg border p-4" [class]="bulkResult()!.failed ? 'border-amber-200 bg-amber-50' : 'border-green-200 bg-green-50'">
              <p class="text-sm font-semibold" [class]="bulkResult()!.failed ? 'text-amber-700' : 'text-green-700'">
                {{ bulkResult()!.successful }} of {{ bulkResult()!.total_rows }} products created
                @if (bulkResult()!.failed) {
                  &mdash; {{ bulkResult()!.failed }} failed
                }
              </p>
              @if (bulkResult()!.errors.length) {
                <ul class="mt-2 space-y-1">
                  @for (err of bulkResult()!.errors; track err.row) {
                    <li class="text-xs text-red-600">Row {{ err.row }}: {{ err.error }}</li>
                  }
                </ul>
              }
            </div>
          }
        </div>
      </div>
    }

    <!-- ── CATEGORIES TAB ──────────────────────────────────────────────────── -->
    @if (activeTab() === 'categories') {
      <div class="space-y-6">
        <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h3 class="mb-4 text-sm font-semibold text-text">Add New Category</h3>
          <div class="flex gap-3">
            <input
              [(ngModel)]="newCategoryName"
              placeholder="Category name"
              class="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              (keydown.enter)="submitCreateCategory()"
            />
            <input
              [(ngModel)]="newCategoryDescription"
              placeholder="Description (optional)"
              class="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              (keydown.enter)="submitCreateCategory()"
            />
            <button
              (click)="submitCreateCategory()"
              [disabled]="savingCategory() || !newCategoryName.trim()"
              class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
            >
              @if (savingCategory()) {
                <i class="pi pi-spinner pi-spin text-sm"></i>
              } @else {
                <i class="pi pi-plus text-sm"></i>
              }
              Add Category
            </button>
          </div>
        </div>

        @if (categoryPendingDelete()) {
          <app-alert-banner
            severity="danger"
            [message]="'Delete category &quot;' + categoryPendingDelete()!.name + '&quot;? Products will become uncategorised.'"
            confirmLabel="Delete"
            (confirmed)="executeDeleteCategory()"
            (dismissed)="categoryPendingDelete.set(null)"
          />
        }

        <div class="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Name</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Description</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Products</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (cat of categories(); track cat.id) {
                <tr class="transition-colors hover:bg-gray-50">
                  <td class="px-4 py-3 font-medium text-text">{{ cat.name }}</td>
                  <td class="px-4 py-3 text-muted">{{ cat.description || '—' }}</td>
                  <td class="px-4 py-3 text-muted">{{ productCountForCategory(cat.id) }}</td>
                  <td class="px-4 py-3 text-right">
                    <button (click)="confirmDeleteCategory(cat)" class="rounded-lg p-1.5 text-red-400 hover:bg-red-50" title="Delete category">
                      <i class="pi pi-trash text-xs"></i>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="4" class="py-12 text-center text-muted">No categories yet. Add your first category above.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    }

    <!-- ── EDIT PRODUCT DIALOG ─────────────────────────────────────────────── -->
    <p-dialog
      header="Edit Product"
      [visible]="showEdit"
      (visibleChange)="showEdit = $event"
      [modal]="true"
      [style]="{ width: '480px' }"
    >
      <div class="space-y-4 pt-2">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Name</label>
          <input
            [(ngModel)]="editForm.name"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Category</label>
          <select
            [(ngModel)]="editForm.category_id"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">-- None --</option>
            @for (cat of categories(); track cat.id) {
              <option [value]="cat.id">{{ cat.name }}</option>
            }
          </select>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Unit Cost</label>
            <input
              type="number"
              [(ngModel)]="editForm.unit_cost"
              min="0"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Selling Price</label>
            <input
              type="number"
              [(ngModel)]="editForm.selling_price"
              min="0"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>
        @if (editFormMargin !== null) {
          <p
            data-testid="edit-margin"
            class="text-xs font-medium"
            [class.text-green-600]="editFormMargin >= 0"
            [class.text-red-500]="editFormMargin < 0"
          >
            Margin: {{ editFormMargin | number: '1.1-1' }}%
          </p>
        }
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Description</label>
          <textarea
            [(ngModel)]="editForm.description"
            rows="2"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          ></textarea>
        </div>
        <div class="flex items-center gap-2">
          <input
            type="checkbox"
            id="editActive"
            [(ngModel)]="editForm.is_active"
            class="h-4 w-4 rounded border-gray-300 text-primary"
          />
          <label for="editActive" class="text-sm font-medium text-text">Active</label>
        </div>
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Replace Image</label>
          <input
            type="file"
            accept="image/*"
            (change)="onEditFileChange($event)"
            class="w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-primary/10 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary"
          />
        </div>
        <button
          (click)="submitEdit()"
          [disabled]="saving()"
          class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
        >
          @if (saving()) {
            <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
          } @else {
            <i class="pi pi-check text-sm"></i> Save Changes
          }
        </button>
      </div>
    </p-dialog>

    <!-- ── CONFIRM DELETE PRODUCT DIALOG ────────────────────────────────────── -->
    <app-confirm-dialog
      [visible]="!!productPendingDelete()"
      header="Delete Product"
      [message]="'Delete &quot;' + (productPendingDelete()?.name ?? '') + '&quot;? This action cannot be undone.'"
      (confirmed)="executeDeleteProduct()"
      (cancelled)="productPendingDelete.set(null)"
    />
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductsPageComponent implements OnInit {
  private readonly productsService = inject(ProductsService);
  private readonly inventoryService = inject(InventoryService);
  private readonly messageService = inject(MessageService);

  // ── Shared state ──────────────────────────────────────────────────────────
  products = signal<Product[]>([]);
  categories = signal<Category[]>([]);
  saving = signal(false);
  savingAdd = signal(false);

  // ── Tab & view ────────────────────────────────────────────────────────────
  activeTab = signal<ProductsTab>('products');
  viewMode = signal<'grid' | 'list'>('list');

  // ── Stock data ────────────────────────────────────────────────────────────
  stockMap = signal<Map<string, number>>(new Map());
  thresholdMap = signal<Map<string, number>>(new Map());

  // ── Filters & search ──────────────────────────────────────────────────────
  filterCategoryId = signal('');
  filterStatus = signal<'' | 'active' | 'inactive'>('');
  searchQuery = signal('');
  showFilters = signal(false);

  // ── Sort ──────────────────────────────────────────────────────────────────
  sortCol = signal('name');
  sortDir = signal<SortDir>('asc');

  // ── Pagination ────────────────────────────────────────────────────────────
  pageSize = signal(25);
  currentPage = signal(1);

  // ── Column visibility & menus ─────────────────────────────────────────────
  showColMenu = signal(false);
  visibleCols = signal<ColVisibility>({
    sku: true, category: true, unit_cost: true, selling_price: true, stock: true,
  });

  // ── Selection ─────────────────────────────────────────────────────────────
  selectedIds = signal<Set<string>>(new Set());

  // ── Actions dropdown ──────────────────────────────────────────────────────
  openActionId = signal<string | null>(null);
  actionMenuPos = signal<{ top: number; right: number } | null>(null);
  menuProduct = computed(() => this.products().find((p) => p.id === this.openActionId()) ?? null);

  // ── Edit dialog ───────────────────────────────────────────────────────────
  showEdit = false;
  editTarget = signal<Product | null>(null);

  // ── Confirm delete dialogs ────────────────────────────────────────────────
  categoryPendingDelete = signal<Category | null>(null);
  productPendingDelete = signal<Product | null>(null);
  editForm: ProductUpdate & { category_id: string; is_active: boolean } = {
    name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '', is_active: true,
  };
  editFile: File | null = null;

  // ── Add Product tab form ──────────────────────────────────────────────────
  addForm: ProductCreate & { category_id: string } = {
    name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '',
  };
  addFile: File | null = null;

  // ── Inline category (in Add tab) ──────────────────────────────────────────
  showInlineCategoryForm = false;
  inlineCategoryName = '';
  savingInlineCategory = signal(false);

  // ── Bulk upload tab ───────────────────────────────────────────────────────
  bulkFile: File | null = null;
  uploadingBulk = signal(false);
  bulkResult = signal<BulkUploadResult | null>(null);

  // ── Categories tab ────────────────────────────────────────────────────────
  newCategoryName = '';
  newCategoryDescription = '';
  savingCategory = signal(false);

  // ── Computed ──────────────────────────────────────────────────────────────
  filteredProducts = computed(() => {
    let items = this.products();
    const catFilter = this.filterCategoryId();
    if (catFilter) items = items.filter((p) => p.category_id === catFilter);
    const statusFilter = this.filterStatus();
    if (statusFilter === 'active') items = items.filter((p) => p.is_active);
    else if (statusFilter === 'inactive') items = items.filter((p) => !p.is_active);
    const q = this.searchQuery().toLowerCase().trim();
    if (q) items = items.filter((p) => p.name.toLowerCase().includes(q) || (p.sku ?? '').toLowerCase().includes(q));
    const col = this.sortCol();
    const dir = this.sortDir() === 'asc' ? 1 : -1;
    return [...items].sort((a, b) => {
      let av: string | number, bv: string | number;
      switch (col) {
        case 'sku': av = a.sku ?? ''; bv = b.sku ?? ''; break;
        case 'category': av = this.categoryName(a.category_id); bv = this.categoryName(b.category_id); break;
        case 'unit_cost': av = a.unit_cost; bv = b.unit_cost; break;
        case 'selling_price': av = a.selling_price; bv = b.selling_price; break;
        case 'stock': av = this.stockMap().get(a.id) ?? 0; bv = this.stockMap().get(b.id) ?? 0; break;
        default: av = a.name.toLowerCase(); bv = b.name.toLowerCase();
      }
      return av < bv ? -dir : av > bv ? dir : 0;
    });
  });

  pagedProducts = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredProducts().slice(start, start + this.pageSize());
  });

  totalPages = computed(() => Math.max(1, Math.ceil(this.filteredProducts().length / this.pageSize())));
  showingFrom = computed(() => this.filteredProducts().length === 0 ? 0 : (this.currentPage() - 1) * this.pageSize() + 1);
  showingTo = computed(() => Math.min(this.currentPage() * this.pageSize(), this.filteredProducts().length));

  pageNumbers = computed(() => {
    const total = this.totalPages();
    const current = this.currentPage();
    const start = Math.max(1, Math.min(current - 2, total - 4));
    const end = Math.min(total, start + 4);
    const pages: number[] = [];
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  });

  allSelected = computed(() => {
    const paged = this.pagedProducts();
    return paged.length > 0 && paged.every((p) => this.selectedIds().has(p.id));
  });

  colEntries = computed((): ColEntry[] => {
    const cv = this.visibleCols();
    return [
      { key: 'sku', label: 'SKU', visible: cv.sku },
      { key: 'category', label: 'Category', visible: cv.category },
      { key: 'unit_cost', label: 'Unit Cost', visible: cv.unit_cost },
      { key: 'selling_price', label: 'Selling Price', visible: cv.selling_price },
      { key: 'stock', label: 'Stock', visible: cv.stock },
    ];
  });

  // ── Lifecycle ─────────────────────────────────────────────────────────────
  ngOnInit(): void {
    this.loadProducts();
    this.productsService.getCategories().subscribe({ next: (cats) => this.categories.set(cats) });
    this.loadStock();
  }

  private loadProducts(): void {
    this.productsService.getAll().subscribe({ next: (p) => this.products.set(p) });
  }

  private loadStock(): void {
    this.inventoryService.getCurrent().subscribe({
      next: (items) => {
        const sm = new Map<string, number>();
        const tm = new Map<string, number>();
        items.forEach((item) => {
          sm.set(item.product_id, item.current_stock);
          tm.set(item.product_id, item.low_stock_threshold);
        });
        this.stockMap.set(sm);
        this.thresholdMap.set(tm);
      },
    });
  }

  // ── Helpers ───────────────────────────────────────────────────────────────
  categoryName(categoryId: string | null): string {
    if (!categoryId) return '';
    return this.categories().find((c) => c.id === categoryId)?.name ?? '';
  }

  productCountForCategory(categoryId: string): number {
    return this.products().filter((p) => p.category_id === categoryId).length;
  }

  stockStatus(productId: string): 'out' | 'low' | 'ok' {
    const qty = this.stockMap().get(productId) ?? 0;
    if (qty === 0) return 'out';
    const threshold = this.thresholdMap().get(productId) ?? 10;
    return qty <= threshold ? 'low' : 'ok';
  }

  margin(product: Product): number {
    if (!product.selling_price) return 0;
    return ((product.selling_price - product.unit_cost) / product.selling_price) * 100;
  }

  get addFormMargin(): number | null {
    const { unit_cost, selling_price } = this.addForm;
    if (!selling_price) return null;
    return ((selling_price - unit_cost) / selling_price) * 100;
  }

  get editFormMargin(): number | null {
    const cost = this.editForm.unit_cost ?? 0;
    const price = this.editForm.selling_price ?? 0;
    if (!price) return null;
    return ((price - cost) / price) * 100;
  }

  sortIcon(col: string): string {
    if (this.sortCol() !== col) return 'pi pi-sort text-[8px] opacity-30';
    return this.sortDir() === 'asc'
      ? 'pi pi-sort-up text-[8px] text-primary'
      : 'pi pi-sort-down text-[8px] text-primary';
  }

  // ── Sort / filter / pagination ────────────────────────────────────────────
  toggleSort(col: string): void {
    if (this.sortCol() === col) {
      this.sortDir.update((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      this.sortCol.set(col);
      this.sortDir.set('asc');
    }
    this.currentPage.set(1);
  }

  resetFilters(): void {
    this.filterCategoryId.set('');
    this.filterStatus.set('');
    this.searchQuery.set('');
    this.currentPage.set(1);
  }

  prevPage(): void { if (this.currentPage() > 1) this.currentPage.update((p) => p - 1); }
  nextPage(): void { if (this.currentPage() < this.totalPages()) this.currentPage.update((p) => p + 1); }
  goToPage(n: number): void { this.currentPage.set(n); }

  // ── Selection ─────────────────────────────────────────────────────────────
  toggleSelectAll(): void {
    const paged = this.pagedProducts();
    if (this.allSelected()) {
      this.selectedIds.update((s) => { const ns = new Set(s); paged.forEach((p) => ns.delete(p.id)); return ns; });
    } else {
      this.selectedIds.update((s) => { const ns = new Set(s); paged.forEach((p) => ns.add(p.id)); return ns; });
    }
  }

  toggleSelect(id: string): void {
    this.selectedIds.update((s) => {
      const ns = new Set(s);
      if (ns.has(id)) ns.delete(id); else ns.add(id);
      return ns;
    });
  }

  // ── Export ────────────────────────────────────────────────────────────────
  exportCsv(): void {
    const items = this.selectedIds().size > 0
      ? this.filteredProducts().filter((p) => this.selectedIds().has(p.id))
      : this.filteredProducts();
    const header = 'Name,SKU,Category,Unit Cost,Selling Price,Stock,Status';
    const rows = items.map((p) =>
      [p.name, p.sku, this.categoryName(p.category_id), p.unit_cost, p.selling_price, this.stockMap().get(p.id) ?? 0, p.is_active ? 'Active' : 'Inactive']
        .map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`)
        .join(',')
    );
    const csv = [header, ...rows].join('\n');
    const a = Object.assign(document.createElement('a'), {
      href: URL.createObjectURL(new Blob([csv], { type: 'text/csv' })),
      download: 'products.csv',
    });
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ── Column visibility ─────────────────────────────────────────────────────
  toggleCol(key: keyof ColVisibility): void {
    this.visibleCols.update((c) => ({ ...c, [key]: !c[key] }));
  }

  // ── Action menu helpers ───────────────────────────────────────────────────
  toggleActionMenu(productId: string, event: MouseEvent): void {
    if (this.openActionId() === productId) {
      this.closeActionMenu();
      return;
    }
    const btn = event.currentTarget as HTMLElement;
    const rect = btn.getBoundingClientRect();
    // Position below button, aligned to its right edge
    this.actionMenuPos.set({
      top: rect.bottom + 4,
      right: window.innerWidth - rect.right,
    });
    this.openActionId.set(productId);
  }

  closeActionMenu(): void {
    this.openActionId.set(null);
    this.actionMenuPos.set(null);
  }

  openEditFromMenu(): void {
    const product = this.menuProduct();
    if (product) this.openEdit(product);
    else this.closeActionMenu();
  }

  toggleActivateFromMenu(): void {
    const product = this.menuProduct();
    if (product) this.toggleActivate(product);
    else this.closeActionMenu();
  }

  confirmDeleteFromMenu(): void {
    const product = this.menuProduct();
    if (product) this.confirmDelete(product);
    else this.closeActionMenu();
  }

  // ── Product CRUD ──────────────────────────────────────────────────────────
  openEdit(product: Product): void {
    this.editTarget.set(product);
    this.editForm = {
      name: product.name,
      category_id: product.category_id ?? '',
      // parseFloat strips trailing zeros from Decimal strings (e.g. "10500.000000" → 10500)
      unit_cost: parseFloat(String(product.unit_cost)),
      selling_price: parseFloat(String(product.selling_price)),
      description: product.description ?? '',
      is_active: product.is_active,
    };
    this.editFile = null;
    this.showEdit = true;
    this.closeActionMenu();
  }

  onEditFileChange(event: Event): void {
    this.editFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  onAddFileChange(event: Event): void {
    this.addFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  cancelAdd(): void {
    this.addForm = { name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '' };
    this.addFile = null;
    this.showInlineCategoryForm = false;
    this.inlineCategoryName = '';
    this.activeTab.set('products');
  }

  submitAdd(): void {
    if (!this.addForm.name || !this.addForm.unit_cost || !this.addForm.selling_price) return;
    this.savingAdd.set(true);
    const body: ProductCreate = {
      name: this.addForm.name,
      description: this.addForm.description || undefined,
      unit_cost: this.addForm.unit_cost,
      selling_price: this.addForm.selling_price,
      category_id: this.addForm.category_id || undefined,
    };
    this.productsService.create(body).subscribe({
      next: (created) => {
        const finish = (prod: Product) => {
          this.savingAdd.set(false);
          this.addForm = { name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '' };
          this.addFile = null;
          this.showInlineCategoryForm = false;
          this.products.update((list) => [...list, prod]);
          this.messageService.add({ severity: 'success', summary: 'Created', detail: 'Product created' });
          this.activeTab.set('products');
        };
        if (this.addFile) {
          this.productsService.uploadImage(created.id, this.addFile).subscribe({
            next: finish,
            error: () => finish(created),
          });
        } else {
          finish(created);
        }
      },
      error: () => {
        this.savingAdd.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create product' });
      },
    });
  }

  submitEdit(): void {
    const target = this.editTarget();
    if (!target) return;
    this.saving.set(true);
    const body: ProductUpdate = {
      name: this.editForm.name,
      description: this.editForm.description || undefined,
      unit_cost: this.editForm.unit_cost,
      selling_price: this.editForm.selling_price,
      category_id: this.editForm.category_id || undefined,
      is_active: this.editForm.is_active,
    };
    this.productsService.update(target.id, body).subscribe({
      next: (updated) => {
        const finish = (prod: Product) => {
          this.saving.set(false);
          this.showEdit = false;
          this.products.update((list) => list.map((p) => (p.id === prod.id ? prod : p)));
          this.messageService.add({ severity: 'success', summary: 'Updated', detail: 'Product updated' });
        };
        if (this.editFile) {
          this.productsService.uploadImage(updated.id, this.editFile).subscribe({
            next: finish,
            error: () => finish(updated),
          });
        } else {
          finish(updated);
        }
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update product' });
      },
    });
  }

  toggleActivate(product: Product): void {
    this.productsService.update(product.id, { is_active: !product.is_active }).subscribe({
      next: (updated) => {
        this.products.update((list) => list.map((p) => (p.id === product.id ? updated : p)));
        this.closeActionMenu();
        this.messageService.add({
          severity: 'success',
          summary: updated.is_active ? 'Activated' : 'Deactivated',
          detail: `"${updated.name}" ${updated.is_active ? 'activated' : 'deactivated'}`,
        });
      },
      error: () => this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update status' }),
    });
  }

  confirmDelete(product: Product): void {
    this.closeActionMenu();
    this.productPendingDelete.set(product);
  }

  executeDeleteProduct(): void {
    const product = this.productPendingDelete();
    if (!product) return;
    this.productPendingDelete.set(null);
    this.productsService.delete(product.id).subscribe({
      next: () => {
        this.products.update((list) => list.filter((p) => p.id !== product.id));
        this.messageService.add({ severity: 'success', summary: 'Deleted', detail: `"${product.name}" deleted` });
      },
      error: () => this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to delete product' }),
    });
  }

  // ── Bulk upload ──────────────────────────────────────────────────────────
  onBulkFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.bulkFile = input.files?.[0] ?? null;
    this.bulkResult.set(null);
  }

  downloadBulkTemplate(): void {
    const header = 'name,unit_cost,selling_price,sku,description,category,currency';
    const example = 'Sample Product,5000,8000,,A great product,Electronics,NGN';
    const csv = [header, example].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'product_upload_template.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  submitBulkUpload(): void {
    if (!this.bulkFile) return;
    this.uploadingBulk.set(true);
    this.bulkResult.set(null);
    this.productsService.bulkUpload(this.bulkFile).subscribe({
      next: (result) => {
        this.uploadingBulk.set(false);
        this.bulkResult.set(result);
        this.bulkFile = null;
        if (result.successful > 0) {
          this.loadProducts();
          this.loadStock();
          this.messageService.add({
            severity: 'success',
            summary: 'Upload complete',
            detail: `${result.successful} product(s) created`,
          });
        }
      },
      error: (err) => {
        this.uploadingBulk.set(false);
        const detail = err?.error?.detail ?? 'Upload failed';
        this.messageService.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  // ── Inline category (Add tab) ─────────────────────────────────────────────
  submitInlineCategory(): void {
    const name = this.inlineCategoryName.trim();
    if (!name) return;
    this.savingInlineCategory.set(true);
    this.productsService.createCategory({ name }).subscribe({
      next: (created) => {
        this.savingInlineCategory.set(false);
        this.categories.update((list) => [...list, created]);
        this.addForm.category_id = created.id;
        this.showInlineCategoryForm = false;
        this.inlineCategoryName = '';
        this.messageService.add({ severity: 'success', summary: 'Category created', detail: `"${created.name}" added and selected` });
      },
      error: () => {
        this.savingInlineCategory.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create category' });
      },
    });
  }

  // ── Category CRUD ─────────────────────────────────────────────────────────
  submitCreateCategory(): void {
    const name = this.newCategoryName.trim();
    if (!name) return;
    this.savingCategory.set(true);
    const body: CategoryCreate = { name, description: this.newCategoryDescription.trim() || undefined };
    this.productsService.createCategory(body).subscribe({
      next: (created) => {
        this.savingCategory.set(false);
        this.newCategoryName = '';
        this.newCategoryDescription = '';
        this.categories.update((list) => [...list, created]);
        this.messageService.add({ severity: 'success', summary: 'Created', detail: `Category "${created.name}" added` });
      },
      error: () => {
        this.savingCategory.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create category' });
      },
    });
  }

  confirmDeleteCategory(cat: Category): void {
    this.categoryPendingDelete.set(cat);
  }

  executeDeleteCategory(): void {
    const cat = this.categoryPendingDelete();
    if (!cat) return;
    this.categoryPendingDelete.set(null);
    this.productsService.deleteCategory(cat.id).subscribe({
      next: () => {
        this.categories.update((list) => list.filter((c) => c.id !== cat.id));
        this.products.update((list) => list.map((p) => (p.category_id === cat.id ? { ...p, category_id: null } : p)));
        this.messageService.add({ severity: 'success', summary: 'Deleted', detail: `Category "${cat.name}" deleted` });
      },
      error: () => this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to delete category' }),
    });
  }
}
