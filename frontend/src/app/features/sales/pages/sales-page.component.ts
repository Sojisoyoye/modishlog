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
} from '../../../core/services/sales.service';
import { ProductsService, Product } from '../../../core/services/products.service';
import { InventoryService } from '../../../core/services/inventory.service';

interface EntryRow {
  product_id: string;
  quantity: number;
  sale_date: string;
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

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
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
              <div class="flex items-end gap-3">
                <div class="flex-1">
                  @if ($index === 0) {
                    <label class="mb-1.5 block text-xs font-medium text-muted">Product</label>
                  }
                  <div class="flex items-center gap-2">
                    <select
                      [(ngModel)]="row.product_id"
                      [name]="'product_' + $index"
                      class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
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
                <div class="w-24">
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
                <div class="w-36">
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

        <!-- Sales History -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
              <i class="pi pi-history text-sm text-success"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Recent Sales</h3>
          </div>

          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Date
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Product
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Qty
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Total
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Status
                  </th>
                  <th class="px-3 py-2.5 text-center text-xs font-semibold uppercase text-muted">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (sale of history(); track sale.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 text-muted">
                      {{ sale.sale_date | date: 'mediumDate' }}
                    </td>
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
                      >
                        {{ sale.status }}
                      </span>
                    </td>
                    <td class="px-3 py-2.5 text-center">
                      <div class="flex items-center justify-center gap-1">
                        @if (sale.status !== 'voided') {
                          <button
                            data-testid="edit-sale-btn"
                            (click)="openEditDialog(sale)"
                            class="rounded p-1.5 text-muted transition-colors hover:bg-blue-50 hover:text-secondary"
                            title="Edit sale"
                            type="button"
                          >
                            <i class="pi pi-pencil text-xs"></i>
                          </button>
                          <button
                            data-testid="void-sale-btn"
                            (click)="openVoidDialog(sale)"
                            class="rounded p-1.5 text-muted transition-colors hover:bg-red-50 hover:text-danger"
                            title="Void sale"
                            type="button"
                          >
                            <i class="pi pi-trash text-xs"></i>
                          </button>
                        }
                        <button
                          data-testid="audit-sale-btn"
                          (click)="openAuditDialog(sale)"
                          class="rounded p-1.5 text-muted transition-colors hover:bg-gray-100 hover:text-text"
                          title="View audit trail"
                          type="button"
                        >
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
            <label class="mb-1.5 block text-xs font-medium text-muted">Quantity</label>
            <input
              type="number"
              [(ngModel)]="editForm.quantity"
              min="1"
              data-testid="edit-quantity-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Unit Price</label>
            <input
              type="number"
              [(ngModel)]="editForm.unit_price"
              min="0"
              step="0.01"
              data-testid="edit-price-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Channel</label>
            <select
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
            <label class="mb-1.5 block text-xs font-medium text-muted">Notes</label>
            <textarea
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

  objectKeys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj);
  }

  private newRow(): EntryRow {
    return { product_id: '', quantity: 1, sale_date: new Date().toISOString().split('T')[0] };
  }

  addRow(): void {
    this.entryRows.update((rows) => [...rows, this.newRow()]);
  }

  removeRow(index: number): void {
    this.entryRows.update((rows) => rows.filter((_, i) => i !== index));
  }

  submitEntries(): void {
    const valid = this.entryRows().filter((r) => r.product_id && r.quantity > 0);
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
      unit_price: sale.unit_price,
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

  private loadHistory(): void {
    this.salesService.listSales({ page_size: '20' }).subscribe({
      next: (r) => this.history.set(r.items ?? []),
    });
  }
}
