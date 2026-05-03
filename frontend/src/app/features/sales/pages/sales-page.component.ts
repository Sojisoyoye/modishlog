import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, CurrencyPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  SalesService,
  SaleRecord,
  AuditEntry,
  SaleUpdatePayload,
  BulkUploadResponse,
} from '../../../core/services/sales.service';
import { ProductsService, Product } from '../../../core/services/products.service';
import { InventoryService } from '../../../core/services/inventory.service';

interface EntryRow {
  product_id: string;
  quantity: number;
  sale_date: string;
  unit_price: number | null;
  discount_amount: number | null;
}

@Component({
  selector: 'app-sales-page',
  standalone: true,
  imports: [FormsModule, DatePipe, CurrencyPipe, Toast, Dialog],
  template: `
    <p-toast />
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Sales</h2>
        <p class="mt-1 text-sm text-muted">Record and track your daily sales</p>
      </div>

      <!-- Tab Navigation -->
      <div class="mb-6 border-b border-gray-200">
        <nav class="-mb-px flex gap-4" aria-label="Sales tabs">
          <button
            type="button"
            data-testid="tab-record-sales"
            (click)="activeTab.set('record')"
            class="whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors"
            [class.border-primary]="activeTab() === 'record'"
            [class.text-primary]="activeTab() === 'record'"
            [class.border-transparent]="activeTab() !== 'record'"
            [class.text-muted]="activeTab() !== 'record'"
            [class.hover:border-gray-300]="activeTab() !== 'record'"
            [class.hover:text-text]="activeTab() !== 'record'"
          >
            <i class="pi pi-plus-circle mr-1.5 text-xs"></i>
            Record Sales
          </button>
          <button
            type="button"
            data-testid="tab-all-sales"
            (click)="activeTab.set('all')"
            class="whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors"
            [class.border-primary]="activeTab() === 'all'"
            [class.text-primary]="activeTab() === 'all'"
            [class.border-transparent]="activeTab() !== 'all'"
            [class.text-muted]="activeTab() !== 'all'"
            [class.hover:border-gray-300]="activeTab() !== 'all'"
            [class.hover:text-text]="activeTab() !== 'all'"
          >
            <i class="pi pi-list mr-1.5 text-xs"></i>
            All Sales
          </button>
          <button
            type="button"
            data-testid="tab-upload-csv"
            (click)="activeTab.set('upload')"
            class="whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors"
            [class.border-primary]="activeTab() === 'upload'"
            [class.text-primary]="activeTab() === 'upload'"
            [class.border-transparent]="activeTab() !== 'upload'"
            [class.text-muted]="activeTab() !== 'upload'"
            [class.hover:border-gray-300]="activeTab() !== 'upload'"
            [class.hover:text-text]="activeTab() !== 'upload'"
          >
            <i class="pi pi-upload mr-1.5 text-xs"></i>
            Upload CSV
          </button>
        </nav>
      </div>

      <!-- Record Sales Tab -->
      @if (activeTab() === 'record') {
        <div class="grid grid-cols-1 gap-6">
          <!-- Entry Form -->
          <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div class="mb-5 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
                <i class="pi pi-plus text-sm text-secondary"></i>
              </div>
              <h3 class="text-base font-semibold text-text">Record Sales</h3>
            </div>

            @for (row of entryRows(); track $index) {
              <div class="mb-3">
                <div class="flex flex-wrap items-end gap-3">
                  <div class="min-w-[200px] flex-1 lg:min-w-[260px]">
                    @if ($index === 0) {
                      <label class="mb-1.5 block text-xs font-medium text-muted">Product</label>
                    }
                    <div class="flex items-center gap-2">
                      <select
                        [(ngModel)]="row.product_id"
                        [name]="'product_' + $index"
                        (change)="onProductChange(row)"
                        class="w-full rounded-lg border border-gray-300 px-3 py-3 text-base transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                      >
                        <option value="">Select product</option>
                        @for (p of products(); track p.id) {
                          <option [value]="p.id">{{ p.name }}</option>
                        }
                      </select>
                      @if (row.product_id && getStock(row.product_id) !== undefined) {
                        <span
                          data-testid="stock-indicator"
                          class="whitespace-nowrap text-xs font-medium text-muted"
                        >(Stock: {{ getStock(row.product_id) }})</span>
                      }
                    </div>
                  </div>
                  <div class="w-20">
                    @if ($index === 0) {
                      <label class="mb-1.5 block text-xs font-medium text-muted">Qty</label>
                    }
                    <input
                      type="number"
                      [(ngModel)]="row.quantity"
                      [name]="'qty_' + $index"
                      min="1"
                      class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                      [class.border-red-500]="exceedsStock(row)"
                    />
                  </div>
                  <div class="w-32">
                    @if ($index === 0) {
                      <label class="mb-1.5 block text-xs font-medium text-muted">Unit Price</label>
                    }
                    <input
                      type="number"
                      [(ngModel)]="row.unit_price"
                      [name]="'price_' + $index"
                      min="0"
                      step="0.01"
                      data-testid="entry-price-input"
                      [placeholder]="row.product_id ? '' : '—'"
                      class="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div class="w-32">
                    @if ($index === 0) {
                      <label class="mb-1.5 block text-xs font-medium text-muted">Discount</label>
                    }
                    <input
                      type="number"
                      [(ngModel)]="row.discount_amount"
                      [name]="'discount_' + $index"
                      min="0"
                      step="0.01"
                      data-testid="entry-discount-input"
                      placeholder="0.00"
                      class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div class="w-32">
                    @if ($index === 0) {
                      <label class="mb-1.5 block text-xs font-medium text-muted">Line Total</label>
                    }
                    <div
                      data-testid="entry-line-total"
                      class="flex h-[42px] items-center rounded-lg border border-gray-200 bg-gray-50 px-3 text-sm font-semibold text-text"
                    >
                      {{ lineTotal(row) | currency: 'NGN' : 'symbol' : '1.2-2' }}
                    </div>
                  </div>
                  <div class="w-28">
                    @if ($index === 0) {
                      <label class="mb-1.5 block text-xs font-medium text-muted">Date</label>
                    }
                    <input
                      type="date"
                      [(ngModel)]="row.sale_date"
                      [name]="'date_' + $index"
                      class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  @if (entryRows().length > 1) {
                    <button
                      (click)="removeRow($index)"
                      class="rounded-lg p-2.5 text-muted transition-colors hover:bg-red-50 hover:text-danger"
                      type="button"
                    >
                      <i class="pi pi-trash text-sm"></i>
                    </button>
                  }
                </div>
                @if (exceedsStock(row)) {
                  <p
                    data-testid="stock-warning"
                    class="mt-1 text-xs font-medium text-red-600"
                  >Exceeds available stock ({{ getStock(row.product_id) }})</p>
                }
              </div>
            }

            <div class="mt-4 flex gap-3">
              <button
                (click)="addRow()"
                class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
                type="button"
              >
                <i class="pi pi-plus text-xs"></i> Add Row
              </button>
              <button
                (click)="submitEntries()"
                [disabled]="submitting() || hasStockExceeded()"
                class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
              >
                @if (submitting()) {
                  <i class="pi pi-spinner pi-spin text-sm"></i>
                  Saving...
                } @else {
                  <i class="pi pi-check text-sm"></i>
                  Record Sales
                }
              </button>
            </div>
          </div>

          <!-- Recent Sales (shown alongside entry form) -->
          <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div class="mb-5 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
                <i class="pi pi-history text-sm text-success"></i>
              </div>
              <h3 class="text-base font-semibold text-text">Recent Sales</h3>
            </div>

            <div class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200 text-sm">
                <caption class="sr-only">Recent sales records</caption>
                <thead>
                  <tr class="bg-gray-50/80">
                    <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Date</th>
                    <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Product</th>
                    <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Qty</th>
                    <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Total</th>
                    <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Status</th>
                    <th class="px-3 py-2.5 text-center text-xs font-semibold uppercase text-muted">Actions</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  @for (sale of history(); track sale.id) {
                    <tr class="transition-colors hover:bg-gray-50/50">
                      <td class="px-3 py-2.5 text-muted">{{ sale.sale_date | date: 'mediumDate' }}</td>
                      <td class="px-3 py-2.5 font-medium">{{ getProductName(sale.product_id) }}</td>
                      <td class="px-3 py-2.5 text-right">{{ sale.quantity }}</td>
                      <td class="px-3 py-2.5 text-right font-semibold">
                        {{ sale.total_amount | currency: (sale.currency || 'NGN') : 'symbol' : '1.0-0' }}
                      </td>
                      <td class="px-3 py-2.5">
                        <span
                          class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                          [class.bg-green-100]="sale.status === 'completed'"
                          [class.text-green-700]="sale.status === 'completed'"
                          [class.bg-red-100]="sale.status === 'voided'"
                          [class.text-red-700]="sale.status === 'voided'"
                          [class.bg-yellow-100]="sale.status === 'pending'"
                          [class.text-yellow-700]="sale.status === 'pending'"
                        >{{ sale.status }}</span>
                      </td>
                      <td class="px-3 py-2.5 text-center">
                        <div class="flex items-center justify-center gap-1">
                          @if (sale.status !== 'voided') {
                            <button data-testid="edit-sale-btn" (click)="openEditDialog(sale)" class="rounded p-1.5 text-muted transition-colors hover:bg-blue-50 hover:text-secondary" title="Edit sale" type="button">
                              <i class="pi pi-pencil text-xs"></i>
                            </button>
                            <button data-testid="void-sale-btn" (click)="openVoidDialog(sale)" class="rounded p-1.5 text-muted transition-colors hover:bg-red-50 hover:text-danger" title="Void sale" type="button">
                              <i class="pi pi-trash text-xs"></i>
                            </button>
                          }
                          <button data-testid="audit-sale-btn" (click)="openAuditDialog(sale)" class="rounded p-1.5 text-muted transition-colors hover:bg-gray-100 hover:text-text" title="View audit trail" type="button">
                            <i class="pi pi-clock text-xs"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                  } @empty {
                    <tr>
                      <td colspan="6" class="px-3 py-10 text-center text-sm text-muted">
                        <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                        No sales recorded yet
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>
      }

      <!-- All Sales Tab -->
      @if (activeTab() === 'all') {
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
                <i class="pi pi-list text-sm text-success"></i>
              </div>
              <h3 class="text-base font-semibold text-text">All Sales</h3>
            </div>
            @if (history().length > 0) {
              <button
                (click)="exportSalesCsv()"
                class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
              >
                <i class="pi pi-download text-xs"></i> Export CSV
              </button>
            }
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">All sales records</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Date</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Product</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Qty</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Total</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Status</th>
                  <th class="px-3 py-2.5 text-center text-xs font-semibold uppercase text-muted">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (sale of history(); track sale.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 text-muted">{{ sale.sale_date | date: 'mediumDate' }}</td>
                    <td class="px-3 py-2.5 font-medium">{{ getProductName(sale.product_id) }}</td>
                    <td class="px-3 py-2.5 text-right">{{ sale.quantity }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold">
                      {{ sale.total_amount | currency: (sale.currency || 'NGN') : 'symbol' : '1.0-0' }}
                    </td>
                    <td class="px-3 py-2.5">
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                        [class.bg-green-100]="sale.status === 'completed'"
                        [class.text-green-700]="sale.status === 'completed'"
                        [class.bg-red-100]="sale.status === 'voided'"
                        [class.text-red-700]="sale.status === 'voided'"
                        [class.bg-yellow-100]="sale.status === 'pending'"
                        [class.text-yellow-700]="sale.status === 'pending'"
                      >{{ sale.status }}</span>
                    </td>
                    <td class="px-3 py-2.5 text-center">
                      <div class="flex items-center justify-center gap-1">
                        @if (sale.status !== 'voided') {
                          <button data-testid="edit-sale-btn" (click)="openEditDialog(sale)" class="rounded p-1.5 text-muted transition-colors hover:bg-blue-50 hover:text-secondary" title="Edit sale" type="button">
                            <i class="pi pi-pencil text-xs"></i>
                          </button>
                          <button data-testid="void-sale-btn" (click)="openVoidDialog(sale)" class="rounded p-1.5 text-muted transition-colors hover:bg-red-50 hover:text-danger" title="Void sale" type="button">
                            <i class="pi pi-trash text-xs"></i>
                          </button>
                        }
                        <button data-testid="audit-sale-btn" (click)="openAuditDialog(sale)" class="rounded p-1.5 text-muted transition-colors hover:bg-gray-100 hover:text-text" title="View audit trail" type="button">
                          <i class="pi pi-clock text-xs"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="6" class="px-3 py-10 text-center text-sm text-muted">
                      <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                      No sales recorded yet
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }

      <!-- Upload CSV Tab -->
      @if (activeTab() === 'upload') {
        <div class="mx-auto max-w-2xl">
          <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div class="mb-5 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
                <i class="pi pi-upload text-sm text-purple-600"></i>
              </div>
              <h3 class="text-base font-semibold text-text">Upload CSV</h3>
            </div>

            <p class="mb-4 text-sm text-muted">
              Upload a CSV file to bulk-import sales records. The file must include the required headers.
            </p>

            <!-- Download Template Link -->
            <div class="mb-5">
              <a
                data-testid="download-template-link"
                (click)="downloadTemplate()"
                class="inline-flex cursor-pointer items-center gap-1.5 text-sm font-medium text-primary hover:text-primary/80 hover:underline"
              >
                <i class="pi pi-download text-xs"></i>
                Download Template
              </a>
            </div>

            <!-- File Picker -->
            <div class="mb-5">
              <label for="sales-csv-file" class="mb-1.5 block text-xs font-medium text-muted">CSV File</label>
              <input
                id="sales-csv-file"
                type="file"
                accept=".csv"
                data-testid="csv-file-input"
                (change)="onFileSelected($event)"
                class="block w-full text-sm text-muted file:mr-4 file:rounded-lg file:border-0 file:bg-primary/10 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-primary hover:file:bg-primary/20"
              />
              @if (selectedFile()) {
                <p class="mt-1.5 text-xs text-muted">
                  Selected: {{ selectedFile()!.name }} ({{ formatFileSize(selectedFile()!.size) }})
                </p>
              }
            </div>

            <!-- Upload Button -->
            <button
              (click)="uploadCsv()"
              [disabled]="!selectedFile() || uploading()"
              data-testid="upload-csv-btn"
              class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
            >
              @if (uploading()) {
                <i class="pi pi-spinner pi-spin text-sm"></i>
                Uploading...
              } @else {
                <i class="pi pi-upload text-sm"></i>
                Upload CSV
              }
            </button>

            <!-- Upload Results -->
            @if (uploadResult()) {
              <div class="mt-6" data-testid="upload-results">
                <h4 class="mb-3 text-sm font-semibold text-text">Upload Results</h4>
                <div class="rounded-lg border p-4"
                  [class.border-green-200]="uploadResult()!.status === 'completed'"
                  [class.bg-green-50]="uploadResult()!.status === 'completed'"
                  [class.border-yellow-200]="uploadResult()!.status === 'partial'"
                  [class.bg-yellow-50]="uploadResult()!.status === 'partial'"
                  [class.border-red-200]="uploadResult()!.status === 'failed'"
                  [class.bg-red-50]="uploadResult()!.status === 'failed'"
                >
                  <p class="text-sm font-medium"
                    [class.text-green-800]="uploadResult()!.status === 'completed'"
                    [class.text-yellow-800]="uploadResult()!.status === 'partial'"
                    [class.text-red-800]="uploadResult()!.status === 'failed'"
                  >
                    {{ uploadResult()!.message }}
                  </p>
                </div>
              </div>
            }

            <!-- Upload Error -->
            @if (uploadError()) {
              <div class="mt-6" data-testid="upload-error">
                <div class="rounded-lg border border-red-200 bg-red-50 p-4">
                  <p class="text-sm font-medium text-red-800">{{ uploadError() }}</p>
                </div>
              </div>
            }
          </div>
        </div>
      }
    </div>

    <!-- Edit Sale Dialog -->
    <p-dialog
      header="Edit Sale"
      [(visible)]="editDialogVisible"
      [modal]="true"
      [style]="{ width: '450px' }"
    >
      @if (editingSale()) {
        <div class="space-y-4">
          <div>
            <label for="edit-sale-quantity" class="mb-1.5 block text-xs font-medium text-muted">Quantity</label>
            <input
              id="edit-sale-quantity"
              type="number"
              [(ngModel)]="editForm.quantity"
              min="1"
              data-testid="edit-quantity-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="edit-sale-unit-price" class="mb-1.5 block text-xs font-medium text-muted">Unit Price</label>
            <input
              id="edit-sale-unit-price"
              type="number"
              [(ngModel)]="editForm.unit_price"
              min="0"
              step="0.01"
              data-testid="edit-price-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="edit-sale-channel" class="mb-1.5 block text-xs font-medium text-muted">Channel</label>
            <select
              id="edit-sale-channel"
              [(ngModel)]="editForm.channel"
              data-testid="edit-channel-select"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="online">Online</option>
              <option value="retail">Retail</option>
              <option value="wholesale">Wholesale</option>
            </select>
          </div>
          <div>
            <label for="edit-sale-notes" class="mb-1.5 block text-xs font-medium text-muted">Notes</label>
            <textarea
              id="edit-sale-notes"
              [(ngModel)]="editForm.notes"
              rows="3"
              data-testid="edit-notes-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              placeholder="Optional notes..."
            ></textarea>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button
              (click)="editDialogVisible = false"
              class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50"
              type="button"
            >
              Cancel
            </button>
            <button
              (click)="submitEdit()"
              [disabled]="saving()"
              data-testid="save-edit-btn"
              class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
            >
              @if (saving()) {
                <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
              } @else {
                <i class="pi pi-check text-sm"></i> Save Changes
              }
            </button>
          </div>
        </div>
      }
    </p-dialog>

    <!-- Void Sale Confirmation Dialog -->
    <p-dialog
      header="Void Sale"
      [(visible)]="voidDialogVisible"
      [modal]="true"
      [style]="{ width: '420px' }"
    >
      @if (voidingSale()) {
        <div class="space-y-4">
          <div class="rounded-lg border border-red-200 bg-red-50 p-3">
            <p class="text-sm font-medium text-red-800">
              Are you sure you want to void this sale? This will reverse the inventory deduction.
            </p>
          </div>
          <div class="rounded-lg bg-gray-50 p-3 text-sm">
            <p><span class="font-medium text-muted">Product:</span> {{ getProductName(voidingSale()!.product_id) }}</p>
            <p><span class="font-medium text-muted">Quantity:</span> {{ voidingSale()!.quantity }}</p>
            <p><span class="font-medium text-muted">Total:</span> {{ voidingSale()!.total_amount | currency: (voidingSale()!.currency || 'NGN') : 'symbol' : '1.0-0' }}</p>
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Reason for voiding</label>
            <textarea
              [(ngModel)]="voidReason"
              rows="2"
              data-testid="void-reason-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              placeholder="Enter reason..."
            ></textarea>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button
              (click)="voidDialogVisible = false"
              class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50"
              type="button"
            >
              Cancel
            </button>
            <button
              (click)="submitVoid()"
              [disabled]="saving()"
              data-testid="confirm-void-btn"
              class="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-red-700 disabled:opacity-50"
            >
              @if (saving()) {
                <i class="pi pi-spinner pi-spin text-sm"></i> Voiding...
              } @else {
                <i class="pi pi-trash text-sm"></i> Void Sale
              }
            </button>
          </div>
        </div>
      }
    </p-dialog>

    <!-- Audit Trail Dialog -->
    <p-dialog
      header="Audit Trail"
      [(visible)]="auditDialogVisible"
      [modal]="true"
      [style]="{ width: '550px' }"
    >
      <div class="space-y-3">
        @if (auditLoading()) {
          <div class="py-6 text-center text-muted">
            <i class="pi pi-spinner pi-spin text-xl"></i>
            <p class="mt-2 text-sm">Loading audit trail...</p>
          </div>
        } @else {
          @for (entry of auditEntries(); track entry.id) {
            <div
              class="rounded-lg border border-gray-200 p-3"
              data-testid="audit-entry"
            >
              <div class="flex items-center justify-between">
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                  [class.bg-green-100]="entry.action === 'created'"
                  [class.text-green-700]="entry.action === 'created'"
                  [class.bg-blue-100]="entry.action === 'updated'"
                  [class.text-blue-700]="entry.action === 'updated'"
                  [class.bg-red-100]="entry.action === 'voided'"
                  [class.text-red-700]="entry.action === 'voided'"
                >
                  {{ entry.action }}
                </span>
                <span class="text-xs text-muted">{{ entry.created_at | date: 'medium' }}</span>
              </div>
              @if (entry.reason) {
                <p class="mt-1.5 text-xs text-muted"><span class="font-medium">Reason:</span> {{ entry.reason }}</p>
              }
              @if (entry.field_changes) {
                <div class="mt-2 space-y-1">
                  @for (key of objectKeys(entry.field_changes); track key) {
                    <div class="flex items-center gap-2 text-xs">
                      <span class="font-medium text-muted">{{ key }}:</span>
                      <span class="text-red-600 line-through">{{ entry.field_changes[key].old }}</span>
                      <i class="pi pi-arrow-right text-[10px] text-muted"></i>
                      <span class="font-medium text-green-700">{{ entry.field_changes[key].new }}</span>
                    </div>
                  }
                </div>
              }
            </div>
          } @empty {
            <div class="py-6 text-center text-sm text-muted">
              <i class="pi pi-clock mb-2 block text-2xl text-gray-300"></i>
              No audit entries found
            </div>
          }
        }
      </div>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SalesPageComponent implements OnInit {
  private readonly salesService = inject(SalesService);
  private readonly productsService = inject(ProductsService);
  private readonly inventoryService = inject(InventoryService);
  private readonly messageService = inject(MessageService);

  products = signal<Product[]>([]);
  history = signal<SaleRecord[]>([]);
  entryRows = signal<EntryRow[]>([this.newRow()]);
  submitting = signal(false);
  saving = signal(false);
  stockMap = signal<Map<string, number>>(new Map());
  productMap = signal<Map<string, string>>(new Map());

  // Tab state
  activeTab = signal<'record' | 'all' | 'upload'>('record');

  // CSV upload state
  selectedFile = signal<File | null>(null);
  uploading = signal(false);
  uploadResult = signal<BulkUploadResponse | null>(null);
  uploadError = signal<string | null>(null);

  // Edit dialog state
  editDialogVisible = false;
  editingsale = signal<SaleRecord | null>(null);
  editForm: SaleUpdatePayload = {};

  // Void dialog state
  voidDialogVisible = false;
  voidingSaleRecord = signal<SaleRecord | null>(null);
  voidReason = '';

  // Audit dialog state
  auditDialogVisible = false;
  auditEntries = signal<AuditEntry[]>([]);
  auditLoading = signal(false);

  hasStockExceeded = computed(() => {
    const map = this.stockMap();
    return this.entryRows().some((row) => {
      if (!row.product_id) return false;
      const available = map.get(row.product_id);
      return available !== undefined && row.quantity > available;
    });
  });

  // Signal-based accessors for the template
  editingSale = this.editingsale;
  voidingSale = this.voidingSaleRecord;

  ngOnInit(): void {
    this.productsService.getAll().subscribe({
      next: (p) => {
        this.products.set(p);
        const map = new Map<string, string>();
        p.forEach((prod) => map.set(prod.id, prod.name));
        this.productMap.set(map);
      },
    });
    this.loadHistory();
    this.loadInventory();
  }

  private loadInventory(): void {
    this.inventoryService.getCurrent().subscribe({
      next: (items) => {
        const map = new Map<string, number>();
        items.forEach((item) => map.set(item.product_id, item.current_stock));
        this.stockMap.set(map);
      },
    });
  }

  getStock(productId: string): number | undefined {
    if (!productId) return undefined;
    return this.stockMap().get(productId);
  }

  getProductName(productId: string): string {
    return this.productMap().get(productId) || 'Unknown';
  }

  exceedsStock(row: EntryRow): boolean {
    if (!row.product_id) return false;
    const available = this.stockMap().get(row.product_id);
    return available !== undefined && row.quantity > available;
  }

  onProductChange(row: EntryRow): void {
    if (!row.product_id) {
      row.unit_price = null;
      return;
    }
    const product = this.products().find((p) => p.id === row.product_id);
    row.unit_price = product ? product.selling_price : null;
  }

  lineTotal(row: EntryRow): number {
    const price = row.unit_price ?? 0;
    const discount = row.discount_amount ?? 0;
    return price * row.quantity - discount;
  }

  objectKeys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj);
  }

  private newRow(): EntryRow {
    return {
      product_id: '',
      quantity: 1,
      sale_date: new Date().toISOString().split('T')[0],
      unit_price: null,
      discount_amount: null,
    };
  }

  addRow(): void {
    this.entryRows.update((rows) => [...rows, this.newRow()]);
  }

  removeRow(index: number): void {
    this.entryRows.update((rows) => rows.filter((_, i) => i !== index));
  }

  submitEntries(): void {
    const valid = this.entryRows()
      .filter((r) => r.product_id && r.quantity > 0)
      .map((r) => ({
        product_id: r.product_id,
        quantity: r.quantity,
        sale_date: r.sale_date,
        discount_amount: r.discount_amount ?? null,
      }));
    if (valid.length === 0) return;

    this.submitting.set(true);
    this.salesService.createDailyEntry(valid).subscribe({
      next: () => {
        this.submitting.set(false);
        this.entryRows.set([this.newRow()]);
        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: 'Sales recorded successfully',
        });
        this.loadHistory();
        this.loadInventory();
      },
      error: () => {
        this.submitting.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to record sales',
        });
      },
    });
  }

  // ---- Edit ----

  openEditDialog(sale: SaleRecord): void {
    this.editingsale.set(sale);
    this.editForm = {
      quantity: sale.quantity,
      // parseFloat strips trailing zeros from Decimal strings (e.g. "5000.000000" → 5000)
      unit_price: parseFloat(String(sale.unit_price ?? 0)),
      channel: sale.channel,
      notes: sale.notes || '',
    };
    this.editDialogVisible = true;
  }

  submitEdit(): void {
    const sale = this.editingsale();
    if (!sale) return;

    this.saving.set(true);
    this.salesService.update(sale.id, this.editForm).subscribe({
      next: () => {
        this.saving.set(false);
        this.editDialogVisible = false;
        this.editingsale.set(null);
        this.messageService.add({
          severity: 'success',
          summary: 'Updated',
          detail: 'Sale updated successfully',
        });
        this.loadHistory();
        this.loadInventory();
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to update sale',
        });
      },
    });
  }

  // ---- Void ----

  openVoidDialog(sale: SaleRecord): void {
    this.voidingSaleRecord.set(sale);
    this.voidReason = '';
    this.voidDialogVisible = true;
  }

  submitVoid(): void {
    const sale = this.voidingSaleRecord();
    if (!sale) return;

    this.saving.set(true);
    const reason = this.voidReason.trim() || 'No reason provided';
    this.salesService.voidSale(sale.id, reason).subscribe({
      next: () => {
        this.saving.set(false);
        this.voidDialogVisible = false;
        this.voidingSaleRecord.set(null);
        this.messageService.add({
          severity: 'success',
          summary: 'Voided',
          detail: 'Sale voided and inventory restored',
        });
        this.loadHistory();
        this.loadInventory();
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to void sale',
        });
      },
    });
  }

  // ---- Audit Trail ----

  openAuditDialog(sale: SaleRecord): void {
    this.auditEntries.set([]);
    this.auditLoading.set(true);
    this.auditDialogVisible = true;

    this.salesService.getAuditTrail(sale.id).subscribe({
      next: (entries) => {
        this.auditEntries.set(entries);
        this.auditLoading.set(false);
      },
      error: () => {
        this.auditLoading.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to load audit trail',
        });
      },
    });
  }

  // ---- CSV Upload ----

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.selectedFile.set(file);
    this.uploadResult.set(null);
    this.uploadError.set(null);
  }

  downloadTemplate(): void {
    const csvContent = 'product_id,quantity,unit_price,sale_date,channel\n';
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sales_upload_template.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  uploadCsv(): void {
    const file = this.selectedFile();
    if (!file) return;

    this.uploading.set(true);
    this.uploadResult.set(null);
    this.uploadError.set(null);

    this.salesService.uploadCsv(file).subscribe({
      next: (result) => {
        this.uploading.set(false);
        this.uploadResult.set(result);
        this.selectedFile.set(null);

        if (result.status === 'completed') {
          this.messageService.add({
            severity: 'success',
            summary: 'Upload Complete',
            detail: result.message,
          });
          // Auto-switch to All Sales tab and reload
          this.activeTab.set('all');
          this.loadHistory();
          this.loadInventory();
        } else if (result.status === 'partial') {
          this.messageService.add({
            severity: 'warn',
            summary: 'Partial Upload',
            detail: result.message,
          });
          this.loadHistory();
          this.loadInventory();
        } else {
          this.messageService.add({
            severity: 'error',
            summary: 'Upload Failed',
            detail: result.message,
          });
        }
      },
      error: (err) => {
        this.uploading.set(false);
        const detail = err?.error?.detail || 'Failed to upload CSV file';
        this.uploadError.set(detail);
        this.messageService.add({
          severity: 'error',
          summary: 'Upload Error',
          detail,
        });
      },
    });
  }

  exportSalesCsv(): void {
    const rows = this.history();
    if (rows.length === 0) return;
    const header = 'Date,Product,Qty,Total,Status';
    const lines = rows.map(
      (s) =>
        `${s.sale_date},${this.getProductName(s.product_id).replace(/,/g, ' ')},${s.quantity},${s.total_amount},${s.status}`,
    );
    const csv = [header, ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sales_export.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  private loadHistory(): void {
    this.salesService.listSales({ page_size: '20' }).subscribe({
      next: (r) => this.history.set(r.items ?? []),
    });
  }
}
