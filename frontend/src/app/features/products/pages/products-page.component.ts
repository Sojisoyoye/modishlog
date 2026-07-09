import { Component, ChangeDetectionStrategy, inject, signal, OnInit, computed } from '@angular/core';
import { forkJoin } from 'rxjs';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  ProductsService,
  Product,
  ProductVariant,
  ProductVariantCreate,
  Category,
  CategoryCreate,
  CategoryUpdate,
  ProductCreate,
  ProductUpdate,
  BulkUploadResult,
} from '../../../core/services/products.service';
import { InventoryService } from '../../../core/services/inventory.service';
import { FxService } from '../../../core/services/fx.service';
import { ApiService } from '../../../core/services/api.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { AlertBannerComponent } from '../../../shared/components/alert-banner/alert-banner.component';
import { environment } from '../../../../environments/environment';

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
          <i class="pi pi-pencil text-xs text-emerald-700"></i> Edit
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
        <button
          role="menuitem"
          title="Suggest sell price"
          (click)="openSuggestFromMenu()"
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text hover:bg-gray-50"
        >
          <i class="pi pi-tag text-xs text-primary"></i> Suggest Price
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

    <!-- Price Suggestion Panel -->
    @if (suggestionPanelProductId()) {
      <div class="fixed inset-0 z-[30] flex items-center justify-center bg-black/40" (click)="closeSuggestPanel()">
        <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl" (click)="$event.stopPropagation()">
          <div class="mb-4 flex items-center justify-between">
            <h3 class="font-bold text-text">Suggest Sell Price</h3>
            <button (click)="closeSuggestPanel()" aria-label="Close suggestions" class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded text-muted hover:bg-gray-100"><i class="pi pi-times text-sm"></i></button>
          </div>
          <p class="mb-3 text-sm text-muted">
            Product: <strong class="text-text">{{ products().find(p => p.id === suggestionPanelProductId())?.name }}</strong>
          </p>
          <div class="mb-4">
            <label class="mb-1 block text-xs font-medium text-muted">Target Margin: {{ (suggestionMargin() * 100 | number: '1.0-0') }}%</label>
            <input type="range" [(ngModel)]="suggestionMarginPct" min="20" max="70" step="1"
              (ngModelChange)="suggestionMargin.set($event / 100)"
              class="w-full accent-emerald-600" />
            <div class="mt-1 flex justify-between text-xs text-muted"><span>20%</span><span>70%</span></div>
          </div>
          <button
            (click)="runSuggestion()"
            [disabled]="suggestionLoading()"
            class="w-full rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
          >
            @if (suggestionLoading()) {
              <i class="pi pi-spinner pi-spin text-xs"></i> Computing…
            } @else {
              <i class="pi pi-sparkles text-xs"></i> Compute Suggestion
            }
          </button>
          @if (latestSuggestion()) {
            <div class="mt-4 rounded-lg bg-green-50 p-4 text-sm">
              <p class="mb-1 text-xs font-bold uppercase tracking-wider text-muted">Suggested Price</p>
              <p class="text-2xl font-bold text-success">₦{{ latestSuggestion()!.suggested_price_ngn | number: '1.0-0' }}</p>
              <div class="mt-2 space-y-1 text-xs text-muted">
                <p>Weighted landed cost: ₦{{ latestSuggestion()!.unit_cost_ngn | number: '1.0-0' }}</p>
                <p>FX rate used: ₦{{ latestSuggestion()!.fx_rate_used | number: '1.0-0' }}/USD</p>
                <p>Margin: {{ (latestSuggestion()!.target_margin_pct * 100 | number: '1.0-0') }}%</p>
                @if (latestSuggestion()!.current_catalog_price_ngn) {
                  <p>Current catalog: ₦{{ latestSuggestion()!.current_catalog_price_ngn | number: '1.0-0' }}</p>
                }
              </div>
            </div>
          }
          @if (suggestionError()) {
            <p class="mt-3 rounded-lg bg-red-50 p-3 text-xs text-red-600">{{ suggestionError() }}</p>
          }
        </div>
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
          class="flex min-h-[44px] items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
        >
          <i class="pi pi-plus text-sm"></i> New Product
        </button>
      </div>

      <!-- Tabs -->
      <div class="overflow-x-auto scrollbar-none -mx-4 px-4 sm:mx-0 sm:px-0">
        <div class="mt-4 flex gap-1 border-b border-gray-200 whitespace-nowrap">
          <button
            (click)="activeTab.set('products')"
            [class]="activeTab() === 'products' ? 'shrink-0 border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'shrink-0 border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
          >
            <i class="pi pi-box mr-1.5 text-xs"></i> All Products
            <span class="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted">{{ products().length }}</span>
          </button>
          <button
            (click)="activeTab.set('stock-report')"
            [class]="activeTab() === 'stock-report' ? 'shrink-0 border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'shrink-0 border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
          >
            <i class="pi pi-chart-bar mr-1.5 text-xs"></i> Stock Report
          </button>
          <button
            (click)="activeTab.set('add')"
            [class]="activeTab() === 'add' ? 'shrink-0 border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'shrink-0 border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
          >
            <i class="pi pi-plus-circle mr-1.5 text-xs"></i> Add Product
          </button>
          <button
            (click)="activeTab.set('upload')"
            [class]="activeTab() === 'upload' ? 'shrink-0 border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'shrink-0 border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
          >
            <i class="pi pi-upload mr-1.5 text-xs"></i> Bulk Upload
          </button>
          <button
            (click)="activeTab.set('categories')"
            [class]="activeTab() === 'categories' ? 'shrink-0 border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary' : 'shrink-0 border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
          >
            <i class="pi pi-tag mr-1.5 text-xs"></i> Categories
            <span class="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted">{{ categories().length }}</span>
          </button>
        </div>
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
        <div class="mb-4 rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
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
                @for (cat of categoryTree(); track cat.id) {
                  @if ((cat.children ?? []).length > 0) {
                    <optgroup [label]="cat.name">
                      @for (child of cat.children!; track child.id) {
                        <option [value]="child.id">{{ child.name }}</option>
                      }
                    </optgroup>
                  } @else {
                    <option [value]="cat.id">{{ cat.name }}</option>
                  }
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
        <div class="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-sm">
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
              @if (pageLoading()) {
                @for (i of [1,2,3,4,5,6]; track i) {
                  <tr class="animate-pulse">
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-3">
                        <div class="h-8 w-8 flex-shrink-0 rounded-lg bg-gray-200"></div>
                        <div class="h-4 w-32 rounded bg-gray-200"></div>
                      </div>
                    </td>
                    <td class="px-4 py-3"><div class="h-4 w-20 rounded bg-gray-200"></div></td>
                    <td class="px-4 py-3"><div class="h-4 w-20 rounded bg-gray-200"></div></td>
                    <td class="px-4 py-3"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-4 py-3"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-4 py-3"><div class="ml-auto h-4 w-10 rounded bg-gray-200"></div></td>
                    <td class="px-4 py-3"><div class="ml-auto h-6 w-6 rounded bg-gray-200"></div></td>
                  </tr>
                }
              } @else {
              @for (product of pagedProducts(); track product.id) {
                <tr class="transition-colors hover:bg-gray-50">
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-3">
                      <div class="h-8 w-8 flex-shrink-0 overflow-hidden rounded-lg bg-gray-100">
                        @if (product.image_url) {
                          <img [src]="mediaBaseUrl + product.image_url" [alt]="product.name" width="32" height="32" class="h-full w-full object-cover" />
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
                    <td class="px-4 py-3 font-mono text-xs text-muted">
                      {{ product.sku }}
                      @if (product.has_variants) {
                        <span class="ml-1 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full px-1.5 py-0.5">
                          variants
                        </span>
                      }
                    </td>
                  }
                  @if (visibleCols().category) {
                    <td class="px-4 py-3 text-muted">{{ categoryName(product.category_id) || '—' }}</td>
                  }
                  @if (visibleCols().unit_cost) {
                    <td class="px-4 py-3 text-right text-text">{{ product.unit_cost | number: '1.2-2' }}</td>
                  }
                  @if (visibleCols().selling_price) {
                    <td class="px-4 py-3 text-right font-semibold text-emerald-700">{{ product.selling_price | number: '1.2-2' }}</td>
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
                      aria-label="Product actions"
                      class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg p-2 text-muted hover:bg-gray-100"
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
              } <!-- end @else (pageLoading) -->
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
                aria-label="Previous page"
                class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded hover:bg-gray-100 disabled:opacity-40"
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
                aria-label="Next page"
                class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded hover:bg-gray-100 disabled:opacity-40"
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
            <div class="rounded-xl border border-gray-100 bg-white p-4 shadow-sm transition-all hover:shadow-md">
              <div class="mb-3 flex h-32 items-center justify-center overflow-hidden rounded-lg bg-gray-100">
                @if (product.image_url) {
                  <img [src]="mediaBaseUrl + product.image_url" [alt]="product.name" width="128" height="128" class="h-full w-full object-cover" />
                } @else {
                  <i class="pi pi-image text-3xl text-gray-300"></i>
                }
              </div>
              <div class="space-y-1">
                <div class="flex items-start justify-between gap-2">
                  <p class="font-semibold text-text">{{ product.name }}</p>
                  <span [class]="product.is_active ? 'rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700' : 'rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500'">
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
                    <p class="font-semibold text-emerald-700">{{ product.selling_price | number: '1.2-2' }}</p>
                  </div>
                </div>
                <p class="text-xs text-muted">Stock: <span [class]="stockStatus(product.id) === 'out' ? 'font-semibold text-red-600' : stockStatus(product.id) === 'low' ? 'font-semibold text-amber-600' : 'font-semibold text-text'">{{ stockMap().get(product.id) ?? 0 }}</span></p>
              </div>
              <div class="mt-3 flex gap-2 border-t border-gray-100 pt-3">
                <button (click)="openEdit(product)" class="flex-1 rounded-lg px-3 py-1.5 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-50">
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
              <button (click)="prevPage()" [disabled]="currentPage() === 1" aria-label="Previous page" class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded hover:bg-gray-100 disabled:opacity-40"><i class="pi pi-chevron-left text-xs"></i></button>
              @for (n of pageNumbers(); track n) {
                <button (click)="goToPage(n)" [class]="n === currentPage() ? 'rounded bg-primary px-2.5 py-1 text-xs font-semibold text-white' : 'rounded px-2.5 py-1 text-xs hover:bg-gray-100'">{{ n }}</button>
              }
              <button (click)="nextPage()" [disabled]="currentPage() === totalPages()" aria-label="Next page" class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded hover:bg-gray-100 disabled:opacity-40"><i class="pi pi-chevron-right text-xs"></i></button>
            </div>
          </div>
        }
      }
    }

    <!-- ── STOCK REPORT TAB ────────────────────────────────────────────────── -->
    @if (activeTab() === 'stock-report') {
      <div class="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-sm">
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
                <td class="px-4 py-3 text-right font-semibold text-emerald-700">{{ product.selling_price | number: '1.2-2' }}</td>
                <td class="px-4 py-3 text-right text-text">{{ stockMap().get(product.id) ?? 0 }}</td>
                <td class="px-4 py-3 text-right">
                  <span [class]="margin(product) >= 30 ? 'font-semibold text-emerald-700' : margin(product) >= 15 ? 'font-semibold text-amber-600' : 'font-semibold text-red-500'">
                    {{ margin(product) | number: '1.0-1' }}%
                  </span>
                </td>
                <td class="px-4 py-3 text-center">
                  @if (stockStatus(product.id) === 'out') {
                    <span class="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700">Out of Stock</span>
                  } @else if (stockStatus(product.id) === 'low') {
                    <span class="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">Low Stock</span>
                  } @else {
                    <span class="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700">In Stock</span>
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
      <div id="add-product-form" class="mx-auto max-w-lg rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-plus text-sm text-emerald-700"></i>
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
                @for (cat of categoryTree(); track cat.id) {
                  @if ((cat.children ?? []).length > 0) {
                    <optgroup [label]="cat.name">
                      @for (child of cat.children!; track child.id) {
                        <option [value]="child.id">{{ child.name }}</option>
                      }
                    </optgroup>
                  } @else {
                    <option [value]="cat.id">{{ cat.name }}</option>
                  }
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

          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Cost Currency</label>
              <select
                [ngModel]="addCurrency()"
                (ngModelChange)="addCurrency.set($event)"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="NGN">NGN (Naira)</option>
                <option value="USD">USD (Dollar)</option>
                <option value="EUR">EUR (Euro)</option>
                <option value="GBP">GBP (Pound)</option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Min Margin %</label>
              <input
                type="number"
                data-testid="add-min-margin-input"
                [ngModel]="addMinMarginPct()"
                (ngModelChange)="addMinMarginPct.set(+$event)"
                min="1"
                max="99"
                step="1"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
          @if (addCurrency() !== 'NGN' && currentFxRate() > 0) {
            <p class="text-xs text-muted">
              <i class="pi pi-info-circle mr-1"></i>
              Live rate: 1 {{ addCurrency() }} = {{ currentFxRate() | number: '1.0-2' }} NGN
            </p>
          }
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Unit Cost ({{ addCurrency() }}) *</label>
              <input
                type="text"
                data-testid="add-unit-cost-input"
                [(ngModel)]="addCostStr"
                (ngModelChange)="addForm.unit_cost = parseMoney($event)"
                (blur)="onAddCostBlur()"
                placeholder="0.00"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Selling Price (NGN) *</label>
              <input
                type="text"
                data-testid="add-selling-price-input"
                [(ngModel)]="addPriceStr"
                (ngModelChange)="addForm.selling_price = parseMoney($event)"
                (blur)="onAddPriceBlur()"
                placeholder="0.00"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>
          @if (addMinSellingPrice !== null) {
            <p
              data-testid="add-min-price-hint"
              class="text-xs font-medium text-emerald-600"
            >
              Min. suggested price ({{ addMinMarginPct() }}% margin): {{ addMinSellingPrice | number: '1.0-2' }} NGN
            </p>
          }
          @if (addFormMargin !== null) {
            <p
              data-testid="add-margin"
              class="text-xs font-medium"
              [class.text-emerald-700]="addFormMargin >= 0"
              [class.text-red-500]="addFormMargin < 0"
            >
              Margin: {{ addFormMargin | number: '1.1-1' }}%
            </p>
          }
          @if (addMinSellingPrice !== null && addForm.selling_price > 0 && addForm.selling_price < addMinSellingPrice) {
            <div
              data-testid="add-price-below-min-warning"
              class="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700"
            >
              <i class="pi pi-exclamation-triangle mt-0.5 text-xs"></i>
              <span>Selling price is below the {{ addMinMarginPct() }}% minimum margin threshold (min: {{ addMinSellingPrice | number: '1.0-2' }} NGN).</span>
            </div>
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
              class="w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary"
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
              class="flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
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
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-upload text-sm text-emerald-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Bulk Upload Products</h3>
          </div>

          <div class="mb-6 rounded-lg border border-blue-100 bg-blue-50/50 p-4">
            <p class="mb-2 text-sm font-medium text-text">Required columns</p>
            <div class="flex flex-wrap gap-2">
              <span class="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">name</span>
              <span class="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">unit_cost</span>
              <span class="rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700">selling_price</span>
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
            class="mb-5 flex items-center gap-2 text-sm font-medium text-emerald-700 transition-colors hover:text-primary hover:underline"
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
              class="mt-3 text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-50 file:px-4 file:py-2 file:text-sm file:font-medium file:text-primary"
            />
          </div>

          <button
            (click)="submitBulkUpload()"
            [disabled]="!bulkFile || uploadingBulk()"
            class="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
          >
            @if (uploadingBulk()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Uploading...
            } @else {
              <i class="pi pi-upload text-sm"></i> Upload Products
            }
          </button>

          @if (bulkResult()) {
            <div class="mt-5 rounded-lg border p-4" [class]="bulkResult()!.failed ? 'border-amber-200 bg-amber-50' : 'border-green-200 bg-green-50'">
              <p class="text-sm font-semibold" [class]="bulkResult()!.failed ? 'text-amber-700' : 'text-emerald-700'">
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
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <h3 class="mb-4 text-sm font-semibold text-text">Add New Category</h3>
          <div class="flex flex-wrap gap-3">
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
            <select
              [(ngModel)]="newCategoryParentId"
              data-testid="new-cat-parent-select"
              aria-label="Parent category"
              class="rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="">None (top-level)</option>
              @for (cat of categoryTree(); track cat.id) {
                <option [value]="cat.id">{{ cat.name }}</option>
              }
            </select>
            <div class="flex items-center gap-1">
              <input
                type="number"
                [(ngModel)]="newCategoryDefaultMarginPct"
                placeholder="Default margin % (optional)"
                min="0"
                max="99"
                step="1"
                aria-label="Default margin %"
                class="w-44 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <span class="text-xs text-muted">%</span>
            </div>
            <button
              (click)="submitCreateCategory()"
              [disabled]="savingCategory() || !newCategoryName.trim()"
              class="flex min-h-[44px] items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
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


        <div class="overflow-x-auto rounded-xl border border-gray-100 bg-white shadow-sm">
          <table class="min-w-full text-sm">
            <thead>
              <tr class="border-b border-gray-200 bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Name</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Description</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Default Margin</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted">Products</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-muted">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (cat of categoryTree(); track cat.id) {
                <tr class="transition-colors hover:bg-gray-50">
                  <td class="px-4 py-3 font-medium text-text">{{ cat.name }}</td>
                  <td class="px-4 py-3 text-muted">{{ cat.description || '—' }}</td>
                  <td class="px-4 py-3 text-muted">
                    @if (cat.default_margin_pct != null) {
                      <span class="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">{{ (cat.default_margin_pct * 100 | number: '1.0-0') }}%</span>
                    } @else {
                      <span class="text-xs text-muted">—</span>
                    }
                  </td>
                  <td class="px-4 py-3 text-muted">{{ productCountForCategory(cat.id) }}</td>
                  <td class="px-4 py-3 text-right">
                    <button (click)="openEditCategory(cat)" aria-label="Edit category" class="mr-1 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-muted hover:bg-gray-100" title="Edit category">
                      <i class="pi pi-pencil text-xs"></i>
                    </button>
                    <button (click)="confirmDeleteCategory(cat)" aria-label="Delete category" class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-red-400 hover:bg-red-50" title="Delete category">
                      <i class="pi pi-trash text-xs"></i>
                    </button>
                  </td>
                </tr>
                @for (child of (cat.children ?? []); track child.id) {
                  <tr class="bg-gray-50/50 transition-colors hover:bg-gray-100/50">
                    <td class="px-4 py-2 text-text">
                      <span class="pl-5 text-muted">↳</span>
                      <span class="ml-1 font-medium">{{ child.name }}</span>
                    </td>
                    <td class="px-4 py-2 text-sm text-muted">{{ child.description || '—' }}</td>
                    <td class="px-4 py-2 text-sm text-muted">
                      @if (child.default_margin_pct != null) {
                        <span class="rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">{{ (child.default_margin_pct * 100 | number: '1.0-0') }}%</span>
                      } @else {
                        <span class="text-xs text-muted">—</span>
                      }
                    </td>
                    <td class="px-4 py-2 text-sm text-muted">{{ productCountForCategory(child.id) }}</td>
                    <td class="px-4 py-2 text-right">
                      <button (click)="openEditCategory(child)" aria-label="Edit category" class="mr-1 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-muted hover:bg-gray-100" title="Edit sub-category">
                        <i class="pi pi-pencil text-xs"></i>
                      </button>
                      <button (click)="confirmDeleteCategory(child)" aria-label="Delete category" class="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg text-red-400 hover:bg-red-50" title="Delete sub-category">
                        <i class="pi pi-trash text-xs"></i>
                      </button>
                    </td>
                  </tr>
                }
              } @empty {
                <tr>
                  <td colspan="5" class="py-12 text-center text-muted">No categories yet. Add your first category above.</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    }

    <!-- ── EDIT CATEGORY DIALOG ────────────────────────────────────────────── -->
    <p-dialog
      header="Edit Category"
      [visible]="!!editingCategory()"
      (visibleChange)="!$event && editingCategory.set(null)"
      [modal]="true"
      [style]="{ width: '400px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
    >
      @if (editingCategory()) {
        <div class="space-y-4 pt-2">
          <div>
            <label for="cat-edit-name" class="mb-1.5 block text-xs font-medium text-muted">Name <span class="text-danger">*</span></label>
            <input
              id="cat-edit-name"
              [(ngModel)]="categoryEditForm.name"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="Category name"
            />
          </div>
          <div>
            <label for="cat-edit-description" class="mb-1.5 block text-xs font-medium text-muted">Description</label>
            <input
              id="cat-edit-description"
              [(ngModel)]="categoryEditForm.description"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              placeholder="Description (optional)"
            />
          </div>
          <div>
            <label for="cat-edit-margin" class="mb-1.5 block text-xs font-medium text-muted">Default Margin %</label>
            <div class="flex items-center gap-2">
              <input
                id="cat-edit-margin"
                type="number"
                [(ngModel)]="categoryEditForm.defaultMarginPct"
                min="0"
                max="99"
                step="1"
                placeholder="e.g. 35 (optional)"
                class="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <span class="text-xs text-muted">%</span>
            </div>
            <p class="mt-1 text-xs text-muted">Leave blank to inherit from parent or use system default (40%).</p>
          </div>
          <button
            (click)="saveEditCategory()"
            [disabled]="!categoryEditForm.name.trim()"
            class="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i class="pi pi-check text-sm"></i> Save
          </button>
        </div>
      }
    </p-dialog>

    <!-- ── EDIT PRODUCT DIALOG ─────────────────────────────────────────────── -->
    <p-dialog
      header="Edit Product"
      [visible]="showEdit"
      (visibleChange)="showEdit = $event"
      [modal]="true"
      [style]="{ width: '480px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
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
            @for (cat of categoryTree(); track cat.id) {
              @if ((cat.children ?? []).length > 0) {
                <optgroup [label]="cat.name">
                  @for (child of cat.children!; track child.id) {
                    <option [value]="child.id">{{ child.name }}</option>
                  }
                </optgroup>
              } @else {
                <option [value]="cat.id">{{ cat.name }}</option>
              }
            }
          </select>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Cost Currency</label>
            <select
              [ngModel]="editCurrency()"
              (ngModelChange)="editCurrency.set($event)"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="NGN">NGN (Naira)</option>
              <option value="USD">USD (Dollar)</option>
              <option value="EUR">EUR (Euro)</option>
              <option value="GBP">GBP (Pound)</option>
            </select>
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Min Margin %</label>
            <input
              type="number"
              data-testid="edit-min-margin-input"
              [ngModel]="editMinMarginPct()"
              (ngModelChange)="editMinMarginPct.set(+$event)"
              min="1"
              max="99"
              step="1"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>
        @if (editCurrency() !== 'NGN' && currentFxRate() > 0) {
          <p class="text-xs text-muted">
            <i class="pi pi-info-circle mr-1"></i>
            Live rate: 1 {{ editCurrency() }} = {{ currentFxRate() | number: '1.0-2' }} NGN
          </p>
        }
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Unit Cost ({{ editCurrency() }})</label>
            <input
              type="text"
              data-testid="edit-unit-cost-input"
              [(ngModel)]="editCostStr"
              (ngModelChange)="editForm.unit_cost = parseMoney($event)"
              (blur)="onEditCostBlur()"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Selling Price (NGN)</label>
            <input
              type="text"
              data-testid="edit-selling-price-input"
              [(ngModel)]="editPriceStr"
              (ngModelChange)="editForm.selling_price = parseMoney($event)"
              (blur)="onEditPriceBlur()"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>
        @if (editMinSellingPrice !== null) {
          <p
            data-testid="edit-min-price-hint"
            class="text-xs font-medium text-emerald-600"
          >
            Min. suggested price ({{ editMinMarginPct() }}% margin): {{ editMinSellingPrice | number: '1.0-2' }} NGN
          </p>
        }
        @if (editFormMargin !== null) {
          <p
            data-testid="edit-margin"
            class="text-xs font-medium"
            [class.text-emerald-700]="editFormMargin >= 0"
            [class.text-red-500]="editFormMargin < 0"
          >
            Margin: {{ editFormMargin | number: '1.1-1' }}%
          </p>
        }
        @if (editMinSellingPrice !== null && (editForm.selling_price ?? 0) > 0 && (editForm.selling_price ?? 0) < editMinSellingPrice) {
          <div
            data-testid="edit-price-below-min-warning"
            class="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700"
          >
            <i class="pi pi-exclamation-triangle mt-0.5 text-xs"></i>
            <span>Selling price is below the {{ editMinMarginPct() }}% minimum margin threshold (min: {{ editMinSellingPrice | number: '1.0-2' }} NGN).</span>
          </div>
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

        <!-- Has variants toggle -->
        <div class="flex items-center gap-2 mt-4">
          <input type="checkbox" id="edit-has-variants"
            [ngModel]="editForm.has_variants"
            (ngModelChange)="onHasVariantsToggle($event)"
            class="h-4 w-4 rounded border-gray-300 text-emerald-600">
          <label for="edit-has-variants" class="text-sm font-medium text-gray-700">
            Has variants (size, colour, etc.)
          </label>
        </div>

        <!-- Variants table (only shown when has_variants) -->
        @if (editForm.has_variants) {
          <div class="mt-4 border-t pt-4">
            <h4 class="text-sm font-semibold text-gray-700 mb-2">Variants</h4>

            @if (editProductVariants().length > 0) {
              <table class="w-full text-xs border border-gray-200 rounded mb-3">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-2 py-1.5 text-left">Name</th>
                    <th class="px-2 py-1.5 text-left">SKU</th>
                    <th class="px-2 py-1.5 text-right">Price Override</th>
                    <th class="px-2 py-1.5 text-right">Cost Override</th>
                    <th class="px-2 py-1.5 text-center">Status</th>
                    <th class="px-2 py-1.5"></th>
                  </tr>
                </thead>
                <tbody>
                  @for (v of editProductVariants(); track v.id) {
                    <tr class="border-t border-gray-100">
                      <td class="px-2 py-1.5">{{ v.name }}</td>
                      <td class="px-2 py-1.5 text-gray-500">{{ v.sku ?? '—' }}</td>
                      <td class="px-2 py-1.5 text-right">{{ v.price_override != null ? formatMoney(v.price_override) : '—' }}</td>
                      <td class="px-2 py-1.5 text-right">{{ v.cost_price_override != null ? formatMoney(v.cost_price_override) : '—' }}</td>
                      <td class="px-2 py-1.5 text-center">
                        <span [class]="v.is_active ? 'text-emerald-600' : 'text-gray-400'">
                          {{ v.is_active ? 'Active' : 'Inactive' }}
                        </span>
                      </td>
                      <td class="px-2 py-1.5 text-right">
                        <button (click)="deactivateVariant(v)" class="text-red-500 hover:text-red-700 text-xs min-h-[28px] px-2">
                          {{ v.is_active ? 'Deactivate' : 'Activate' }}
                        </button>
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            }

            <!-- Inline add form -->
            <div class="grid grid-cols-2 gap-2 text-xs">
              <div class="col-span-2">
                <input type="text" placeholder="Variant name *" [ngModel]="newVariantName()"
                  (ngModelChange)="newVariantName.set($event)"
                  class="w-full border border-gray-300 rounded px-2 py-1.5 text-xs">
              </div>
              <input type="text" placeholder="SKU (optional)" [ngModel]="newVariantSku()"
                (ngModelChange)="newVariantSku.set($event)"
                class="border border-gray-300 rounded px-2 py-1.5 text-xs">
              <input type="text" placeholder="Price override (optional)" [ngModel]="newVariantPriceOverride()"
                (ngModelChange)="newVariantPriceOverride.set($event)"
                class="border border-gray-300 rounded px-2 py-1.5 text-xs">
              <input type="text" placeholder="Cost override (optional)" [ngModel]="newVariantCostOverride()"
                (ngModelChange)="newVariantCostOverride.set($event)"
                class="border border-gray-300 rounded px-2 py-1.5 text-xs">
            </div>
            <button (click)="addVariant()" [disabled]="variantSaving() || !newVariantName().trim()"
              class="mt-2 px-3 py-1.5 bg-emerald-600 text-white text-xs rounded hover:bg-emerald-700 disabled:opacity-50 min-h-[36px]">
              {{ variantSaving() ? 'Adding…' : '+ Add Variant' }}
            </button>
          </div>
        }

        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Replace Image</label>
          <input
            type="file"
            accept="image/*"
            (change)="onEditFileChange($event)"
            class="w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-primary"
          />
        </div>
        <button
          (click)="submitEdit()"
          [disabled]="saving()"
          class="flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
        >
          @if (saving()) {
            <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
          } @else {
            <i class="pi pi-check text-sm"></i> Save Changes
          }
        </button>
      </div>
    </p-dialog>

    <!-- ── CONFIRM DELETE CATEGORY DIALOG ───────────────────────────────────── -->
    <app-confirm-dialog
      [visible]="!!categoryPendingDelete()"
      header="Delete Category"
      [message]="'Delete category &quot;' + (categoryPendingDelete()?.name ?? '') + '&quot;? Direct products will become uncategorised. This will fail if the category has sub-categories.'"
      (confirmed)="executeDeleteCategory()"
      (cancelled)="categoryPendingDelete.set(null)"
    />

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
  private readonly fxService = inject(FxService);
  private readonly messageService = inject(MessageService);
  private readonly api = inject(ApiService);
  readonly mediaBaseUrl = environment.apiBaseUrl.replace('/api/v1', '');

  // ── Shared state ──────────────────────────────────────────────────────────
  pageLoading = signal(true);
  products = signal<Product[]>([]);
  categories = signal<Category[]>([]);   // flat list: all top-level + sub-categories
  categoryTree = signal<Category[]>([]); // tree: top-level with children nested
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

  // ── Price suggestion panel ─────────────────────────────────────────────────
  suggestionPanelProductId = signal<string | null>(null);
  suggestionMargin = signal<number>(0.40);
  suggestionMarginPct = 40;
  suggestionLoading = signal(false);
  latestSuggestion = signal<{ suggested_price_ngn: number; unit_cost_ngn: number; fx_rate_used: number; target_margin_pct: number; current_catalog_price_ngn: number | null } | null>(null);
  suggestionError = signal<string | null>(null);

  // ── Edit dialog ───────────────────────────────────────────────────────────
  showEdit = false;
  editTarget = signal<Product | null>(null);

  // ── Variants management ───────────────────────────────────────────────────
  editProductVariants = signal<ProductVariant[]>([]);
  variantSaving = signal(false);
  newVariantName = signal('');
  newVariantSku = signal('');
  newVariantPriceOverride = signal<string>('');
  newVariantCostOverride = signal<string>('');

  // ── Confirm delete dialogs ────────────────────────────────────────────────
  categoryPendingDelete = signal<Category | null>(null);
  productPendingDelete = signal<Product | null>(null);

  // ── Edit category dialog ──────────────────────────────────────────────────
  editingCategory = signal<Category | null>(null);
  categoryEditForm: { name: string; description: string; defaultMarginPct: number | null } = { name: '', description: '', defaultMarginPct: null };
  editForm: ProductUpdate & { category_id: string; is_active: boolean; has_variants: boolean } = {
    name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '', is_active: true, has_variants: false,
  };
  editFile: File | null = null;

  // Display strings for currency-formatted price inputs (edit dialog)
  editCostStr = '';
  editPriceStr = '';

  // ── Add Product tab form ──────────────────────────────────────────────────
  addForm: ProductCreate & { category_id: string } = {
    name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '',
  };
  addFile: File | null = null;

  // Display strings for currency-formatted price inputs (add form)
  addCostStr = '';
  addPriceStr = '';

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
  newCategoryParentId = '';
  newCategoryDefaultMarginPct: number | null = null;
  savingCategory = signal(false);

  // ── FX-aware selling price suggestion ────────────────────────────────────
  currentFxRate = signal<number>(0);
  addMinMarginPct = signal<number>(35);
  addCurrency = signal<string>('NGN');
  editMinMarginPct = signal<number>(35);
  editCurrency = signal<string>('NGN');

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
    this.pageLoading.set(true);
    forkJoin({
      products: this.productsService.getAll(),
      categories: this.productsService.getCategories(),
      stock: this.inventoryService.getCurrent(1, 10_000),
    }).subscribe({
      next: ({ products, categories, stock }) => {
        this.products.set(products);

        this.categoryTree.set(categories);
        this.categories.set(this._flattenCategories(categories));

        const sm = new Map<string, number>();
        const tm = new Map<string, number>();
        stock.items.forEach((item) => {
          sm.set(item.product_id, item.current_stock);
          tm.set(item.product_id, item.low_stock_threshold);
        });
        this.stockMap.set(sm);
        this.thresholdMap.set(tm);

        this.pageLoading.set(false);
      },
      error: () => { this.pageLoading.set(false); },
    });
    // FX rate is optional UI enhancement — fire independently so it doesn't
    // block the main forkJoin or delay the skeleton from clearing.
    this.fxService.getLatest().subscribe({
      next: (rate) => this.currentFxRate.set(rate.rate),
      error: () => { /* FX rate unavailable — min price hint will be hidden for foreign currencies */ },
    });
  }

  private loadProducts(): void {
    this.productsService.getAll().subscribe({
      next: (p) => { this.products.set(p); },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to refresh products' });
      },
    });
  }

  private loadCategories(): void {
    this.productsService.getCategories().subscribe({
      next: (tree) => {
        this.categoryTree.set(tree);
        this.categories.set(this._flattenCategories(tree));
      },
    });
  }

  private _flattenCategories(tree: Category[]): Category[] {
    const flat: Category[] = [];
    for (const cat of tree) {
      flat.push(cat);
      for (const child of (cat.children ?? [])) flat.push(child);
    }
    return flat;
  }

  private loadStock(): void {
    this.inventoryService.getCurrent(1, 10_000).subscribe({
      next: ({ items }) => {
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

  get addMinSellingPrice(): number | null {
    const cost = this.addForm.unit_cost;
    if (!cost || cost <= 0) return null;
    const margin = this.addMinMarginPct();
    if (margin >= 100) return null;
    const fxRate = this.currentFxRate();
    const currency = this.addCurrency();
    if (currency !== 'NGN' && !fxRate) return null;
    const costNgn = currency === 'NGN' ? cost : cost * fxRate;
    return costNgn / (1 - margin / 100);
  }

  get editMinSellingPrice(): number | null {
    const cost = this.editForm.unit_cost ?? 0;
    if (!cost || cost <= 0) return null;
    const margin = this.editMinMarginPct();
    if (margin >= 100) return null;
    const fxRate = this.currentFxRate();
    const currency = this.editCurrency();
    if (currency !== 'NGN' && !fxRate) return null;
    const costNgn = currency === 'NGN' ? cost : cost * fxRate;
    return costNgn / (1 - margin / 100);
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

  openSuggestFromMenu(): void {
    const product = this.menuProduct();
    if (!product) return;
    this.closeActionMenu();
    this.latestSuggestion.set(null);
    this.suggestionError.set(null);

    // Pre-fill margin from category hierarchy: sub-category → parent → system default 40%
    const defaultMarginPct = this.resolveDefaultMarginPct(product.category_id);
    this.suggestionMarginPct = defaultMarginPct;
    this.suggestionMargin.set(defaultMarginPct / 100);
    this.suggestionPanelProductId.set(product.id);
  }

  private resolveDefaultMarginPct(categoryId: string | null): number {
    if (!categoryId) return 40;
    const cat = this.findCategoryById(categoryId);
    if (!cat) return 40;
    let raw = 40;
    if (cat.default_margin_pct != null) {
      raw = cat.default_margin_pct * 100;
    } else if (cat.parent_id) {
      const parent = this.findCategoryById(cat.parent_id);
      if (parent?.default_margin_pct != null) {
        raw = parent.default_margin_pct * 100;
      }
    }
    // Clamp to slider range [20, 70]; step is now 1 so any integer value is valid
    return Math.min(70, Math.max(20, Math.round(raw)));
  }

  private findCategoryById(id: string | null): Category | null {
    if (!id) return null;
    for (const cat of this.categoryTree()) {
      if (cat.id === id) return cat;
      for (const child of cat.children ?? []) {
        if (child.id === id) return child;
      }
    }
    return null;
  }

  closeSuggestPanel(): void {
    this.suggestionPanelProductId.set(null);
    this.latestSuggestion.set(null);
    this.suggestionError.set(null);
  }

  runSuggestion(): void {
    const pid = this.suggestionPanelProductId();
    if (!pid) return;
    this.suggestionLoading.set(true);
    this.suggestionError.set(null);
    this.api.post<{ suggested_price_ngn: number; unit_cost_ngn: number; fx_rate_used: number; target_margin_pct: number; current_catalog_price_ngn: number | null }>(
      `/pricing/suggest/${pid}`,
      { target_margin_pct: this.suggestionMargin() }
    ).subscribe({
      next: (r) => {
        this.latestSuggestion.set(r);
        this.suggestionLoading.set(false);
      },
      error: (err) => {
        this.suggestionError.set(
          err?.status === 422 ? 'No active lots found for this product' : 'Failed to compute price suggestion'
        );
        this.suggestionLoading.set(false);
      },
    });
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
  formatMoney(value: number): string {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(isFinite(value) ? value : 0);
  }

  parseMoney(s: string): number {
    const n = parseFloat(String(s).replace(/,/g, ''));
    return isNaN(n) ? 0 : n;
  }

  openEdit(product: Product): void {
    this.editTarget.set(product);
    const cost = parseFloat(String(product.unit_cost ?? 0));
    const price = parseFloat(String(product.selling_price ?? 0));
    this.editForm = {
      name: product.name,
      category_id: product.category_id ?? '',
      unit_cost: cost,
      selling_price: price,
      description: product.description ?? '',
      is_active: product.is_active,
      has_variants: product.has_variants ?? false,
    };
    this.editCostStr = this.formatMoney(cost);
    this.editPriceStr = this.formatMoney(price);
    this.editFile = null;
    this.editCurrency.set(product.currency || 'NGN');
    this.editMinMarginPct.set(35);
    this.editProductVariants.set([]);
    this.newVariantName.set('');
    this.newVariantSku.set('');
    this.newVariantPriceOverride.set('');
    this.newVariantCostOverride.set('');
    this.showEdit = true;
    this.closeActionMenu();
    // Load variants only if product has_variants flag is set
    if (product.has_variants) {
      this.productsService.getVariants(product.id).subscribe({
        next: (variants) => this.editProductVariants.set(variants),
        error: () => { /* variants unavailable — non-fatal */ },
      });
    } else {
      this.editProductVariants.set([]);
    }
  }

  onEditCostBlur(): void {
    const n = this.parseMoney(this.editCostStr);
    this.editForm.unit_cost = n;
    this.editCostStr = this.formatMoney(n);
  }

  onEditPriceBlur(): void {
    const n = this.parseMoney(this.editPriceStr);
    this.editForm.selling_price = n;
    this.editPriceStr = this.formatMoney(n);
  }

  onAddCostBlur(): void {
    const n = this.parseMoney(this.addCostStr);
    this.addForm.unit_cost = n;
    this.addCostStr = n ? this.formatMoney(n) : '';
  }

  onAddPriceBlur(): void {
    const n = this.parseMoney(this.addPriceStr);
    this.addForm.selling_price = n;
    this.addPriceStr = n ? this.formatMoney(n) : '';
  }

  onEditFileChange(event: Event): void {
    this.editFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  onAddFileChange(event: Event): void {
    this.addFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  cancelAdd(): void {
    this.addForm = { name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '' };
    this.addCostStr = '';
    this.addPriceStr = '';
    this.addFile = null;
    this.showInlineCategoryForm = false;
    this.inlineCategoryName = '';
    this.addCurrency.set('NGN');
    this.addMinMarginPct.set(35);
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
      currency: this.addCurrency(),
    };
    this.productsService.create(body).subscribe({
      next: (created) => {
        const finish = (prod: Product) => {
          this.savingAdd.set(false);
          this.addForm = { name: '', category_id: '', unit_cost: 0, selling_price: 0, description: '' };
          this.addCostStr = '';
          this.addPriceStr = '';
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
      has_variants: this.editForm.has_variants,
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

  // ── Variants management ───────────────────────────────────────────────────
  onHasVariantsToggle(val: boolean): void {
    if (!val && this.editProductVariants().length > 0) {
      if (!confirm('Disabling variants will not delete existing variants. Continue?')) return;
    }
    this.editForm = { ...this.editForm, has_variants: val };
  }

  addVariant(): void {
    const productId = this.menuProduct()?.id ?? this.editTarget()?.id;
    if (!productId || !this.newVariantName().trim()) return;
    this.variantSaving.set(true);
    const priceStr = this.newVariantPriceOverride().trim();
    const parsedPrice = priceStr ? parseFloat(priceStr.replace(/,/g, '')) : NaN;
    const costStr = this.newVariantCostOverride().trim();
    const parsedCost = costStr ? parseFloat(costStr.replace(/,/g, '')) : NaN;
    const body: ProductVariantCreate = {
      name: this.newVariantName().trim(),
      sku: this.newVariantSku().trim() || undefined,
      price_override: (!isNaN(parsedPrice) && parsedPrice > 0) ? parsedPrice : undefined,
      cost_price_override: (!isNaN(parsedCost) && parsedCost > 0) ? parsedCost : undefined,
    };
    this.productsService.createVariant(productId, body).subscribe({
      next: (v) => {
        this.editProductVariants.update((list) => [...list, v]);
        this.newVariantName.set('');
        this.newVariantSku.set('');
        this.newVariantPriceOverride.set('');
        this.newVariantCostOverride.set('');
        this.variantSaving.set(false);
      },
      error: () => {
        this.variantSaving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to add variant' });
      },
    });
  }

  deactivateVariant(variant: ProductVariant): void {
    const productId = this.menuProduct()?.id ?? this.editTarget()?.id;
    if (!productId) return;
    this.productsService.updateVariant(productId, variant.id, { is_active: !variant.is_active }).subscribe({
      next: (updated) => {
        this.editProductVariants.update((list) => list.map((v) => (v.id === updated.id ? updated : v)));
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update variant' });
      },
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
      error: () => {
        this.uploadingBulk.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Upload failed' });
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
        this.addForm.category_id = created.id;
        this.showInlineCategoryForm = false;
        this.inlineCategoryName = '';
        this.loadCategories();
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
    const body: CategoryCreate = {
      name,
      description: this.newCategoryDescription.trim() || undefined,
      parent_id: this.newCategoryParentId || undefined,
      default_margin_pct: this.newCategoryDefaultMarginPct != null ? this.newCategoryDefaultMarginPct / 100 : undefined,
    };
    this.productsService.createCategory(body).subscribe({
      next: (created) => {
        this.savingCategory.set(false);
        this.newCategoryName = '';
        this.newCategoryDescription = '';
        this.newCategoryParentId = '';
        this.newCategoryDefaultMarginPct = null;
        this.loadCategories();
        this.messageService.add({ severity: 'success', summary: 'Created', detail: `Category "${created.name}" added` });
      },
      error: () => {
        this.savingCategory.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create category' });
      },
    });
  }

  openEditCategory(cat: Category): void {
    this.categoryEditForm = {
      name: cat.name,
      description: cat.description ?? '',
      defaultMarginPct: cat.default_margin_pct != null ? Math.round(cat.default_margin_pct * 100) : null,
    };
    this.editingCategory.set(cat);
  }

  saveEditCategory(): void {
    const cat = this.editingCategory();
    if (!cat || !this.categoryEditForm.name.trim()) return;
    const payload: CategoryUpdate = {
      name: this.categoryEditForm.name.trim(),
      description: this.categoryEditForm.description.trim() || null,
      default_margin_pct: this.categoryEditForm.defaultMarginPct != null ? this.categoryEditForm.defaultMarginPct / 100 : null,
    };
    this.productsService.updateCategory(cat.id, payload).subscribe({
      next: () => {
        this.editingCategory.set(null);
        this.loadCategories();
        this.messageService.add({ severity: 'success', summary: 'Updated', detail: 'Category updated' });
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update category' });
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
        this.loadCategories();
        this.products.update((list) => list.map((p) => (p.category_id === cat.id ? { ...p, category_id: null } : p)));
        this.messageService.add({ severity: 'success', summary: 'Deleted', detail: `Category "${cat.name}" deleted` });
      },
      error: (err) => {
        if (err.status === 409) {
          const backendDetail: string = err.error?.detail ?? '';
          // Sub-categories blocking deletion
          const childMatch = /has (\d+) sub-categor/.exec(backendDetail);
          if (childMatch) {
            const n = childMatch[1];
            this.messageService.add({ severity: 'warn', summary: 'Cannot Delete', detail: `"${cat.name}" has ${n} sub-categor${n === '1' ? 'y' : 'ies'}. Delete them first.` });
            return;
          }
          // Products blocking deletion
          const count = /has (\d+) linked/.exec(backendDetail)?.[1];
          const noun = count === '1' ? 'product' : 'products';
          const detail = count
            ? `"${cat.name}" still has ${count} ${noun}. Move or delete them before removing the category.`
            : `"${cat.name}" still has products. Move or delete them before removing the category.`;
          this.messageService.add({ severity: 'warn', summary: 'Cannot Delete', detail });
        } else {
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to delete category' });
        }
      },
    });
  }
}
