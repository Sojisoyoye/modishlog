import {
  Component,
  ChangeDetectionStrategy,
  DestroyRef,
  inject,
  signal,
  OnInit,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged, switchMap } from 'rxjs/operators';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  SuppliersService,
  Supplier,
  SupplierCreate,
  SupplierUpdate,
  SupplierPurchase,
  LedgerEntry,
  ActivityEntry,
  StockReportItem,
} from '../../../core/services/suppliers.service';

type DetailTab = 'purchases' | 'stock-report' | 'activities' | 'ledger';

@Component({
  selector: 'app-suppliers-page',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe, Toast, Dialog],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />

    <div>
      <!-- Header -->
      <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
            <i class="pi pi-users text-lg"></i>
          </div>
          <div>
            <h2 class="text-2xl font-bold text-text">Suppliers</h2>
            <p class="mt-0.5 text-sm text-muted">Manage your suppliers and purchase history</p>
          </div>
        </div>
        <button
          (click)="openAddDialog()"
          class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md min-h-[44px]"
        >
          <i class="pi pi-plus text-sm"></i> Add Supplier
        </button>
      </div>

      <!-- Search bar -->
      <div class="mb-4 flex gap-3">
        <div class="relative flex-1">
          <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"></i>
          <input
            type="text"
            id="supplier-search"
            aria-label="Search suppliers"
            [(ngModel)]="searchTerm"
            (ngModelChange)="supplierSearch$.next($event)"
            placeholder="Search suppliers..."
            class="w-full rounded-lg border border-gray-300 py-2.5 pl-9 pr-3 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>
        <label class="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-muted min-h-[44px]">
          <input type="checkbox" [(ngModel)]="activeOnly" (ngModelChange)="loadSuppliers()" />
          Active only
        </label>
      </div>

      <!-- Suppliers Table -->
      <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Suppliers list</caption>
            <thead>
              <tr class="bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Name</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Contact</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Mobile</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Email</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Pay Terms</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Opening Bal.</th>
                <th class="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @if (loading()) {
                @for (i of [1,2,3,4,5]; track i) {
                  <tr class="animate-pulse">
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-32"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-24"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-24"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-40"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-20"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-20 ml-auto"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-16 mx-auto"></div></td>
                    <td class="px-4 py-3"><div class="h-4 bg-gray-200 rounded w-16 ml-auto"></div></td>
                  </tr>
                }
              } @else {
              @for (s of suppliers(); track s.id) {
                <tr
                  class="cursor-pointer transition-colors hover:bg-gray-50"
                  (click)="openDetail(s)"
                >
                  <td class="px-4 py-3 font-semibold text-gray-900">{{ s.name }}</td>
                  <td class="px-4 py-3 text-sm text-gray-500">{{ s.contact_person ?? '—' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-500">{{ s.mobile ?? '—' }}</td>
                  <td class="px-4 py-3 text-sm text-gray-500">{{ s.email ?? '—' }}</td>
                  <td class="px-4 py-3 text-text">
                    @if (s.pay_term_number) {
                      {{ s.pay_term_number }} {{ s.pay_term_type }}
                    } @else {
                      —
                    }
                  </td>
                  <td class="px-4 py-3 text-right font-medium">
                    {{ s.opening_balance | number: '1.2-2' }}
                  </td>
                  <td class="px-4 py-3 text-center">
                    <span
                      class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                      [class]="s.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                    >
                      {{ s.is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-right" (click)="$event.stopPropagation()">
                    <button
                      [attr.data-testid]="'edit-supplier-' + s.name"
                      (click)="openEditDialog(s)"
                      class="mr-2 inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 text-muted transition-colors hover:bg-gray-100 hover:text-secondary"
                      title="Edit"
                    >
                      <i class="pi pi-pencil text-xs"></i>
                    </button>
                    <button
                      (click)="toggleActive(s)"
                      class="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 text-muted transition-colors hover:bg-gray-100 hover:text-text"
                      [title]="s.is_active ? 'Deactivate' : 'Activate'"
                    >
                      <i class="pi pi-power-off text-xs"></i>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8" class="px-4 py-16 text-center">
                    <div class="flex flex-col items-center gap-3">
                      @if (searchTerm || activeOnly) {
                        <i class="pi pi-search text-2xl text-muted"></i>
                        <p class="text-sm text-muted">No suppliers match your filters.</p>
                      } @else {
                        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50">
                          <i class="pi pi-users text-3xl text-emerald-300"></i>
                        </div>
                        <p class="font-semibold text-gray-900">No suppliers yet</p>
                        <p class="text-sm text-muted">Add your first supplier to get started.</p>
                        <button
                          (click)="openAddDialog()"
                          class="mt-1 flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 min-h-[44px]"
                        >
                          <i class="pi pi-plus text-xs"></i> Add Supplier
                        </button>
                      }
                    </div>
                  </td>
                </tr>
              }
              }
            </tbody>
          </table>
        </div>
        @if (total() > 0) {
          <div class="border-t border-gray-100 px-4 py-2 text-xs text-muted">
            Showing {{ suppliers().length }} of {{ total() }} suppliers
          </div>
        }
      </div>
    </div>

    <!-- Add / Edit Dialog -->
    <p-dialog
      [header]="editingSupplier() ? 'Edit Supplier' : 'Add Supplier'"
      [(visible)]="showForm"
      [modal]="true"
      [style]="{ width: '560px' }"
      [breakpoints]="{ '768px': '95vw' }"
    >
      <div class="space-y-4">
        <!-- Identity -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label for="supplier-name" class="mb-1 block text-xs font-medium text-muted">
              Supplier Name <span class="text-danger">*</span>
            </label>
            <input
              id="supplier-name"
              type="text"
              [(ngModel)]="form.name"
              placeholder="Supplier name"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label for="supplier-contact-person" class="mb-1 block text-xs font-medium text-muted">Contact Person</label>
            <input
              id="supplier-contact-person"
              type="text"
              [(ngModel)]="form.contact_person"
              placeholder="Contact person"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label for="supplier-tax-number" class="mb-1 block text-xs font-medium text-muted">Tax / VAT Number</label>
            <input
              id="supplier-tax-number"
              type="text"
              [(ngModel)]="form.tax_number"
              placeholder="TIN / VAT number"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label for="supplier-email" class="mb-1 block text-xs font-medium text-muted">Email Address</label>
            <input
              id="supplier-email"
              type="email"
              [(ngModel)]="form.email"
              placeholder="Email address"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label for="supplier-mobile" class="mb-1 block text-xs font-medium text-muted">Mobile</label>
            <input
              id="supplier-mobile"
              type="tel"
              [(ngModel)]="form.mobile"
              placeholder="Mobile number"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label for="supplier-alternate-number" class="mb-1 block text-xs font-medium text-muted">Alternate Number</label>
            <input
              id="supplier-alternate-number"
              type="tel"
              [(ngModel)]="form.alternate_number"
              placeholder="Alternate number"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Address -->
        <div>
          <p class="mb-2 text-xs font-semibold uppercase text-muted">Address</p>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div class="sm:col-span-2">
              <input
                type="text"
                [(ngModel)]="form.address_line_1"
                placeholder="Address line 1"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div class="sm:col-span-2">
              <input
                type="text"
                [(ngModel)]="form.address_line_2"
                placeholder="Address line 2"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.city"
                placeholder="City"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.state"
                placeholder="State"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.country"
                placeholder="Country"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.zip_code"
                placeholder="ZIP / Postal code"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
          </div>
        </div>

        <!-- Payment Terms & Opening Balance -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label for="supplier-pay-term-number" class="mb-1 block text-xs font-medium text-muted">Pay Term</label>
            <input
              id="supplier-pay-term-number"
              type="number"
              [(ngModel)]="form.pay_term_number"
              placeholder="e.g. 30"
              min="1"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label for="supplier-pay-term-type" class="mb-1 block text-xs font-medium text-muted">Term Type</label>
            <select
              id="supplier-pay-term-type"
              [(ngModel)]="form.pay_term_type"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            >
              <option value="">—</option>
              <option value="days">Days</option>
              <option value="months">Months</option>
            </select>
          </div>
          <div>
            <label for="supplier-opening-balance" class="mb-1 block text-xs font-medium text-muted">Opening Balance</label>
            <input
              id="supplier-opening-balance"
              type="number"
              [(ngModel)]="form.opening_balance"
              min="0"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Notes -->
        <div>
          <label for="supplier-notes" class="mb-1 block text-xs font-medium text-muted">Notes</label>
          <textarea
            id="supplier-notes"
            [(ngModel)]="form.notes"
            rows="2"
            placeholder="Internal notes about this supplier"
            class="w-full resize-none rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          ></textarea>
        </div>

        <div class="flex gap-3">
          <button
            type="button"
            (click)="showForm = false"
            class="flex flex-1 items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 shadow-sm transition-all hover:bg-gray-50 min-h-[44px]"
          >
            Cancel
          </button>
          <button
            (click)="saveSupplier()"
            [disabled]="saving() || !form.name"
            class="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50 min-h-[44px]"
          >
            @if (saving()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
            } @else {
              <i class="pi pi-check text-sm"></i> Save Supplier
            }
          </button>
        </div>
      </div>
    </p-dialog>

    <!-- Supplier Detail Dialog -->
    <p-dialog
      [header]="selectedSupplier()?.name ?? 'Supplier'"
      [(visible)]="showDetail"
      [modal]="true"
      [style]="{ width: '700px' }"
      [breakpoints]="{ '960px': '95vw' }"
    >
      @if (selectedSupplier()) {
        <!-- Supplier summary strip -->
        <div class="mb-4 grid grid-cols-1 gap-2 rounded-xl border border-gray-100 bg-gray-50 p-4 text-sm sm:grid-cols-2">
          <div>
            <p class="text-xs text-muted">Contact</p>
            <p class="font-semibold text-gray-900">{{ selectedSupplier()!.contact_person ?? '—' }}</p>
          </div>
          <div>
            <p class="text-xs text-muted">Mobile</p>
            <p class="font-semibold text-gray-900">{{ selectedSupplier()!.mobile ?? '—' }}</p>
          </div>
          <div>
            <p class="text-xs text-muted">Pay Terms</p>
            <p class="font-semibold text-gray-900">
              @if (selectedSupplier()!.pay_term_number) {
                {{ selectedSupplier()!.pay_term_number }} {{ selectedSupplier()!.pay_term_type }}
              } @else {
                —
              }
            </p>
          </div>
          <div>
            <p class="text-xs text-muted">Opening Balance</p>
            <p class="font-semibold text-amber-700">{{ selectedSupplier()!.opening_balance | number: '1.2-2' }}</p>
          </div>
        </div>

        <!-- Tabs -->
        <div class="mb-4 flex gap-1 overflow-x-auto scrollbar-none border-b border-gray-200">
          @for (tab of detailTabs; track tab.key) {
            <button
              role="tab"
              [attr.aria-selected]="activeTab() === tab.key"
              (click)="switchTab(tab.key)"
              class="px-4 py-2.5 text-sm transition-colors"
              [class]="activeTab() === tab.key
                ? 'border-b-2 border-primary text-primary font-semibold'
                : 'font-medium text-muted hover:text-text'"
            >
              {{ tab.label }}
            </button>
          }
        </div>

        <!-- Tab: Purchases -->
        @if (activeTab() === 'purchases') {
          <div class="overflow-x-auto">
            @if (tabLoading()) {
              <p class="py-8 text-center text-sm text-muted">
                <i class="pi pi-spinner pi-spin mr-2"></i>Loading...
              </p>
            } @else if (supplierPurchases().length === 0) {
              <p class="py-8 text-center text-sm text-muted">No purchases recorded for this supplier.</p>
            } @else {
              <table class="min-w-full divide-y divide-gray-200 text-sm">
                <thead>
                  <tr class="bg-gray-50">
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Order #</th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Date</th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Total</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  @for (p of supplierPurchases(); track p.id) {
                    <tr class="hover:bg-gray-50">
                      <td class="px-3 py-2 font-medium text-secondary">{{ p.order_number }}</td>
                      <td class="px-3 py-2 text-muted">{{ p.created_at | date: 'mediumDate' }}</td>
                      <td class="px-3 py-2">{{ p.status }}</td>
                      <td class="px-3 py-2 text-right font-semibold text-gray-900">{{ p.total_amount | number: '1.2-2' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </div>
        }

        <!-- Tab: Stock Report -->
        @if (activeTab() === 'stock-report') {
          <div class="overflow-x-auto">
            @if (tabLoading()) {
              <p class="py-8 text-center text-sm text-muted">
                <i class="pi pi-spinner pi-spin mr-2"></i>Loading...
              </p>
            } @else if (supplierStock().length === 0) {
              <p class="py-8 text-center text-sm text-muted">No stock linked to this supplier.</p>
            } @else {
              <table class="min-w-full divide-y divide-gray-200 text-sm">
                <thead>
                  <tr class="bg-gray-50">
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">SKU</th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Product</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Stock Qty</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Unit Cost</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Stock Value</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  @for (item of supplierStock(); track item.product_id) {
                    <tr class="hover:bg-gray-50">
                      <td class="px-3 py-2 text-muted">{{ item.sku }}</td>
                      <td class="px-3 py-2 font-medium text-text">{{ item.product_name }}</td>
                      <td class="px-3 py-2 text-right">{{ item.quantity_on_hand }}</td>
                      <td class="px-3 py-2 text-right">{{ item.unit_cost | number: '1.2-2' }}</td>
                      <td class="px-3 py-2 text-right font-semibold text-gray-900">{{ item.stock_value | number: '1.2-2' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </div>
        }

        <!-- Tab: Activities -->
        @if (activeTab() === 'activities') {
          <div>
            @if (tabLoading()) {
              <p class="py-8 text-center text-sm text-muted">
                <i class="pi pi-spinner pi-spin mr-2"></i>Loading...
              </p>
            } @else if (supplierActivities().length === 0) {
              <p class="py-8 text-center text-sm text-muted">No activity yet.</p>
            } @else {
              <div class="space-y-2">
                @for (a of supplierActivities(); track a.timestamp) {
                  <div class="flex items-start gap-3 rounded-lg border border-gray-100 p-3 text-sm">
                    <div
                      class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                      [class]="a.event_type === 'payment' ? 'bg-emerald-50 text-emerald-700' : 'bg-blue-100 text-blue-600'"
                    >
                      <i
                        class="pi text-xs"
                        [class]="a.event_type === 'payment' ? 'pi-check-circle' : 'pi-shopping-bag'"
                      ></i>
                    </div>
                    <div class="flex-1">
                      <p class="font-medium text-text">{{ a.description }}</p>
                      <p class="text-xs text-muted">{{ a.timestamp | date: 'medium' }}</p>
                    </div>
                    @if (a.amount) {
                      <p class="font-semibold text-gray-900">{{ a.amount | number: '1.2-2' }}</p>
                    }
                  </div>
                }
              </div>
            }
          </div>
        }

        <!-- Tab: Ledger -->
        @if (activeTab() === 'ledger') {
          <div class="overflow-x-auto">
            @if (tabLoading()) {
              <p class="py-8 text-center text-sm text-muted">
                <i class="pi pi-spinner pi-spin mr-2"></i>Loading...
              </p>
            } @else {
              <table class="min-w-full divide-y divide-gray-200 text-sm">
                <thead>
                  <tr class="bg-gray-50">
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Date</th>
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Description</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Debit</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Credit</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Balance</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  @if (supplierLedger().length === 0) {
                    <tr>
                      <td colspan="5" class="px-3 py-6 text-center text-muted">Opening balance</td>
                    </tr>
                  }
                  @for (entry of supplierLedger(); track $index) {
                    <tr class="hover:bg-gray-50">
                      <td class="px-3 py-2 text-muted">{{ entry.date | date: 'mediumDate' }}</td>
                      <td class="px-3 py-2 text-text">{{ entry.description }}</td>
                      <td class="px-3 py-2 text-right">
                        @if (entry.debit > 0) {
                          <span class="font-semibold text-red-600">{{ entry.debit | number: '1.2-2' }}</span>
                        } @else {
                          —
                        }
                      </td>
                      <td class="px-3 py-2 text-right">
                        @if (entry.credit > 0) {
                          <span class="font-semibold text-emerald-600">{{ entry.credit | number: '1.2-2' }}</span>
                        } @else {
                          —
                        }
                      </td>
                      <td class="px-3 py-2 text-right font-semibold text-text">
                        {{ entry.balance | number: '1.2-2' }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            }
          </div>
        }
      }
    </p-dialog>
  `,
})
export class SuppliersPageComponent implements OnInit {
  private readonly suppliersService = inject(SuppliersService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly supplierSearch$ = new Subject<string>();

  suppliers = signal<Supplier[]>([]);
  total = signal(0);
  loading = signal(false);
  saving = signal(false);
  tabLoading = signal(false);

  searchTerm = '';
  activeOnly = false;
  showForm = false;
  showDetail = false;

  editingSupplier = signal<Supplier | null>(null);
  selectedSupplier = signal<Supplier | null>(null);
  activeTab = signal<DetailTab>('purchases');

  supplierPurchases = signal<SupplierPurchase[]>([]);
  supplierStock = signal<StockReportItem[]>([]);
  supplierActivities = signal<ActivityEntry[]>([]);
  supplierLedger = signal<LedgerEntry[]>([]);

  form: SupplierCreate = this.emptyForm();

  readonly detailTabs: { key: DetailTab; label: string }[] = [
    { key: 'purchases', label: 'Purchases' },
    { key: 'stock-report', label: 'Stock Report' },
    { key: 'activities', label: 'Activities' },
    { key: 'ledger', label: 'Ledger' },
  ];

  ngOnInit(): void {
    this.supplierSearch$
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        switchMap(() => {
          const params: Record<string, string> = {};
          if (this.searchTerm) params['search'] = this.searchTerm;
          if (this.activeOnly) params['active_only'] = 'true';
          this.loading.set(true);
          return this.suppliersService.getAll(params);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (resp) => {
          this.suppliers.set(resp.items);
          this.total.set(resp.total);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load suppliers' });
        },
      });
    this.loadSuppliers();
  }

  loadSuppliers(): void {
    const params: Record<string, string> = {};
    if (this.searchTerm) params['search'] = this.searchTerm;
    if (this.activeOnly) params['active_only'] = 'true';
    this.loading.set(true);
    this.suppliersService.getAll(params).subscribe({
      next: (resp) => {
        this.suppliers.set(resp.items);
        this.total.set(resp.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load suppliers' });
      },
    });
  }

  openAddDialog(): void {
    this.editingSupplier.set(null);
    this.form = this.emptyForm();
    this.showForm = true;
  }

  openEditDialog(s: Supplier): void {
    this.editingSupplier.set(s);
    this.form = {
      name: s.name,
      contact_person: s.contact_person,
      email: s.email,
      mobile: s.mobile,
      alternate_number: s.alternate_number,
      tax_number: s.tax_number,
      address_line_1: s.address_line_1,
      address_line_2: s.address_line_2,
      city: s.city,
      state: s.state,
      country: s.country,
      zip_code: s.zip_code,
      pay_term_number: s.pay_term_number,
      pay_term_type: s.pay_term_type,
      opening_balance: s.opening_balance,
      notes: s.notes,
    };
    this.showForm = true;
  }

  saveSupplier(): void {
    if (!this.form.name) return;
    this.saving.set(true);
    const existing = this.editingSupplier();

    const payload: SupplierCreate = {
      ...this.form,
      pay_term_type: this.form.pay_term_type || null,
    };

    const req$ = existing
      ? this.suppliersService.update(existing.id, payload)
      : this.suppliersService.create(payload);

    req$.subscribe({
      next: () => {
        this.saving.set(false);
        this.showForm = false;
        this.messageService.add({
          severity: 'success',
          summary: existing ? 'Supplier updated' : 'Supplier added',
          detail: existing ? 'Supplier updated successfully' : `${this.form.name} added`,
        });
        this.loadSuppliers();
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to save supplier' });
      },
    });
  }

  toggleActive(s: Supplier): void {
    const update: SupplierUpdate = { is_active: !s.is_active };
    this.suppliersService.update(s.id, update).subscribe({
      next: () => this.loadSuppliers(),
    });
  }

  openDetail(s: Supplier): void {
    this.selectedSupplier.set(s);
    this.activeTab.set('purchases');
    this.showDetail = true;
    this.loadTab('purchases', s.id);
  }

  switchTab(tab: DetailTab): void {
    this.activeTab.set(tab);
    const s = this.selectedSupplier();
    if (s) this.loadTab(tab, s.id);
  }

  private loadTab(tab: DetailTab, id: string): void {
    this.tabLoading.set(true);
    if (tab === 'purchases') {
      this.suppliersService.getPurchases(id).subscribe({
        next: (r) => { this.supplierPurchases.set(r.items); this.tabLoading.set(false); },
        error: () => this.tabLoading.set(false),
      });
    } else if (tab === 'stock-report') {
      this.suppliersService.getStockReport(id).subscribe({
        next: (r) => { this.supplierStock.set(r); this.tabLoading.set(false); },
        error: () => this.tabLoading.set(false),
      });
    } else if (tab === 'activities') {
      this.suppliersService.getActivities(id).subscribe({
        next: (r) => { this.supplierActivities.set(r); this.tabLoading.set(false); },
        error: () => this.tabLoading.set(false),
      });
    } else if (tab === 'ledger') {
      this.suppliersService.getLedger(id).subscribe({
        next: (r) => { this.supplierLedger.set(r); this.tabLoading.set(false); },
        error: () => this.tabLoading.set(false),
      });
    }
  }

  private emptyForm(): SupplierCreate {
    return {
      name: '',
      contact_person: null,
      email: null,
      mobile: null,
      alternate_number: null,
      tax_number: null,
      address_line_1: null,
      address_line_2: null,
      city: null,
      state: null,
      country: null,
      zip_code: null,
      pay_term_number: null,
      pay_term_type: null,
      opening_balance: 0,
      notes: null,
    };
  }
}
