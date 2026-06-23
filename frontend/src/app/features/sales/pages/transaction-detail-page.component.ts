import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CurrencyPipe, DatePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  SalesService,
  SaleRecord,
  SaleTransaction,
  SaleTransactionItem,
  AuditEntry,
  SaleUpdatePayload,
  SaleTransactionUpdatePayload,
} from '../../../core/services/sales.service';
import { ProductsService } from '../../../core/services/products.service';

@Component({
  selector: 'app-transaction-detail-page',
  standalone: true,
  imports: [FormsModule, CurrencyPipe, DatePipe, RouterLink, Toast, Dialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [MessageService],
  template: `
    <p-toast />

    @if (loading()) {
      <div class="flex h-64 items-center justify-center">
        <i class="pi pi-spinner pi-spin text-2xl text-primary"></i>
      </div>
    } @else if (!transaction()) {
      <div class="flex h-64 flex-col items-center justify-center gap-3 text-muted">
        <i class="pi pi-exclamation-circle text-3xl text-gray-300"></i>
        <p class="text-sm">Transaction not found.</p>
        <a routerLink="/sales" class="text-sm font-medium text-primary hover:underline">← Back to Sales</a>
      </div>
    } @else {
      <div class="space-y-6">

        <!-- Breadcrumb -->
        <div class="flex items-center gap-3">
          <a routerLink="/sales" class="flex items-center gap-1.5 text-sm font-medium text-muted transition-colors hover:text-text">
            <i class="pi pi-arrow-left text-xs"></i> Back to Sales
          </a>
          <span class="text-muted">/</span>
          <span class="text-sm font-semibold text-text">{{ invoiceNo(transaction()!.transaction_id) }}</span>
        </div>

        <!-- Header card -->
        <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="space-y-1">
              <h1 class="text-lg font-bold text-text">{{ invoiceNo(transaction()!.transaction_id) }}</h1>
              <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
                @if (transaction()!.customer_name) {
                  <span><i class="pi pi-user mr-1 text-xs"></i>{{ transaction()!.customer_name }}</span>
                }
                @if (transaction()!.contact_number) {
                  <span><i class="pi pi-phone mr-1 text-xs"></i>{{ transaction()!.contact_number }}</span>
                }
                <span><i class="pi pi-calendar mr-1 text-xs"></i>{{ transaction()!.sale_date | date: 'mediumDate' }}</span>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span
                class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
                [class.bg-red-100]="transaction()!.status === 'voided'"
                [class.text-red-700]="transaction()!.status === 'voided'"
                [class.bg-green-100]="transaction()!.status !== 'voided'"
                [class.text-green-700]="transaction()!.status !== 'voided'"
              >
                {{ transaction()!.status === 'voided' ? 'Voided' : 'Active' }}
              </span>
            </div>
          </div>

          <!-- Payment / notes summary -->
          <div class="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-gray-100 pt-4 text-sm">
            <div>
              <span class="font-medium text-muted">Payment method: </span>
              <span class="text-text">{{ formatPaymentMethod(transaction()!.payment_method) }}</span>
            </div>
            <div>
              <span class="font-medium text-muted">Payment status: </span>
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                [class.bg-green-100]="(transaction()!.payment_status || 'paid') === 'paid'"
                [class.text-green-700]="(transaction()!.payment_status || 'paid') === 'paid'"
                [class.bg-yellow-100]="(transaction()!.payment_status || 'paid') === 'partial'"
                [class.text-yellow-700]="(transaction()!.payment_status || 'paid') === 'partial'"
                [class.bg-orange-100]="(transaction()!.payment_status || 'paid') === 'credit'"
                [class.text-orange-700]="(transaction()!.payment_status || 'paid') === 'credit'"
              >
                {{ transaction()!.payment_status || 'paid' }}
              </span>
            </div>
            @if (transaction()!.payment_amount != null) {
              <div>
                <span class="font-medium text-muted">Amount paid: </span>
                <span class="font-semibold text-text">
                  {{ transaction()!.payment_amount | currency: (transaction()!.currency || 'NGN') : 'symbol' : '1.2-2' }}
                </span>
                @if ((transaction()!.total_amount - (transaction()!.payment_amount ?? 0)) > 0) {
                  <span class="ml-2 text-xs text-orange-600">
                    ({{ (transaction()!.total_amount - (transaction()!.payment_amount ?? 0)) | currency: (transaction()!.currency || 'NGN') : 'symbol' : '1.0-0' }} outstanding)
                  </span>
                }
              </div>
            }
            @if (transaction()!.notes) {
              <div class="w-full">
                <span class="font-medium text-muted">Note: </span>
                <span class="text-text">{{ transaction()!.notes }}</span>
              </div>
            }
          </div>
        </div>

        <!-- Items table -->
        <div class="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div class="border-b border-gray-100 px-5 py-3">
            <h2 class="text-sm font-semibold text-text">Line Items</h2>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-100 text-sm">
              <caption class="sr-only">Transaction items</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Product</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Qty</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Unit Price</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Discount</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Line Total</th>
                  <th class="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-muted">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50">
                @for (item of transaction()!.items; track item.id) {
                  <tr
                    data-testid="transaction-item-row"
                    class="transition-colors hover:bg-gray-50/50"
                    [class.opacity-50]="item.status === 'voided'"
                  >
                    <td class="px-4 py-3 font-medium text-text">
                      {{ getProductName(item.product_id) }}
                      @if (item.status === 'voided') {
                        <span class="ml-2 rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-600">voided</span>
                      }
                    </td>
                    <td class="px-4 py-3 text-right text-muted">{{ item.quantity }}</td>
                    <td class="px-4 py-3 text-right text-muted">
                      {{ item.unit_price | currency: (item.currency || 'NGN') : 'symbol' : '1.2-2' }}
                    </td>
                    <td class="px-4 py-3 text-right text-muted">
                      @if (item.discount_amount) {
                        {{ item.discount_amount | currency: (item.currency || 'NGN') : 'symbol' : '1.2-2' }}
                      } @else {
                        —
                      }
                    </td>
                    <td class="px-4 py-3 text-right font-semibold text-text">
                      {{ item.total_amount | currency: (item.currency || 'NGN') : 'symbol' : '1.2-2' }}
                    </td>
                    <td class="px-4 py-3 text-center">
                      <div class="flex items-center justify-center gap-1">
                        @if (item.status !== 'voided') {
                          <button
                            data-testid="txn-item-edit-btn"
                            (click)="openEditDialog(item)"
                            class="rounded p-1.5 text-muted transition-colors hover:bg-blue-50 hover:text-secondary"
                            title="Edit sale"
                            type="button"
                          >
                            <i class="pi pi-pencil text-xs"></i>
                          </button>
                          <button
                            data-testid="txn-item-void-btn"
                            (click)="openVoidDialog(item)"
                            class="rounded p-1.5 text-muted transition-colors hover:bg-red-50 hover:text-danger"
                            title="Void sale"
                            type="button"
                          >
                            <i class="pi pi-trash text-xs"></i>
                          </button>
                        }
                        <button
                          data-testid="txn-item-audit-btn"
                          (click)="openAuditDialog(item.id)"
                          class="rounded p-1.5 text-muted transition-colors hover:bg-gray-100 hover:text-text"
                          title="View audit trail"
                          type="button"
                        >
                          <i class="pi pi-clock text-xs"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
              <tfoot>
                <tr class="border-t-2 border-gray-200 bg-gray-50/80">
                  <td colspan="4" class="px-4 py-3 text-right text-sm font-semibold text-text">Grand Total</td>
                  <td class="px-4 py-3 text-right text-base font-bold text-primary">
                    {{ transaction()!.total_amount | currency: (transaction()!.currency || 'NGN') : 'symbol' : '1.2-2' }}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>

          @if (transaction()!.status !== 'voided') {
            <div class="border-t border-gray-100 px-5 py-4">
              <button
                data-testid="edit-transaction-btn"
                (click)="openEditTransactionDialog()"
                class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
                type="button"
              >
                <i class="pi pi-pencil text-xs"></i> Edit Payment & Notes
              </button>
            </div>
          }
        </div>

      </div>
    }

    <!-- Edit Sale Item Dialog -->
    <p-dialog
      header="Edit Sale"
      [(visible)]="editDialogVisible"
      [modal]="true"
      [style]="{ width: '450px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
    >
      @if (editingItem()) {
        <div class="space-y-4">
          <div>
            <label for="detail-edit-qty" class="mb-1.5 block text-xs font-medium text-muted">Quantity</label>
            <input
              id="detail-edit-qty"
              type="number"
              [(ngModel)]="editForm.quantity"
              min="1"
              data-testid="edit-quantity-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="detail-edit-price" class="mb-1.5 block text-xs font-medium text-muted">Unit Price</label>
            <input
              id="detail-edit-price"
              type="number"
              [(ngModel)]="editForm.unit_price"
              min="0"
              step="0.01"
              data-testid="edit-price-input"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="detail-edit-channel" class="mb-1.5 block text-xs font-medium text-muted">Channel</label>
            <select
              id="detail-edit-channel"
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
            >Cancel</button>
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

    <!-- Void Sale Dialog -->
    <p-dialog
      header="Void Sale"
      [(visible)]="voidDialogVisible"
      [modal]="true"
      [style]="{ width: '420px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
    >
      @if (voidingItem()) {
        <div class="space-y-4">
          <div class="rounded-lg border border-red-200 bg-red-50 p-3">
            <p class="text-sm font-medium text-red-800">
              Are you sure you want to void this sale? This will reverse the inventory deduction.
            </p>
          </div>
          <div class="rounded-lg bg-gray-50 p-3 text-sm">
            <p><span class="font-medium text-muted">Product:</span> {{ getProductName(voidingItem()!.product_id) }}</p>
            <p><span class="font-medium text-muted">Quantity:</span> {{ voidingItem()!.quantity }}</p>
            <p><span class="font-medium text-muted">Total:</span> {{ voidingItem()!.total_amount | currency: (voidingItem()!.currency || 'NGN') : 'symbol' : '1.0-0' }}</p>
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
            >Cancel</button>
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

    <!-- Edit Transaction Dialog -->
    <p-dialog
      header="Edit Payment & Notes"
      [(visible)]="editTransactionDialogVisible"
      [modal]="true"
      [style]="{ width: '440px' }"
      [breakpoints]="{ '960px': '75vw', '640px': '90vw' }"
    >
      <div class="space-y-4">
        <div>
          <label for="txn-payment-method" class="mb-1.5 block text-xs font-medium text-muted">Payment Method</label>
          <select
            id="txn-payment-method"
            [(ngModel)]="txnEditForm.payment_method"
            data-testid="txn-payment-method-select"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
          >
            <option value="">— None —</option>
            <option value="cash">Cash</option>
            <option value="transfer">Bank Transfer</option>
            <option value="pos">POS</option>
            <option value="credit">Credit</option>
            <option value="cheque">Cheque</option>
          </select>
        </div>
        <div>
          <label for="txn-payment-status" class="mb-1.5 block text-xs font-medium text-muted">Payment Status</label>
          <select
            id="txn-payment-status"
            [(ngModel)]="txnEditForm.payment_status"
            data-testid="txn-payment-status-select"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
          >
            <option value="paid">Paid</option>
            <option value="credit">Credit (Owed)</option>
            <option value="partial">Partial</option>
          </select>
        </div>
        <div>
          <label for="txn-payment-amount" class="mb-1.5 block text-xs font-medium text-muted">
            Amount Paid
            <span class="ml-1 font-normal text-muted/70">(leave blank if fully paid or unknown)</span>
          </label>
          <input
            id="txn-payment-amount"
            type="number"
            [(ngModel)]="txnEditForm.payment_amount"
            min="0"
            step="0.01"
            data-testid="txn-payment-amount-input"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            placeholder="e.g. 5000.00"
          />
        </div>
        <div>
          <label for="txn-notes" class="mb-1.5 block text-xs font-medium text-muted">Sale Note</label>
          <textarea
            id="txn-notes"
            [(ngModel)]="txnEditForm.notes"
            rows="3"
            data-testid="txn-notes-input"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            placeholder="Optional note for this transaction..."
          ></textarea>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button
            (click)="editTransactionDialogVisible = false"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50"
            type="button"
          >Cancel</button>
          <button
            (click)="submitTransactionEdit()"
            [disabled]="saving()"
            data-testid="save-txn-edit-btn"
            class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
          >
            @if (saving()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
            } @else {
              <i class="pi pi-check text-sm"></i> Save
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
            <div class="rounded-lg border border-gray-200 p-3" data-testid="audit-entry">
              <div class="flex items-center justify-between">
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                  [class.bg-green-100]="entry.action === 'created'"
                  [class.text-green-700]="entry.action === 'created'"
                  [class.bg-blue-100]="entry.action === 'updated' || entry.action === 'transaction_updated'"
                  [class.text-blue-700]="entry.action === 'updated' || entry.action === 'transaction_updated'"
                  [class.bg-red-100]="entry.action === 'voided'"
                  [class.text-red-700]="entry.action === 'voided'"
                >{{ entry.action }}</span>
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
})
export class TransactionDetailPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly salesService = inject(SalesService);
  private readonly productsService = inject(ProductsService);
  private readonly messageService = inject(MessageService);

  transaction = signal<SaleTransaction | null>(null);
  loading = signal(true);
  saving = signal(false);
  productMap = signal<Map<string, string>>(new Map());

  // Edit item dialog
  editDialogVisible = false;
  editingItem = signal<SaleTransactionItem | null>(null);
  editForm: SaleUpdatePayload = {};

  // Void dialog
  voidDialogVisible = false;
  voidingItem = signal<SaleTransactionItem | null>(null);
  voidReason = '';

  // Edit transaction dialog
  editTransactionDialogVisible = false;
  txnEditForm: { payment_method: string; payment_status: string; payment_amount: string; notes: string } = {
    payment_method: '',
    payment_status: 'paid',
    payment_amount: '',
    notes: '',
  };

  // Audit dialog
  auditDialogVisible = false;
  auditEntries = signal<AuditEntry[]>([]);
  auditLoading = signal(false);

  ngOnInit(): void {
    this.productsService.getAll().subscribe({
      next: (products) => {
        const map = new Map<string, string>();
        products.forEach((p) => map.set(p.id, p.name));
        this.productMap.set(map);
      },
    });

    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.loading.set(false);
      return;
    }
    this.loadTransaction(id);
  }

  private loadTransaction(id: string): void {
    this.salesService.getTransaction(id).subscribe({
      next: (txn) => {
        this.transaction.set(txn);
        this.loading.set(false);
      },
      error: () => {
        this.transaction.set(null);
        this.loading.set(false);
      },
    });
  }

  getProductName(productId: string): string {
    return this.productMap().get(productId) || 'Unknown';
  }

  invoiceNo(transactionId: string): string {
    return 'INV-' + transactionId.replace(/-/g, '').slice(0, 8).toUpperCase();
  }

  formatPaymentMethod(method?: string | null): string {
    if (!method) return '—';
    const map: Record<string, string> = {
      cash: 'Cash',
      transfer: 'Bank Transfer',
      pos: 'POS',
      credit: 'Credit',
      cheque: 'Cheque',
    };
    return map[method] ?? method;
  }

  objectKeys(obj: Record<string, unknown>): string[] {
    return Object.keys(obj);
  }

  // ---- Edit item ----

  openEditDialog(item: SaleTransactionItem): void {
    this.editingItem.set(item);
    this.editForm = {
      quantity: item.quantity,
      unit_price: parseFloat(String(item.unit_price ?? 0)),
      channel: 'retail',
      notes: item.notes || '',
    };
    this.editDialogVisible = true;
  }

  submitEdit(): void {
    const item = this.editingItem();
    if (!item) return;
    this.saving.set(true);
    this.salesService.update(item.id, this.editForm).subscribe({
      next: () => {
        this.saving.set(false);
        this.editDialogVisible = false;
        this.editingItem.set(null);
        this.messageService.add({ severity: 'success', summary: 'Updated', detail: 'Sale updated' });
        this.loadTransaction(this.transaction()!.transaction_id);
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update sale' });
      },
    });
  }

  // ---- Void item ----

  openVoidDialog(item: SaleTransactionItem): void {
    this.voidingItem.set(item);
    this.voidReason = '';
    this.voidDialogVisible = true;
  }

  submitVoid(): void {
    const item = this.voidingItem();
    if (!item) return;
    this.saving.set(true);
    const reason = this.voidReason.trim() || 'No reason provided';
    this.salesService.voidSale(item.id, reason).subscribe({
      next: () => {
        this.saving.set(false);
        this.voidDialogVisible = false;
        this.voidingItem.set(null);
        this.messageService.add({ severity: 'success', summary: 'Voided', detail: 'Sale voided and inventory restored' });
        this.loadTransaction(this.transaction()!.transaction_id);
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to void sale' });
      },
    });
  }

  // ---- Edit transaction ----

  openEditTransactionDialog(): void {
    const txn = this.transaction();
    if (!txn) return;
    this.txnEditForm = {
      payment_method: txn.payment_method || '',
      payment_status: txn.payment_status || 'paid',
      payment_amount: txn.payment_amount != null ? String(txn.payment_amount) : '',
      notes: txn.notes || '',
    };
    this.editTransactionDialogVisible = true;
  }

  submitTransactionEdit(): void {
    const txn = this.transaction();
    if (!txn) return;
    this.saving.set(true);
    const rawAmount = this.txnEditForm.payment_amount.trim();
    const payload: SaleTransactionUpdatePayload = {
      payment_method: this.txnEditForm.payment_method || null,
      payment_status: this.txnEditForm.payment_status || null,
      payment_amount: rawAmount !== '' ? parseFloat(rawAmount) : null,
      notes: this.txnEditForm.notes || null,
    };
    this.salesService.updateTransaction(txn.transaction_id, payload).subscribe({
      next: (updated) => {
        this.saving.set(false);
        this.editTransactionDialogVisible = false;
        this.transaction.set(updated);
        this.messageService.add({ severity: 'success', summary: 'Updated', detail: 'Transaction updated' });
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update transaction' });
      },
    });
  }

  // ---- Audit trail ----

  openAuditDialog(saleId: string): void {
    this.auditEntries.set([]);
    this.auditLoading.set(true);
    this.auditDialogVisible = true;
    this.salesService.getAuditTrail(saleId).subscribe({
      next: (entries) => {
        this.auditEntries.set(entries);
        this.auditLoading.set(false);
      },
      error: () => {
        this.auditLoading.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load audit trail' });
      },
    });
  }
}
