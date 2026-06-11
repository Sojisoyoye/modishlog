import {
  Component,
  ChangeDetectionStrategy,
  DestroyRef,
  inject,
  signal,
  OnInit,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { switchMap } from 'rxjs';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  OrdersService,
  OrderDetail,
  UpdateOrderPayload,
} from '../../../core/services/orders.service';
import { ProductsService, Product } from '../../../core/services/products.service';
import { FxService } from '../../../core/services/fx.service';

@Component({
  selector: 'app-order-detail-page',
  standalone: true,
  imports: [
    FormsModule,
    CurrencyPipe,
    DatePipe,
    DecimalPipe,
    RouterLink,
    Toast,
    StatusBadgeComponent,
  ],
  template: `
    <p-toast />
    @if (loading()) {
      <div class="flex h-64 items-center justify-center">
        <i class="pi pi-spinner pi-spin text-2xl text-primary"></i>
      </div>
    } @else if (order()) {
      <div class="space-y-6">
        <!-- Breadcrumb / Back -->
        <div class="flex items-center gap-3">
          <a
            routerLink="/orders"
            class="flex items-center gap-1.5 text-sm font-medium text-muted transition-colors hover:text-text"
          >
            <i class="pi pi-arrow-left text-xs"></i> Back to Orders
          </a>
          <span class="text-muted">/</span>
          <span class="text-sm font-semibold text-text">{{ order()!.order_number }}</span>
        </div>

        <!-- Header -->
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div class="flex items-center gap-3">
              <h2 class="text-2xl font-bold text-text">{{ order()!.order_number }}</h2>
              <app-status-badge
                [label]="order()!.status"
                [status]="statusColor(order()!.status)"
              />
              <span
                class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                [class]="order()!.is_purchase_order ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'"
              >
                {{ order()!.is_purchase_order ? 'Purchase Order' : 'Received Purchase' }}
              </span>
            </div>
            <p class="mt-1 text-sm text-muted">{{ order()!.supplier_name }}</p>
          </div>
          <div class="flex gap-2">
            @if (!editing()) {
              <button
                (click)="startEdit()"
                class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-text shadow-sm transition-all hover:bg-gray-50"
              >
                <i class="pi pi-pencil text-sm"></i> Edit
              </button>
            } @else {
              <button
                (click)="cancelEdit()"
                class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-muted shadow-sm transition-all hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                (click)="saveEdit()"
                [disabled]="saving()"
                class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
              >
                @if (saving()) {
                  <i class="pi pi-spinner pi-spin text-sm"></i> Saving…
                } @else {
                  <i class="pi pi-check text-sm"></i> Save
                }
              </button>
            }
          </div>
        </div>

        <!-- Order Metadata Grid -->
        <div class="grid grid-cols-2 gap-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:grid-cols-3 lg:grid-cols-4">
          <div>
            <p class="text-xs font-medium text-muted">Supplier</p>
            @if (editing()) {
              <input
                type="text"
                [(ngModel)]="editForm.supplier_name"
                class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              />
            } @else {
              <p class="mt-0.5 font-semibold text-text">{{ order()!.supplier_name }}</p>
            }
          </div>
          <div>
            <p class="text-xs font-medium text-muted">Status</p>
            <p class="mt-0.5 font-semibold text-text">{{ order()!.status }}</p>
          </div>
          <div>
            <p class="text-xs font-medium text-muted">Order Date</p>
            <p class="mt-0.5 font-semibold text-text">
              {{ order()!.created_at | date: 'mediumDate' }}
            </p>
          </div>
          <div>
            <p class="text-xs font-medium text-muted">Expected Delivery</p>
            @if (editing()) {
              <input
                type="date"
                [(ngModel)]="editForm.expected_delivery_date"
                class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              />
            } @else {
              <p class="mt-0.5 font-semibold text-text">
                {{ order()!.expected_delivery_date ? (order()!.expected_delivery_date | date: 'mediumDate') : 'TBD' }}
              </p>
            }
          </div>
          @if (order()!.supplier_invoice_number) {
            <div>
              <p class="text-xs font-medium text-muted">Invoice #</p>
              <p class="mt-0.5 font-semibold text-text">{{ order()!.supplier_invoice_number }}</p>
            </div>
          }
          @if (order()!.supplier_invoice_date) {
            <div>
              <p class="text-xs font-medium text-muted">Invoice Date</p>
              <p class="mt-0.5 font-semibold text-text">
                {{ order()!.supplier_invoice_date | date: 'mediumDate' }}
              </p>
            </div>
          }
          @if (order()!.pay_term_number) {
            <div>
              <p class="text-xs font-medium text-muted">Payment Terms</p>
              <p class="mt-0.5 font-semibold text-text">
                {{ order()!.pay_term_number }} {{ order()!.pay_term_type }}
              </p>
            </div>
          }
          @if (order()!.fx_rate_at_creation) {
            <div>
              <p class="text-xs font-medium text-muted">FX Rate (creation)</p>
              <p class="mt-0.5 font-semibold text-text">
                ₦{{ order()!.fx_rate_at_creation | number: '1.0-0' }}/USD
              </p>
            </div>
          }
          @if (order()!.fx_rate_at_delivery) {
            <div>
              <p class="text-xs font-medium text-muted">FX Rate (delivery)</p>
              <p class="mt-0.5 font-semibold text-text">
                ₦{{ order()!.fx_rate_at_delivery | number: '1.0-0' }}/USD
              </p>
            </div>
          }
        </div>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <!-- Left: Line Items -->
          <div class="lg:col-span-2 space-y-6">
            <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">Line Items</p>
              <div class="overflow-x-auto">
                <table
                  class="min-w-full divide-y divide-gray-200 text-sm"
                  data-testid="line-items-table"
                >
                  <thead>
                    <tr class="bg-gray-50/80">
                      <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                        Product
                      </th>
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                        Qty
                      </th>
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                        Unit Cost (USD)
                      </th>
                      @if (order()!.fx_rate_at_creation) {
                        <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                          Unit Cost (₦)
                        </th>
                      }
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                        Line Total (USD)
                      </th>
                      @if (order()!.fx_rate_at_creation) {
                        <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                          Line Total (₦)
                        </th>
                      }
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    @for (item of order()!.line_items; track item.id) {
                      <tr class="transition-colors hover:bg-gray-50/50">
                        <td class="px-3 py-2.5 text-text">
                          {{ productName(item.product_id) }}
                        </td>
                        <td class="px-3 py-2.5 text-right text-text">{{ item.quantity }}</td>
                        <td class="px-3 py-2.5 text-right text-text">
                          {{ item.unit_cost | currency: 'USD' : 'symbol' : '1.2-2' }}
                        </td>
                        @if (order()!.fx_rate_at_creation) {
                          <td class="px-3 py-2.5 text-right text-muted">
                            ₦{{ item.unit_cost * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                          </td>
                        }
                        <td class="px-3 py-2.5 text-right font-semibold text-text">
                          {{ item.line_total | currency: 'USD' : 'symbol' : '1.2-2' }}
                        </td>
                        @if (order()!.fx_rate_at_creation) {
                          <td class="px-3 py-2.5 text-right font-semibold text-muted">
                            ₦{{ item.line_total * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                          </td>
                        }
                      </tr>
                    } @empty {
                      <tr>
                        <td colspan="6" class="px-3 py-8 text-center text-muted">No line items</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Notes -->
            <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Notes</p>
              @if (editing()) {
                <textarea
                  [(ngModel)]="editForm.notes"
                  rows="4"
                  placeholder="Internal notes about this order…"
                  class="w-full resize-none rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                ></textarea>
              } @else {
                <p class="whitespace-pre-line text-sm text-text">
                  {{ order()!.notes || 'No notes.' }}
                </p>
              }
            </div>

            @if (order()!.shipping_details) {
              <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">
                  Shipping Details
                </p>
                <p class="whitespace-pre-line text-sm text-text">{{ order()!.shipping_details }}</p>
              </div>
            }
          </div>

          <!-- Right: Totals + Payment Summary -->
          <div class="space-y-6">
            <!-- Cost Breakdown -->
            <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">
                Cost Breakdown
              </p>
              <dl class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <dt class="text-muted">Goods total</dt>
                  <dd class="font-semibold text-text">
                    {{ goodsTotal() | currency: 'USD' : 'symbol' : '1.2-2' }}
                  </dd>
                </div>
                @if (order()!.shipping_cost > 0) {
                  <div class="flex justify-between">
                    <dt class="text-muted">Shipping</dt>
                    <dd class="font-semibold text-text">
                      {{ order()!.shipping_cost | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                }
                @if (order()!.clearing_cost > 0) {
                  <div class="flex justify-between">
                    <dt class="text-muted">Clearing</dt>
                    <dd class="font-semibold text-text">
                      {{ order()!.clearing_cost | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                }
                @if (additionalExpensesTotal() > 0) {
                  <div class="flex justify-between">
                    <dt class="text-muted">Additional expenses</dt>
                    <dd class="font-semibold text-text">
                      {{ additionalExpensesTotal() | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                }
                @if (order()!.discount_amount > 0) {
                  <div class="flex justify-between">
                    <dt class="text-muted">
                      Discount
                      @if (order()!.discount_type === 'percentage') {
                        (%)
                      }
                    </dt>
                    <dd class="font-semibold text-danger">
                      −{{ order()!.discount_amount | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                }
                @if (order()!.tax_amount > 0) {
                  <div class="flex justify-between">
                    <dt class="text-muted">Tax ({{ order()!.tax_rate }}%)</dt>
                    <dd class="font-semibold text-text">
                      {{ order()!.tax_amount | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                }
                <div class="flex justify-between border-t border-gray-200 pt-2">
                  <dt class="font-bold text-text">Total (USD)</dt>
                  <dd class="font-bold text-text">
                    {{ order()!.total_amount | currency: 'USD' : 'symbol' : '1.2-2' }}
                  </dd>
                </div>
                @if (order()!.fx_rate_at_creation) {
                  <div class="flex justify-between">
                    <dt class="text-muted">Total (₦ est.)</dt>
                    <dd class="font-semibold text-text">
                      ₦{{ order()!.total_amount * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                    </dd>
                  </div>
                }
              </dl>
            </div>

            <!-- Payment Summary -->
            @if (order()!.payment_summary) {
              <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">
                  Payment Status
                </p>
                <dl class="space-y-2 text-sm">
                  <div class="flex justify-between">
                    <dt class="text-muted">Total Due</dt>
                    <dd class="font-semibold text-text">
                      {{ order()!.payment_summary!.total_due | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                  <div class="flex justify-between">
                    <dt class="text-muted">Paid</dt>
                    <dd class="font-semibold text-success">
                      {{ order()!.payment_summary!.total_paid | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                  <div class="flex justify-between border-t border-gray-200 pt-2">
                    <dt class="font-bold text-text">Balance</dt>
                    <dd
                      class="font-bold"
                      [class]="order()!.payment_summary!.balance_remaining > 0 ? 'text-warning' : 'text-success'"
                    >
                      {{ order()!.payment_summary!.balance_remaining | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                </dl>
                <div class="mt-3">
                  @if (order()!.payment_summary!.is_fully_paid) {
                    <span class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">
                      <i class="pi pi-check-circle text-xs"></i> Fully Paid
                    </span>
                  } @else {
                    <span class="inline-flex items-center gap-1 rounded-full bg-yellow-100 px-2.5 py-1 text-xs font-semibold text-yellow-700">
                      <i class="pi pi-clock text-xs"></i>
                      {{ order()!.payment_summary!.payment_count }} payment(s) recorded
                    </span>
                  }
                </div>
              </div>
            }

            <!-- Status Workflow -->
            @if (nextStatuses(order()!.status).length > 0) {
              <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">
                  Move Status
                </p>
                @if (nextStatuses(order()!.status).includes('DELIVERED')) {
                  <div class="mb-3">
                    <label class="mb-1 block text-xs font-medium text-muted">FX Rate at Delivery</label>
                    <input
                      type="number"
                      [(ngModel)]="deliveryFxRate"
                      step="1"
                      min="0"
                      placeholder="e.g. 1600"
                      class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                    />
                  </div>
                }
                <div class="flex flex-wrap gap-2">
                  @for (ns of nextStatuses(order()!.status); track ns) {
                    <button
                      (click)="transitionStatus(ns)"
                      class="flex items-center gap-1.5 rounded-lg border border-secondary px-4 py-2 text-sm font-semibold text-secondary transition-all hover:bg-secondary hover:text-white"
                    >
                      <i class="pi pi-arrow-right text-xs"></i> {{ ns }}
                    </button>
                  }
                </div>
              </div>
            }
          </div>
        </div>
      </div>
    } @else if (!loading()) {
      <div class="flex h-64 flex-col items-center justify-center gap-4">
        <i class="pi pi-exclamation-circle text-4xl text-muted"></i>
        <p class="text-muted">Order not found.</p>
        <a routerLink="/orders" class="text-sm font-medium text-secondary hover:underline">
          Back to Orders
        </a>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrderDetailPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly ordersService = inject(OrdersService);
  private readonly productsService = inject(ProductsService);
  private readonly fxService = inject(FxService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  order = signal<OrderDetail | null>(null);
  products = signal<Product[]>([]);
  loading = signal(true);
  editing = signal(false);
  saving = signal(false);
  deliveryFxRate: number | null = null;

  editForm: {
    supplier_name: string;
    expected_delivery_date: string;
    notes: string;
  } = { supplier_name: '', expected_delivery_date: '', notes: '' };

  private readonly statusTransitions: Record<string, string[]> = {
    ORDERED: ['PENDING'],
    PENDING: ['IN_PRODUCTION'],
    IN_PRODUCTION: ['SHIPPING'],
    SHIPPING: ['CLEARED'],
    CLEARED: ['DELIVERED'],
  };

  ngOnInit(): void {
    this.productsService.getAll().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (p) => this.products.set(p),
    });

    this.route.paramMap
      .pipe(
        takeUntilDestroyed(this.destroyRef),
        switchMap((params) => {
          this.loading.set(true);
          const id = params.get('id') ?? '';
          return this.ordersService.getById(id);
        }),
      )
      .subscribe({
        next: (o) => {
          this.order.set(o);
          this.loading.set(false);
        },
        error: () => {
          this.order.set(null);
          this.loading.set(false);
        },
      });
  }

  productName(productId: string): string {
    return this.products().find((p) => p.id === productId)?.name ?? productId;
  }

  statusColor(status: string): 'info' | 'warning' | 'success' | 'neutral' {
    if (status === 'DELIVERED') return 'success';
    if (status === 'SHIPPING' || status === 'CLEARED') return 'warning';
    if (status === 'IN_PRODUCTION' || status === 'ORDERED' || status === 'PENDING') return 'info';
    return 'neutral';
  }

  nextStatuses(status: string): string[] {
    return this.statusTransitions[status] ?? [];
  }

  goodsTotal(): number {
    return (this.order()?.line_items ?? []).reduce((sum, i) => sum + Number(i.line_total), 0);
  }

  additionalExpensesTotal(): number {
    const o = this.order() as Record<string, unknown> | null;
    if (!o) return 0;
    let total = 0;
    for (let n = 1; n <= 4; n++) {
      const v = o[`additional_expense_value_${n}`];
      if (v != null) total += Number(v);
    }
    return total;
  }

  startEdit(): void {
    const o = this.order();
    if (!o) return;
    this.editForm = {
      supplier_name: o.supplier_name,
      expected_delivery_date: o.expected_delivery_date ?? '',
      notes: o.notes ?? '',
    };
    this.editing.set(true);
  }

  cancelEdit(): void {
    this.editing.set(false);
  }

  saveEdit(): void {
    const o = this.order();
    if (!o) return;
    this.saving.set(true);
    const payload: UpdateOrderPayload = {
      supplier_name: this.editForm.supplier_name || null,
      expected_delivery_date: this.editForm.expected_delivery_date || null,
      notes: this.editForm.notes || null,
    };
    this.ordersService.update(o.id, payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (updated) => {
        this.order.set({ ...updated, payment_summary: o.payment_summary });
        this.saving.set(false);
        this.editing.set(false);
        this.messageService.add({ severity: 'success', summary: 'Saved', detail: 'Order updated' });
      },
      error: (err) => {
        this.saving.set(false);
        const detail = err?.error?.detail ?? 'Failed to save changes';
        this.messageService.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  transitionStatus(newStatus: string): void {
    const o = this.order();
    if (!o) return;
    const fxRate = newStatus === 'DELIVERED' && this.deliveryFxRate ? this.deliveryFxRate : undefined;
    this.ordersService.updateStatus(o.id, newStatus, fxRate)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (updated) => {
          this.order.set({ ...updated, payment_summary: o.payment_summary });
          this.deliveryFxRate = null;
          this.messageService.add({
            severity: 'success',
            summary: 'Updated',
            detail: `Moved to ${newStatus}`,
          });
        },
        error: () => {
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Status update failed' });
        },
      });
  }
}
