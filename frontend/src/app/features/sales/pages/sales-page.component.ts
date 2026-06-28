import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, CurrencyPipe } from '@angular/common';
import { Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  SalesService,
  SaleRecord,
  SaleTransaction,
  AuditEntry,
  SaleUpdatePayload,
  BulkUploadResponse,
  QuickQuote,
} from '../../../core/services/sales.service';
import { ProductsService, Product } from '../../../core/services/products.service';
import { InventoryService } from '../../../core/services/inventory.service';
import { CustomerService, Customer } from '../../../core/services/customer.service';

interface EntryRow {
  product_id: string;
  quantity: number;
  unit_price: number | null;
  discount_amount: number | null;
}

interface TransactionMeta {
  customer_id: string;
  payment_method: string;
  payment_amount: number | null;
  payment_date: string | null;
  payment_status: string;
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
            data-testid="tab-all-sales"
            (click)="activeTab.set('all')"
            [attr.aria-selected]="activeTab() === 'all'"
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
            [attr.aria-selected]="activeTab() === 'upload'"
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
          <button
            type="button"
            data-testid="tab-quick-quote"
            (click)="activeTab.set('quick-quote')"
            [attr.aria-selected]="activeTab() === 'quick-quote'"
            class="whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors"
            [class.border-primary]="activeTab() === 'quick-quote'"
            [class.text-primary]="activeTab() === 'quick-quote'"
            [class.border-transparent]="activeTab() !== 'quick-quote'"
            [class.text-muted]="activeTab() !== 'quick-quote'"
            [class.hover:border-gray-300]="activeTab() !== 'quick-quote'"
            [class.hover:text-text]="activeTab() !== 'quick-quote'"
          >
            <i class="pi pi-calculator mr-1.5 text-xs"></i>
            Quick Quote
          </button>
          <button
            type="button"
            data-testid="tab-record-sales"
            (click)="activeTab.set('record')"
            [attr.aria-selected]="activeTab() === 'record'"
            class="whitespace-nowrap border-b-2 px-1 py-3 text-sm font-medium transition-colors"
            [class.border-primary]="activeTab() === 'record'"
            [class.text-primary]="activeTab() === 'record'"
            [class.border-transparent]="activeTab() !== 'record'"
            [class.text-muted]="activeTab() !== 'record'"
            [class.hover:border-gray-300]="activeTab() !== 'record'"
            [class.hover:text-text]="activeTab() !== 'record'"
          >
            <i class="pi pi-plus-circle mr-1.5 text-xs"></i>
            Add Sale
          </button>
        </nav>
      </div>

      <!-- Record Sales Tab -->
      @if (activeTab() === 'record') {
        <div class="mx-auto max-w-3xl">
        <div data-testid="add-sale-form-card" class="rounded-xl border border-gray-200 bg-white shadow-sm">

          <!-- Card header -->
          <div class="flex items-center gap-3 border-b border-gray-100 px-6 py-4">
            <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10">
              <i class="pi pi-shopping-cart text-sm text-primary"></i>
            </div>
            <div>
              <h3 class="text-base font-semibold text-text">New Sale</h3>
              <p class="text-xs text-muted">Add products, set quantities and discounts, then record</p>
            </div>
          </div>

          <!-- Top meta: Date + Customer -->
          <div class="grid grid-cols-2 gap-4 border-b border-gray-100 px-5 py-4">
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">Sale Date</label>
              <input
                type="date"
                [ngModel]="saleDate()"
                (ngModelChange)="saleDate.set($event)"
                name="sale_date"
                class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label class="mb-1 block text-xs font-medium text-muted">Customer</label>
              <div class="flex gap-2">
                <select
                  [(ngModel)]="txnMeta.customer_id"
                  name="customer_id"
                  (change)="onCustomerSelected()"
                  class="min-w-0 flex-1 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                >
                  <option value="">— Select —</option>
                  @for (c of customers(); track c.id) {
                    <option [value]="c.id">{{ c.name }}{{ c.contact_number ? ' · ' + c.contact_number : '' }}</option>
                  }
                </select>
                <button
                  type="button"
                  (click)="newCustomerDialogVisible = true"
                  title="Add new customer"
                  class="flex shrink-0 items-center gap-1 rounded-lg border border-primary/40 bg-white px-2.5 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/5"
                >
                  <i class="pi pi-plus text-xs"></i> New
                </button>
              </div>
            </div>
          </div>

          <!-- Products section header + Add button -->
          <div class="flex items-center justify-between border-b border-gray-100 px-5 py-2.5">
            <span class="text-[11px] font-semibold uppercase tracking-wide text-muted">Products</span>
            <button
              (click)="addRow()"
              class="flex items-center gap-1 rounded-lg border border-dashed border-primary/40 px-2.5 py-1.5 text-xs font-medium text-primary transition-colors hover:border-primary hover:bg-primary/5"
              type="button"
            >
              <i class="pi pi-plus text-[10px]"></i> Add Product
            </button>
          </div>

          <!-- Column headers -->
          <div class="flex items-center gap-2 bg-gray-50/60 px-5 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
            <div class="min-w-0 flex-1">Product</div>
            <div class="w-14 shrink-0 text-right">Qty</div>
            <div class="w-24 shrink-0 text-right">Unit Price</div>
            <div class="w-20 shrink-0 text-right">Discount</div>
            <div class="w-24 shrink-0 text-right">Total</div>
            <div class="w-6 shrink-0"></div>
          </div>

          <!-- Product rows — compact inline -->
          <div class="divide-y divide-gray-50">
            @for (row of entryRows(); track $index) {
              <div class="px-5 py-2" [class.bg-red-50]="exceedsStock(row)">
                <!-- items-start so fixed-height stock slot below product doesn't shift other cells -->
                <div class="flex items-start gap-2">

                  <!-- Product dropdown + fixed-height stock slot (row height stays constant) -->
                  <div class="min-w-0 flex-1">
                    <select
                      [(ngModel)]="row.product_id"
                      [name]="'product_' + $index"
                      (change)="onProductChange(row)"
                      class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm font-medium text-text transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    >
                      <option value="">Select product</option>
                      @for (p of products(); track p.id) {
                        <option [value]="p.id">{{ p.name }}</option>
                      }
                    </select>
                    <!-- Fixed slot — always h-3.5 so all rows are the same height -->
                    <div class="h-3.5 mt-0.5">
                      @if (exceedsStock(row)) {
                        <p data-testid="stock-warning" class="text-[10px] font-medium leading-none text-red-600">Exceeds stock</p>
                      } @else if (row.product_id && getStock(row.product_id) !== undefined) {
                        <span
                          data-testid="stock-indicator"
                          class="text-[10px] font-medium leading-none text-muted"
                        >{{ getStock(row.product_id) }} in stock</span>
                      }
                    </div>
                  </div>

                  <!-- Qty -->
                  <input
                    type="number"
                    [(ngModel)]="row.quantity"
                    (ngModelChange)="refreshRows()"
                    [name]="'qty_' + $index"
                    min="1"
                    class="h-8 w-14 shrink-0 rounded border px-2 text-right text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    [class.border-red-400]="exceedsStock(row)"
                    [class.border-gray-300]="!exceedsStock(row)"
                  />

                  <!-- Unit Price (read-only) -->
                  <div
                    data-testid="entry-price-input"
                    class="flex h-8 w-24 shrink-0 items-center justify-end rounded border border-gray-200 bg-gray-50 px-2 text-sm text-text"
                  >
                    @if (row.unit_price !== null) {
                      {{ row.unit_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                    } @else {
                      <span class="text-muted">—</span>
                    }
                  </div>

                  <!-- Discount -->
                  <input
                    type="number"
                    [(ngModel)]="row.discount_amount"
                    (ngModelChange)="refreshRows()"
                    [name]="'discount_' + $index"
                    min="0"
                    step="0.01"
                    data-testid="entry-discount-input"
                    placeholder="0"
                    class="h-8 w-20 shrink-0 rounded border border-gray-300 px-2 text-right text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  />

                  <!-- Line Total -->
                  <div
                    data-testid="entry-line-total"
                    class="flex h-8 w-24 shrink-0 items-center justify-end rounded border border-gray-200 bg-gray-50 px-2 text-sm font-semibold text-text"
                  >
                    {{ lineTotal(row) | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </div>

                  <!-- Remove -->
                  @if (entryRows().length > 1) {
                    <button
                      (click)="removeRow($index)"
                      class="flex h-8 w-6 shrink-0 items-center justify-center rounded text-muted transition-colors hover:bg-red-50 hover:text-danger"
                      type="button"
                      title="Remove row"
                    >
                      <i class="pi pi-times text-[10px]"></i>
                    </button>
                  } @else {
                    <div class="w-6 shrink-0"></div>
                  }

                </div>
              </div>
            }
          </div>

          <!-- Grand total — value aligned with the Total column -->
          <div class="flex items-center gap-2 border-t-2 border-gray-200 bg-gray-50/60 px-5 py-2.5">
            <div class="min-w-0 flex-1"></div>
            <div class="w-14 shrink-0"></div>
            <div class="w-24 shrink-0"></div>
            <div class="w-20 shrink-0 text-right text-xs font-semibold text-text">Grand Total</div>
            <div class="w-24 shrink-0 text-right text-sm font-bold text-primary">{{ grandTotal() | currency: 'NGN' : 'symbol' : '1.0-0' }}</div>
            <div class="w-6 shrink-0"></div>
          </div>

          <!-- Payment & submit footer -->
          <div class="border-t border-gray-200 bg-gray-50/40 px-5 py-4">
            <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <!-- Payment Method -->
              <div>
                <label class="mb-1 block text-xs font-medium text-muted">Payment Method</label>
                <select
                  [(ngModel)]="txnMeta.payment_method"
                  name="payment_method"
                  class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                >
                  <option value="">— Select —</option>
                  <option value="cash">Cash</option>
                  <option value="transfer">Bank Transfer</option>
                  <option value="pos">POS</option>
                  <option value="credit">Credit</option>
                  <option value="cheque">Cheque</option>
                </select>
              </div>

              <!-- Payment Amount -->
              <div>
                <label class="mb-1 block text-xs font-medium text-muted">Amount Paid (₦)</label>
                <input
                  type="number"
                  [(ngModel)]="txnMeta.payment_amount"
                  name="payment_amount"
                  min="0"
                  step="0.01"
                  placeholder="0.00"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-right text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              <!-- Payment Date -->
              <div>
                <label class="mb-1 block text-xs font-medium text-muted">Payment Date</label>
                <input
                  type="date"
                  [(ngModel)]="txnMeta.payment_date"
                  name="payment_date"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              <!-- Payment Status -->
              <div>
                <label class="mb-1 block text-xs font-medium text-muted">Payment Status</label>
                <select
                  [(ngModel)]="txnMeta.payment_status"
                  name="payment_status"
                  class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                >
                  <option value="paid">Paid</option>
                  <option value="partial">Partial</option>
                  <option value="credit">Credit (Owed)</option>
                </select>
              </div>
            </div>

            <!-- Submit -->
            <div class="mt-4 flex items-center justify-end">
              <button
                (click)="submitEntries()"
                [disabled]="submitting() || hasStockExceeded()"
                class="flex items-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
              >
                @if (submitting()) {
                  <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
                } @else {
                  <i class="pi pi-check text-sm"></i> Record Sales
                }
              </button>
            </div>
          </div>

        </div>
        </div>
      }

      <!-- All Sales Tab — grouped transactions -->
      @if (activeTab() === 'all') {
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center justify-between">
            <div class="flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
                <i class="pi pi-list text-sm text-success"></i>
              </div>
              <h3 class="text-base font-semibold text-text">All Sales</h3>
            </div>
            <button
              type="button"
              data-testid="export-sales-csv"
              (click)="exportSalesCsv()"
              class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
            >
              <i class="pi pi-download text-xs"></i>
              Export CSV
            </button>
            <button
              type="button"
              data-testid="add-sale-btn"
              (click)="activeTab.set('record')"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90"
            >
              <i class="pi pi-plus text-xs"></i>
              Add Sale
            </button>
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">All sales transactions</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Date</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Invoice No.</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Customer</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Contact</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Payment Status</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Total Amount</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Method</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Total Paid</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Sale Due</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Items</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (txn of transactions(); track txn.transaction_id) {
                  <tr
                    data-testid="transaction-row"
                    class="cursor-pointer transition-colors hover:bg-gray-50/50"
                    (click)="openTransactionDetail(txn)"
                    title="Click to view product details"
                  >
                    <td class="whitespace-nowrap px-3 py-2.5 text-muted">{{ txn.sale_date | date: 'mediumDate' }}</td>
                    <td class="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-secondary">{{ invoiceNo(txn.transaction_id) }}</td>
                    <td class="px-3 py-2.5 font-medium text-text">{{ txn.customer_name || '—' }}</td>
                    <td class="whitespace-nowrap px-3 py-2.5 text-muted">{{ txn.contact_number || '—' }}</td>
                    <td class="px-3 py-2.5">
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                        [class.bg-green-100]="txn.payment_status === 'paid' || !txn.payment_status"
                        [class.text-green-700]="txn.payment_status === 'paid' || !txn.payment_status"
                        [class.bg-amber-100]="txn.payment_status === 'credit'"
                        [class.text-amber-700]="txn.payment_status === 'credit'"
                      >{{ txn.payment_status || 'paid' }}</span>
                    </td>
                    <td class="whitespace-nowrap px-3 py-2.5 text-right font-semibold">
                      {{ txn.total_amount | currency: (txn.currency || 'NGN') : 'symbol' : '1.0-0' }}
                    </td>
                    <td class="px-3 py-2.5 text-muted">{{ formatPaymentMethod(txn.payment_method) }}</td>
                    <td class="whitespace-nowrap px-3 py-2.5 text-right font-medium text-success">
                      {{ txn.total_paid | currency: (txn.currency || 'NGN') : 'symbol' : '1.0-0' }}
                    </td>
                    <td class="whitespace-nowrap px-3 py-2.5 text-right font-medium"
                      [class.text-danger]="txn.sale_due > 0"
                      [class.text-muted]="txn.sale_due <= 0"
                    >
                      {{ txn.sale_due | currency: (txn.currency || 'NGN') : 'symbol' : '1.0-0' }}
                    </td>
                    <td class="px-3 py-2.5 text-right text-muted">{{ txn.item_count }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="10" class="px-3 py-10 text-center text-sm text-muted">
                      <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                      No transactions recorded yet
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

      <!-- Quick Quote Tab -->
      @if (activeTab() === 'quick-quote') {
        <div class="mx-auto max-w-lg">
          <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <div class="mb-5 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
                <i class="pi pi-calculator text-sm text-amber-600"></i>
              </div>
              <h3 class="text-base font-semibold text-text">Quick Quote</h3>
            </div>
            <p class="mb-5 text-sm text-muted">
              Calculate the minimum sell price for a product using FIFO landed cost.
            </p>

            <div class="space-y-4">
              <div>
                <label for="qq-product" class="mb-1.5 block text-xs font-medium text-muted">Product</label>
                <select
                  id="qq-product"
                  data-testid="quick-quote-product-select"
                  [(ngModel)]="qqProductId"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                >
                  <option value="">Select product</option>
                  @for (p of products(); track p.id) {
                    <option [value]="p.id">{{ p.name }}</option>
                  }
                </select>
              </div>

              <div>
                <label for="qq-qty" class="mb-1.5 block text-xs font-medium text-muted">Quantity</label>
                <input
                  id="qq-qty"
                  type="number"
                  min="1"
                  data-testid="quick-quote-qty-input"
                  [(ngModel)]="qqQuantity"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                />
              </div>

              <button
                type="button"
                data-testid="quick-quote-calculate-btn"
                (click)="calculateQuote()"
                [disabled]="!qqProductId || qqQuantity < 1 || qqCalculating()"
                class="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                @if (qqCalculating()) { Calculating… } @else { Calculate }
              </button>
            </div>

            @if (qqResult()) {
              @if (qqResult()!.fifo_landed_cost_per_unit === 0) {
                <div
                  data-testid="qq-no-data"
                  class="mt-5 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800"
                >
                  No FIFO cost data found. Ensure the product has a delivered purchase order with remaining stock.
                </div>
              } @else {
                <div class="mt-6 space-y-3 rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <div class="flex items-center justify-between">
                    <span class="text-sm text-muted">FIFO Landed Cost / Unit</span>
                    <span data-testid="qq-fifo-cost" class="font-semibold text-text">
                      {{ qqResult()!.fifo_landed_cost_per_unit | currency: 'NGN' : 'symbol' : '1.2-2' }}
                    </span>
                  </div>
                  <div class="flex items-center justify-between">
                    <span class="text-sm text-muted">Floor Margin</span>
                    <span data-testid="qq-floor-margin" class="font-semibold text-text">
                      {{ qqResult()!.floor_margin_pct }}%
                    </span>
                  </div>
                  <div class="flex items-center justify-between border-t border-gray-200 pt-3">
                    <span class="text-sm font-semibold text-text">Min Sell Price / Unit</span>
                    <span data-testid="qq-min-price" class="text-base font-bold text-primary">
                      {{ qqResult()!.min_sell_price_per_unit | currency: 'NGN' : 'symbol' : '1.2-2' }}
                    </span>
                  </div>
                  <div class="flex items-center justify-between">
                    <span class="text-sm text-muted">Total Min Price (× {{ qqResult()!.quantity }})</span>
                    <span data-testid="qq-total-price" class="font-semibold text-text">
                      {{ qqResult()!.total_min_price | currency: 'NGN' : 'symbol' : '1.2-2' }}
                    </span>
                  </div>
                </div>
              }
            }

            @if (qqError()) {
              <div data-testid="qq-error" class="mt-4 rounded-lg border border-red-200 bg-red-50 p-3">
                <p class="text-sm text-red-700">{{ qqError() }}</p>
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
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
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
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
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

    <!-- New Customer Dialog -->
    <p-dialog
      header="Add New Customer"
      [(visible)]="newCustomerDialogVisible"
      [modal]="true"
      [style]="{ width: '420px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
    >
      <div class="space-y-4">
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Name <span class="text-danger">*</span></label>
          <input
            type="text"
            [(ngModel)]="newCustomerForm.name"
            name="new_customer_name"
            placeholder="Customer name"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Contact Number</label>
          <input
            type="text"
            [(ngModel)]="newCustomerForm.contact_number"
            name="new_customer_contact"
            placeholder="Optional"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Email</label>
          <input
            type="email"
            [(ngModel)]="newCustomerForm.email"
            name="new_customer_email"
            placeholder="Optional"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button
            (click)="newCustomerDialogVisible = false"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50"
            type="button"
          >
            Cancel
          </button>
          <button
            (click)="saveNewCustomer()"
            [disabled]="savingCustomer() || !newCustomerForm.name.trim()"
            class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
          >
            @if (savingCustomer()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
            } @else {
              <i class="pi pi-check text-sm"></i> Save Customer
            }
          </button>
        </div>
      </div>
    </p-dialog>

    <!-- Audit Trail Dialog -->
    <p-dialog
      header="Audit Trail"
      [(visible)]="auditDialogVisible"
      [modal]="true"
      [style]="{ width: '550px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
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
  private readonly customerService = inject(CustomerService);
  private readonly router = inject(Router);

  products = signal<Product[]>([]);
  history = signal<SaleRecord[]>([]);
  entryRows = signal<EntryRow[]>([this.newRow()]);
  submitting = signal(false);
  saving = signal(false);
  stockMap = signal<Map<string, number>>(new Map());
  productMap = signal<Map<string, string>>(new Map());

  // Customer state
  customers = signal<Customer[]>([]);
  newCustomerDialogVisible = false;
  newCustomerForm = { name: '', contact_number: '', email: '' };
  savingCustomer = signal(false);

  // Tab state
  activeTab = signal<'all' | 'record' | 'upload' | 'quick-quote'>('all');

  // Shared sale date for all line items in one submission
  saleDate = signal<string>(new Date().toISOString().split('T')[0]);

  // Transaction-level customer + payment meta (shared across all rows in one submission)
  txnMeta: TransactionMeta = { customer_id: '', payment_method: '', payment_amount: null, payment_date: null, payment_status: 'paid' };

  // CSV upload state
  selectedFile = signal<File | null>(null);
  uploading = signal(false);
  uploadResult = signal<BulkUploadResponse | null>(null);
  uploadError = signal<string | null>(null);

  // Transaction state
  transactions = signal<SaleTransaction[]>([]);

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

  // Quick Quote state
  qqProductId = '';
  qqQuantity = 1;
  qqResult = signal<QuickQuote | null>(null);
  qqError = signal<string | null>(null);
  qqCalculating = signal(false);

  hasStockExceeded = computed(() => {
    const map = this.stockMap();
    return this.entryRows().some((row) => {
      if (!row.product_id) return false;
      const available = map.get(row.product_id);
      return available !== undefined && row.quantity > available;
    });
  });

  grandTotal = computed(() =>
    this.entryRows().reduce((sum, row) => {
      const price = row.unit_price ?? 0;
      const discount = row.discount_amount ?? 0;
      return sum + price * row.quantity - discount;
    }, 0)
  );

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
    this.loadTransactions();
    this.loadCustomers();
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

  loadCustomers(search?: string): void {
    this.customerService.getAll(search).subscribe({
      next: (r) => this.customers.set(r.items ?? []),
      error: () => {
        // silently ignore — auth interceptor will redirect to login if needed
      },
    });
  }

  onCustomerSelected(): void {
    // Customer info is resolved server-side; nothing extra needed here.
  }

  saveNewCustomer(): void {
    const name = this.newCustomerForm.name.trim();
    if (!name) return;

    this.savingCustomer.set(true);
    this.customerService
      .create({
        name,
        contact_number: this.newCustomerForm.contact_number || null,
        email: this.newCustomerForm.email || null,
      })
      .subscribe({
        next: (created) => {
          this.savingCustomer.set(false);
          this.newCustomerDialogVisible = false;
          this.newCustomerForm = { name: '', contact_number: '', email: '' };
          this.loadCustomers();
          // Auto-select newly created customer
          this.txnMeta.customer_id = created.id;
          this.messageService.add({
            severity: 'success',
            summary: 'Customer Created',
            detail: `${created.name} added and selected`,
          });
        },
        error: () => {
          this.savingCustomer.set(false);
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to create customer',
          });
        },
      });
  }

  private loadTransactions(): void {
    this.salesService.getTransactions({ page_size: '20' }).subscribe({
      next: (r) => this.transactions.set(r.items ?? []),
    });
  }

  openTransactionDetail(txn: SaleTransaction): void {
    this.router.navigate(['/sales/transactions', txn.transaction_id]);
  }

  getStock(productId: string): number | undefined {
    if (!productId) return undefined;
    return this.stockMap().get(productId);
  }

  getProductName(productId: string): string {
    return this.productMap().get(productId) || 'Unknown';
  }

  txnProductNames(txn: SaleTransaction): string {
    const names = txn.items.map((item) => this.getProductName(item.product_id));
    if (names.length <= 2) return names.join(', ');
    return `${names[0]}, ${names[1]} and ${names.length - 2} more`;
  }

  exceedsStock(row: EntryRow): boolean {
    if (!row.product_id) return false;
    const available = this.stockMap().get(row.product_id);
    return available !== undefined && row.quantity > available;
  }

  onProductChange(row: EntryRow): void {
    if (!row.product_id) {
      row.unit_price = null;
    } else {
      const product = this.products().find((p) => p.id === row.product_id);
      row.unit_price = product ? product.selling_price : null;
    }
    // Mutating a property on the row object doesn't change the signal reference.
    // Spread the array so computed(grandTotal) re-evaluates.
    this.entryRows.update(rows => [...rows]);
  }

  refreshRows(): void {
    this.entryRows.update(rows => [...rows]);
  }

  lineTotal(row: EntryRow): number {
    const price = row.unit_price ?? 0;
    const discount = row.discount_amount ?? 0;
    return price * row.quantity - discount;
  }

  objectKeys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj);
  }

  invoiceNo(transactionId: string): string {
    return 'INV-' + transactionId.replace(/-/g, '').slice(0, 8).toUpperCase();
  }

  formatPaymentMethod(method?: string | null): string {
    if (!method) return '—';
    const map: Record<string, string> = {
      cash: 'Cash',
      card: 'Card',
      bank_transfer: 'Bank Transfer',
      other: 'Other',
    };
    return map[method] ?? method;
  }

  private newRow(): EntryRow {
    return {
      product_id: '',
      quantity: 1,
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
    const meta = this.txnMeta;
    const date = this.saleDate();
    const valid = this.entryRows()
      .filter((r) => r.product_id && r.quantity > 0)
      .map((r) => ({
        product_id: r.product_id,
        quantity: r.quantity,
        sale_date: date,
        discount_amount: r.discount_amount ?? null,
        customer_id: meta.customer_id || null,
        payment_method: meta.payment_method || null,
        payment_amount: meta.payment_amount ?? null,
        payment_date: meta.payment_date || null,
        payment_status: meta.payment_status || 'paid',
      }));
    if (valid.length === 0) return;

    this.submitting.set(true);
    this.salesService.createDailyEntry(valid).subscribe({
      next: () => {
        this.submitting.set(false);
        this.entryRows.set([this.newRow()]);
        this.txnMeta = { customer_id: '', payment_method: '', payment_amount: null, payment_date: null, payment_status: 'paid' };
        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: 'Sales recorded successfully',
        });
        this.loadHistory();
        this.loadInventory();
        this.loadTransactions();
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
        this.loadTransactions();
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
        this.loadTransactions();
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

  // ---- Quick Quote ----

  calculateQuote(): void {
    if (!this.qqProductId || this.qqQuantity < 1) return;
    this.qqResult.set(null);
    this.qqError.set(null);
    this.qqCalculating.set(true);
    this.salesService.quickQuote(this.qqProductId, this.qqQuantity).subscribe({
      next: (result) => {
        this.qqResult.set(result);
        this.qqCalculating.set(false);
      },
      error: () => {
        this.qqError.set('Failed to calculate quote. Please try again.');
        this.qqCalculating.set(false);
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
    this.salesService.exportCsv().subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'sales_export.csv';
        link.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to export sales CSV',
        });
      },
    });
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
