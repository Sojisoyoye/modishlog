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
  OrderPayment,
  RecordPaymentPayload,
  UpdateOrderPayload,
} from '../../../core/services/orders.service';
import { ProductsService, Product } from '../../../core/services/products.service';
import { FxService } from '../../../core/services/fx.service';
import { LocationsService, Location } from '../../../core/services/locations.service';

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
            class="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-muted transition-colors hover:text-text min-h-[44px]"
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
              <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50">
                <i class="pi pi-truck text-sm text-emerald-700"></i>
              </div>
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
                class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-text shadow-sm transition-all hover:bg-gray-50 min-h-[44px]"
              >
                <i class="pi pi-pencil text-sm"></i> Edit
              </button>
            } @else {
              <button
                (click)="cancelEdit()"
                class="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-semibold text-muted shadow-sm transition-all hover:bg-gray-50 min-h-[44px]"
              >
                Cancel
              </button>
              <button
                (click)="saveEdit()"
                [disabled]="saving()"
                class="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50 min-h-[44px]"
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
        <div class="grid grid-cols-2 gap-4 rounded-xl border border-gray-100 bg-white p-5 shadow-sm sm:grid-cols-3 lg:grid-cols-4">
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
            @if (editing()) {
              <select
                [(ngModel)]="editForm.status"
                class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              >
                @for (s of statusOptions(order()!.status); track s) {
                  <option [value]="s">{{ s }}</option>
                }
              </select>
            } @else {
              <p class="mt-0.5 font-semibold text-text">{{ order()!.status }}</p>
            }
          </div>
          <div>
            <p class="text-xs font-medium text-muted">Order Date</p>
            @if (editing()) {
              <input
                type="date"
                [(ngModel)]="editForm.order_date"
                class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              />
            } @else {
              <p class="mt-0.5 font-semibold text-text">
                {{ (order()!.order_date || order()!.created_at) | date: 'mediumDate' }}
              </p>
            }
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
          <div>
            <p class="text-xs font-medium text-muted">Payment Status</p>
            <span
              class="mt-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
              [class]="order()!.payment_status === 'PAID' ? 'bg-green-100 text-green-700' :
                       order()!.payment_status === 'PARTIAL' ? 'bg-yellow-100 text-yellow-700' :
                       'bg-red-100 text-red-700'"
            >
              {{ order()!.payment_status === 'PAID' ? 'Paid' :
                 order()!.payment_status === 'PARTIAL' ? 'Partially Paid' : 'Unpaid' }}
            </span>
          </div>
          <div>
            <p class="text-xs font-medium text-muted">Location</p>
            @if (editing()) {
              <select
                [(ngModel)]="editForm.location_id"
                class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="">— None —</option>
                @for (loc of locations(); track loc.id) {
                  <option [value]="loc.id">{{ loc.name }}</option>
                }
              </select>
            } @else {
              <p class="mt-0.5 font-semibold text-text">{{ locationName(order()!.location_id) }}</p>
            }
          </div>
          <!-- Invoice # -->
          @if (editing() || order()!.supplier_invoice_number) {
            <div>
              <p class="text-xs font-medium text-muted">Invoice #</p>
              @if (editing()) {
                <input
                  type="text"
                  [(ngModel)]="editForm.supplier_invoice_number"
                  placeholder="e.g. INV-2026-001"
                  class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                />
              } @else {
                <p class="mt-0.5 font-semibold text-text">{{ order()!.supplier_invoice_number }}</p>
              }
            </div>
          }

          <!-- Invoice Date -->
          @if (editing() || order()!.supplier_invoice_date) {
            <div>
              <p class="text-xs font-medium text-muted">Invoice Date</p>
              @if (editing()) {
                <input
                  type="date"
                  [(ngModel)]="editForm.supplier_invoice_date"
                  class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                />
              } @else {
                <p class="mt-0.5 font-semibold text-text">
                  {{ order()!.supplier_invoice_date | date: 'mediumDate' }}
                </p>
              }
            </div>
          }

          <!-- Payment Terms -->
          @if (editing() || order()!.pay_term_number) {
            <div>
              <p class="text-xs font-medium text-muted">Payment Terms</p>
              @if (editing()) {
                <div class="mt-0.5 flex gap-1">
                  <input
                    type="number"
                    [(ngModel)]="editForm.pay_term_number"
                    min="0"
                    placeholder="30"
                    class="w-16 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                  />
                  <select
                    [(ngModel)]="editForm.pay_term_type"
                    class="flex-1 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                  >
                    <option value="">— unit —</option>
                    <option value="days">days</option>
                    <option value="months">months</option>
                  </select>
                </div>
              } @else {
                <p class="mt-0.5 font-semibold text-text">
                  {{ order()!.pay_term_number }} {{ order()!.pay_term_type }}
                </p>
              }
            </div>
          }

          <!-- FX Rate at creation -->
          @if (editing() || order()!.fx_rate_at_creation) {
            <div>
              <p class="text-xs font-medium text-muted">FX Rate (creation)</p>
              @if (editing()) {
                <input
                  type="number"
                  [(ngModel)]="editForm.fx_rate_at_creation"
                  step="1"
                  min="0"
                  placeholder="e.g. 1600"
                  class="mt-0.5 w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                />
              } @else {
                <p class="mt-0.5 font-semibold text-text">
                  ₦{{ order()!.fx_rate_at_creation | number: '1.0-0' }}/{{ order()!.currency }}
                </p>
              }
            </div>
          }

          @if (order()!.fx_rate_at_delivery) {
            <div>
              <p class="text-xs font-medium text-muted">FX Rate (delivery)</p>
              <p class="mt-0.5 font-semibold text-text">
                ₦{{ order()!.fx_rate_at_delivery | number: '1.0-0' }}/{{ order()!.currency }}
              </p>
            </div>
          }

          <!-- Move Status — full-width row at bottom of metadata card, hidden while editing -->
          @if (!editing() && nextStatuses(order()!.status).length > 0) {
            <div class="col-span-2 border-t border-gray-100 pt-4 sm:col-span-3 lg:col-span-4">
              <p class="mb-2 text-xs font-bold uppercase tracking-wider text-muted">Move Status</p>
              @if (nextStatuses(order()!.status).includes('DELIVERED')) {
                <div class="mb-3 max-w-xs">
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
                    class="flex items-center gap-1.5 rounded-lg border border-emerald-600 px-4 py-2 text-sm font-semibold text-emerald-600 transition-all hover:bg-emerald-600 hover:text-white min-h-[44px]"
                  >
                    <i class="pi pi-arrow-right text-xs"></i> {{ ns }}
                  </button>
                }
              </div>
            </div>
          }
        </div>

        <!-- Line Items (full width) -->
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
              <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">Line Items</p>
              <div class="overflow-x-auto">
                <table
                  class="min-w-full divide-y divide-gray-200 text-sm"
                  data-testid="line-items-table"
                >
                  <thead>
                    <tr class="bg-gray-50">
                      <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Product
                      </th>
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Qty
                      </th>
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                        {{ order()!.currency === 'NGN' ? 'Unit Cost (₦)' : 'Unit Cost ($)' }}
                      </th>
                      @if (order()!.currency === 'USD' && order()!.fx_rate_at_creation) {
                        <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                          Unit Cost (₦)
                        </th>
                      }
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                        {{ order()!.currency === 'NGN' ? 'Total (₦)' : 'Total ($)' }}
                      </th>
                      @if (order()!.currency === 'USD' && order()!.fx_rate_at_creation) {
                        <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                          Total (₦)
                        </th>
                      }
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Sell (₦)
                      </th>
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Margin (₦)
                      </th>
                      <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                        Margin (%)
                      </th>
                      @if (order()!.status === 'DELIVERED') {
                        <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">
                          In Stock
                        </th>
                      }
                      @if (editing()) {
                        <th class="px-3 py-2.5 w-8"></th>
                      }
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    @for (item of order()!.line_items; track item.id) {
                      @if (!editing() || !editDeletedProductIds().has(item.product_id)) {
                      <tr class="transition-colors hover:bg-gray-50/50">
                        <td class="px-3 py-2.5 text-text">
                          {{ productName(item.product_id) }}
                        </td>
                        <td class="px-3 py-2.5 text-right text-text">
                          @if (editing()) {
                            <input
                              type="number"
                              [ngModel]="getEditQty(item.product_id)"
                              (ngModelChange)="setEditQty(item.product_id, $event)"
                              step="1"
                              min="0"
                              class="w-20 rounded border border-gray-300 px-2 py-1 text-sm text-right focus:border-primary focus:ring-1 focus:ring-primary"
                            />
                          } @else {
                            {{ item.quantity }}
                          }
                        </td>
                        <td class="px-3 py-2.5 text-right text-text">
                          @if (editing()) {
                            <input
                              type="number"
                              [ngModel]="getEditUnitCost(item.product_id)"
                              (ngModelChange)="setEditUnitCost(item.product_id, $event)"
                              step="0.01"
                              min="0"
                              class="w-24 rounded border border-gray-300 px-2 py-1 text-sm text-right focus:border-primary focus:ring-1 focus:ring-primary"
                            />
                          } @else {
                            {{ item.unit_cost | number: '1.2-2' }}
                          }
                        </td>
                        @if (order()!.currency === 'USD' && order()!.fx_rate_at_creation) {
                          <td class="px-3 py-2.5 text-right text-muted">
                            @if (editing()) {
                              <input
                                type="number"
                                [ngModel]="getEditUnitCostNGN(item.product_id)"
                                (ngModelChange)="setEditUnitCostNGN(item.product_id, $event)"
                                step="1"
                                min="0"
                                [placeholder]="item.unit_cost * order()!.fx_rate_at_creation! | number: '1.0-0'"
                                class="w-28 rounded border border-gray-300 px-2 py-1 text-sm text-right focus:border-primary focus:ring-1 focus:ring-primary"
                              />
                            } @else if (item.unit_cost_ngn != null) {
                              {{ item.unit_cost_ngn | number: '1.0-0' }}
                              <span class="block text-xs font-normal opacity-60">
                                (est. {{ item.unit_cost * order()!.fx_rate_at_creation! | number: '1.0-0' }})
                              </span>
                            } @else {
                              {{ item.unit_cost * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                            }
                          </td>
                        }
                        <td class="px-3 py-2.5 text-right font-semibold text-text">
                          {{ item.line_total | number: '1.2-2' }}
                        </td>
                        @if (order()!.currency === 'USD' && order()!.fx_rate_at_creation) {
                          <td class="px-3 py-2.5 text-right font-semibold text-muted">
                            {{ item.line_total * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                          </td>
                        }
                        <td class="px-3 py-2.5 text-right text-muted">
                          @if (editing()) {
                            <input
                              type="number"
                              [ngModel]="getEditSellPriceNGN(item.product_id)"
                              (ngModelChange)="setEditSellPriceNGN(item.product_id, $event)"
                              step="0.01"
                              min="0"
                              class="w-28 rounded border border-gray-300 px-2 py-1 text-sm text-right focus:border-primary focus:ring-1 focus:ring-primary"
                              data-testid="sell-price-input"
                            />
                          } @else if (item.sell_price_ngn != null) {
                            {{ item.sell_price_ngn | number: '1.0-0' }}
                          } @else {
                            {{ productSellingPrice(item.product_id) | number: '1.0-0' }}
                            <span class="block text-xs font-normal opacity-50">(catalog)</span>
                          }
                        </td>
                        <td class="px-3 py-2.5 text-right font-semibold"
                            [class]="!canComputeMargin(order()!) ? 'text-muted' : marginNGN(item, order()!) >= 0 ? 'text-success' : 'text-danger'">
                          @if (canComputeMargin(order()!)) {
                            {{ marginNGN(item, order()!) | number: '1.0-0' }}
                          } @else {
                            <span class="text-xs font-normal">N/A</span>
                          }
                        </td>
                        <td class="px-3 py-2.5 text-right font-semibold"
                            [class]="!canComputeMargin(order()!) ? 'text-muted' : marginPct(item, order()!) >= 0 ? 'text-success' : 'text-danger'">
                          @if (canComputeMargin(order()!)) {
                            {{ marginPct(item, order()!) | number: '1.1-1' }}%
                          } @else {
                            <span class="text-xs font-normal">N/A</span>
                          }
                        </td>
                        @if (order()!.status === 'DELIVERED') {
                          <td class="px-3 py-2.5 text-right text-sm font-semibold"
                              [class]="item.units_remaining == null ? 'text-muted' : item.units_remaining > 0 ? 'text-success' : 'text-muted'">
                            {{ item.units_remaining != null ? (item.units_remaining | number: '1.0-0') : '—' }}
                          </td>
                        }
                        @if (editing()) {
                          <td class="px-2 py-2.5 text-center">
                            <button
                              type="button"
                              (click)="removeLineItem(item.product_id)"
                              title="Remove product"
                              class="rounded p-1 text-muted transition-colors hover:bg-red-50 hover:text-danger"
                            >
                              <i class="pi pi-trash text-xs"></i>
                            </button>
                          </td>
                        }
                      </tr>
                      }
                    } @empty {
                      <tr>
                        <td colspan="10" class="px-3 py-8 text-center text-muted">No line items</td>
                      </tr>
                    }
                    @if (editing() && order()!.line_items.length > 0 && order()!.line_items.every(i => editDeletedProductIds().has(i.product_id))) {
                      <tr>
                        <td colspan="10" class="px-3 py-8 text-center text-muted">No line items — all products removed</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
        </div>

        <!-- Notes (full width) -->
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
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

        <!-- Cost Breakdown + Payments (2-col) -->
        <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <!-- Cost Breakdown -->
            <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
              <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">
                Cost Breakdown
              </p>
              <dl class="space-y-2 text-sm">
                <div class="flex justify-between">
                  <dt class="text-muted">Total items</dt>
                  <dd class="font-semibold text-text">{{ totalItems() | number }}</dd>
                </div>
                <div class="flex justify-between">
                  <dt class="text-muted">Goods total</dt>
                  <dd class="font-semibold text-text">
                    @if (order()!.currency === 'NGN') {
                      ₦{{ goodsTotal() | number: '1.0-0' }}
                    } @else {
                      {{ goodsTotal() | currency: 'USD' : 'symbol' : '1.2-2' }}
                    }
                  </dd>
                </div>
                @if (order()!.currency === 'USD' && order()!.fx_rate_at_creation) {
                  <div class="flex justify-between">
                    <dt class="text-muted text-xs">≈ at ₦{{ order()!.fx_rate_at_creation | number: '1.0-0' }}/USD</dt>
                    <dd class="text-muted text-xs">
                      ₦{{ goodsTotal() * order()!.fx_rate_at_creation! | number: '1.0-0' }}
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
                      Discount@if (order()!.discount_type === 'percentage') { (%) }
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

                <!-- Shipping: always entered and stored in NGN -->
                <div class="flex justify-between border-t border-gray-200 pt-2">
                  <dt class="text-muted">
                    Shipping (₦)
                    @if (editing()) { <span class="text-xs text-muted">(agent quote)</span> }
                  </dt>
                  <dd class="font-semibold text-text">
                    @if (editing()) {
                      <input
                        type="number"
                        [(ngModel)]="editForm.shipping_cost_ngn"
                        step="1000"
                        min="0"
                        class="w-36 rounded border border-gray-300 px-2 py-1 text-sm text-right focus:border-primary focus:ring-1 focus:ring-primary"
                      />
                    } @else {
                      ₦{{ order()!.shipping_cost | number: '1.0-0' }}
                    }
                  </dd>
                </div>

                <!-- Shipping note — always visible -->
                <div class="border-t border-gray-200 pt-2">
                  <dt class="mb-1 text-xs font-medium text-muted">Shipping note</dt>
                  @if (editing()) {
                    <textarea
                      [(ngModel)]="editForm.shipping_details"
                      rows="3"
                      placeholder="e.g. via Maersk, vessel ETA Lagos 28 Jun…"
                      class="w-full resize-none rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                    ></textarea>
                  } @else if (order()!.shipping_details) {
                    <p class="whitespace-pre-line text-sm text-text">{{ order()!.shipping_details }}</p>
                  } @else {
                    <p class="text-sm text-muted/50 italic">None</p>
                  }
                </div>

                <!-- Total landed cost -->
                <div class="flex justify-between border-t border-gray-200 pt-2">
                  <dt class="font-bold text-gray-900">Total landed (₦)</dt>
                  <dd class="text-xl font-bold text-gray-900">
                    @if (order()!.currency === 'NGN') {
                      ₦{{ goodsTotal() + order()!.shipping_cost | number: '1.0-0' }}
                    } @else if (order()!.fx_rate_at_creation) {
                      ₦{{ goodsTotal() * order()!.fx_rate_at_creation! + order()!.shipping_cost | number: '1.0-0' }}
                    } @else {
                      ₦{{ order()!.shipping_cost | number: '1.0-0' }}
                    }
                  </dd>
                </div>
                @if (order()!.currency === 'USD' && order()!.fx_rate_at_creation) {
                  <div class="flex justify-between">
                    <dt class="text-muted">Total landed (USD est.)</dt>
                    <dd class="font-semibold text-text">
                      {{ (goodsTotal() * order()!.fx_rate_at_creation! + order()!.shipping_cost) / order()!.fx_rate_at_creation! | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                }

                @if (order()!.payment_summary) {
                  <!-- Paid -->
                  <div class="flex justify-between border-t border-gray-200 pt-2">
                    <dt class="text-muted">Paid</dt>
                    <dd class="font-semibold text-success">
                      @if (order()!.currency === 'NGN') {
                        ₦{{ order()!.payment_summary!.total_paid | number: '1.0-0' }}
                      } @else if (order()!.fx_rate_at_creation) {
                        ₦{{ order()!.payment_summary!.total_paid * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                      } @else {
                        {{ order()!.payment_summary!.total_paid | currency: order()!.currency : 'symbol' : '1.2-2' }}
                      }
                    </dd>
                  </div>
                  @if (order()!.currency !== 'NGN') {
                    <div class="flex justify-between">
                      <dt class="text-xs text-muted"></dt>
                      <dd class="text-xs text-success">
                        {{ order()!.payment_summary!.total_paid | currency: order()!.currency : 'symbol' : '1.2-2' }}
                      </dd>
                    </div>
                  }

                  <!-- Remaining -->
                  <div class="flex justify-between">
                    <dt class="font-bold text-text">Remaining</dt>
                    <dd class="font-bold"
                      [class]="order()!.payment_summary!.balance_remaining > 0 ? 'text-warning' : 'text-success'">
                      @if (order()!.currency === 'NGN') {
                        ₦{{ order()!.payment_summary!.balance_remaining | number: '1.0-0' }}
                      } @else if (order()!.fx_rate_at_creation) {
                        ₦{{ order()!.payment_summary!.balance_remaining * order()!.fx_rate_at_creation! | number: '1.0-0' }}
                      } @else {
                        {{ order()!.payment_summary!.balance_remaining | currency: order()!.currency : 'symbol' : '1.2-2' }}
                      }
                    </dd>
                  </div>
                  @if (order()!.currency !== 'NGN') {
                    <div class="flex justify-between">
                      <dt class="text-xs text-muted"></dt>
                      <dd class="text-xs"
                        [class]="order()!.payment_summary!.balance_remaining > 0 ? 'text-warning' : 'text-success'">
                        {{ order()!.payment_summary!.balance_remaining | currency: order()!.currency : 'symbol' : '1.2-2' }}
                      </dd>
                    </div>
                  }
                }
              </dl>
            </div>

            <!-- Payment Panel -->
            <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm" data-testid="payment-section">
              <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">
                Payments
              </p>

              <!-- Summary row -->
              @if (order()!.payment_summary) {
                <dl class="mb-3 space-y-2 text-sm">
                  <div class="flex justify-between">
                    <dt class="text-muted">Total Due</dt>
                    <dd class="font-semibold text-text">
                      {{ order()!.payment_summary!.total_due | currency: 'USD' : 'symbol' : '1.2-2' }}
                    </dd>
                  </div>
                  <div class="flex justify-between">
                    <dt class="text-muted">Paid</dt>
                    <dd class="font-semibold text-success" data-testid="total-paid-value">
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
                <div class="mb-3">
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
              }

              <!-- Individual payments list -->
              @if (payments().length > 0) {
                <div class="mb-3 divide-y divide-gray-100 rounded-lg border border-gray-200 text-xs">
                  @for (p of payments(); track p.id) {
                    <div
                      class="flex items-center justify-between gap-2 px-3 py-2"
                      [class.opacity-40]="p.status === 'VOIDED'"
                      data-testid="payment-row"
                    >
                      <div class="min-w-0">
                        <span class="font-semibold text-text">
                          {{ p.amount | currency: p.currency : 'symbol' : '1.2-2' }}
                        </span>
                        @if (p.currency !== 'NGN' && p.fx_rate) {
                          <span class="ml-1 text-xs text-muted">
                            (₦{{ p.amount * p.fx_rate | number: '1.0-0' }} @ ₦{{ p.fx_rate | number: '1.0-0' }}/{{ p.currency }})
                          </span>
                        }
                        <span class="ml-1 text-muted">{{ p.payment_method }}</span>
                        @if (p.reference) {
                          <span class="ml-1 text-muted">· {{ p.reference }}</span>
                        }
                        <span class="ml-1 text-muted">· {{ p.payment_date | date: 'shortDate' }}</span>
                        @if (p.status === 'VOIDED') {
                          <span class="ml-1 font-semibold text-danger">VOIDED</span>
                        }
                      </div>
                      @if (editing() && p.status !== 'VOIDED') {
                        <button
                          type="button"
                          (click)="voidPayment(p.id)"
                          title="Void payment"
                          class="shrink-0 rounded p-1 text-muted transition-colors hover:bg-red-50 hover:text-danger"
                          data-testid="void-payment-btn"
                        >
                          <i class="pi pi-times-circle text-xs"></i>
                        </button>
                      }
                    </div>
                  }
                </div>
              }

              <!-- Record payment form (edit mode only) -->
              @if (editing()) {
                <div class="rounded-lg border border-dashed border-gray-300 p-3" data-testid="payment-record-form">
                  <p class="mb-2 text-xs font-semibold text-muted">Record Payment</p>
                  <div class="space-y-2">
                    <div class="flex gap-2">
                      <div class="flex-1">
                        <label class="mb-0.5 block text-xs text-muted">Amount</label>
                        <input
                          type="number"
                          [(ngModel)]="paymentForm.amount"
                          step="0.01"
                          min="0.01"
                          placeholder="0.00"
                          class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                          data-testid="payment-amount-input"
                        />
                      </div>
                      <div class="w-24">
                        <label class="mb-0.5 block text-xs text-muted">Currency</label>
                        <select
                          [(ngModel)]="paymentForm.currency"
                          class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                          data-testid="payment-currency-select"
                        >
                          <option value="NGN">₦ NGN</option>
                          <option value="USD">$ USD</option>
                          <option value="EUR">€ EUR</option>
                        </select>
                      </div>
                    </div>

                    <!-- FX rate — only when paying in foreign currency -->
                    @if (paymentForm.currency !== 'NGN') {
                      <div>
                        <label class="mb-0.5 block text-xs text-muted">
                          Exchange Rate (₦ per {{ paymentForm.currency }})
                        </label>
                        <input
                          type="number"
                          [(ngModel)]="paymentForm.fx_rate"
                          step="1"
                          min="0"
                          placeholder="e.g. 1620"
                          class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                          data-testid="payment-fx-rate-input"
                        />
                        @if (paymentNgnEquivalent !== null) {
                          <p class="mt-1 text-xs text-muted">
                            ≈ <span class="font-semibold text-text">₦{{ paymentNgnEquivalent | number: '1.0-0' }}</span>
                          </p>
                        }
                      </div>
                    }

                    <div>
                      <label class="mb-0.5 block text-xs text-muted">Method</label>
                      <select
                        [(ngModel)]="paymentForm.payment_method"
                        class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                        data-testid="payment-method-select"
                      >
                        <option value="BANK_TRANSFER">Bank Transfer</option>
                        <option value="LC">Letter of Credit</option>
                        <option value="CASH">Cash</option>
                      </select>
                    </div>
                    <div>
                      <label class="mb-0.5 block text-xs text-muted">Date</label>
                      <input
                        type="date"
                        [(ngModel)]="paymentForm.payment_date"
                        class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                        data-testid="payment-date-input"
                      />
                    </div>
                    <div>
                      <label class="mb-0.5 block text-xs text-muted">Reference (optional)</label>
                      <input
                        type="text"
                        [(ngModel)]="paymentForm.reference"
                        placeholder="e.g. TRF-001"
                        class="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                        data-testid="payment-reference-input"
                      />
                    </div>
                    <button
                      type="button"
                      (click)="recordPayment()"
                      [disabled]="recordingPayment() || !paymentForm.amount || !paymentForm.payment_date"
                      class="w-full rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white transition-all hover:bg-emerald-700 disabled:opacity-50 min-h-[44px]"
                      data-testid="record-payment-btn"
                    >
                      @if (recordingPayment()) {
                        <i class="pi pi-spinner pi-spin text-xs"></i> Recording…
                      } @else {
                        <i class="pi pi-plus text-xs"></i> Record Payment
                      }
                    </button>
                  </div>
                </div>
              }
            </div>
        </div>

        <!-- Profit Overview (full width) -->
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <p class="mb-4 text-xs font-bold uppercase tracking-wider text-muted">Profit Overview</p>
          @if (!canComputeProfitOverview()) {
            <p class="text-sm text-muted">
              @if (!canComputeMargin(order()!)) {
                Set an FX rate to enable profit calculations.
              } @else {
                Set selling prices on products to enable profit calculations.
              }
            </p>
          } @else {
            <!-- Revenue / Gross Profit / Net Profit figures -->
            <div class="mb-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div class="rounded-lg bg-emerald-50 px-4 py-3">
                <p class="mb-0.5 text-xs font-medium text-muted">Revenue</p>
                <p class="text-xl font-bold text-gray-900">
                  ₦{{ totalRevenueNGN() | number: '1.0-0' }}
                </p>
                <p class="mt-0.5 text-xs text-muted">Σ sell price × qty</p>
              </div>
              <div class="rounded-lg bg-gray-50 px-4 py-3">
                <p class="mb-0.5 text-xs font-medium text-muted">Gross Profit</p>
                <p class="text-xl font-bold" [class]="grossProfit() >= 0 ? 'text-success' : 'text-danger'">
                  ₦{{ grossProfit() | number: '1.0-0' }}
                </p>
                <p class="mt-0.5 text-xs text-muted">revenue − purchase cost only</p>
              </div>
              <div class="rounded-lg bg-gray-50 px-4 py-3">
                <p class="mb-0.5 text-xs font-medium text-muted">Net Profit</p>
                <p class="text-xl font-bold" [class]="netProfit() >= 0 ? 'text-success' : 'text-danger'">
                  ₦{{ netProfit() | number: '1.0-0' }}
                </p>
                <p class="mt-0.5 text-xs text-muted">revenue − all landed costs</p>
              </div>
            </div>

            <!-- 4 margin percentages -->
            <div class="grid grid-cols-2 gap-3 border-t border-gray-100 pt-4 sm:grid-cols-4">
              <div class="rounded-lg bg-gray-50 px-4 py-3 text-center">
                <p class="mb-1 text-xs text-muted">GP Margin (Capital)</p>
                <p class="text-xl font-bold" [class]="grossProfit() >= 0 ? 'text-success' : 'text-danger'">
                  {{ goodsCostNGN() > 0 ? (grossProfit() / goodsCostNGN() * 100 | number: '1.1-1') : '—' }}%
                </p>
                <p class="mt-1 text-xs text-muted">GP ÷ Goods Cost</p>
                <span class="mt-1.5 inline-block rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">Return on Investment</span>
              </div>
              <div class="rounded-lg bg-gray-50 px-4 py-3 text-center">
                <p class="mb-1 text-xs text-muted">GP Margin (Revenue)</p>
                <p class="text-xl font-bold" [class]="grossProfit() >= 0 ? 'text-success' : 'text-danger'">
                  {{ totalRevenueNGN() > 0 ? (grossProfit() / totalRevenueNGN() * 100 | number: '1.1-1') : '—' }}%
                </p>
                <p class="mt-1 text-xs text-muted">GP ÷ Revenue</p>
                <span class="mt-1.5 inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Gross Take-Home</span>
              </div>
              <div class="rounded-lg bg-gray-50 px-4 py-3 text-center">
                <p class="mb-1 text-xs text-muted">NP Margin (Capital)</p>
                <p class="text-xl font-bold" [class]="netProfit() >= 0 ? 'text-success' : 'text-danger'">
                  {{ totalLandedNGN() > 0 ? (netProfit() / totalLandedNGN() * 100 | number: '1.1-1') : '—' }}%
                </p>
                <p class="mt-1 text-xs text-muted">NP ÷ Total Capital</p>
                <span class="mt-1.5 inline-block rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">Net Return on Investment</span>
              </div>
              <div class="rounded-lg bg-gray-50 px-4 py-3 text-center">
                <p class="mb-1 text-xs text-muted">NP Margin (Revenue)</p>
                <p class="text-xl font-bold" [class]="netProfit() >= 0 ? 'text-success' : 'text-danger'">
                  {{ totalRevenueNGN() > 0 ? (netProfit() / totalRevenueNGN() * 100 | number: '1.1-1') : '—' }}%
                </p>
                <p class="mt-1 text-xs text-muted">NP ÷ Revenue</p>
                <span class="mt-1.5 inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">Net Take-Home</span>
              </div>
            </div>

            <!-- Supporting cost bases -->
            <div class="mt-3 flex flex-wrap gap-x-6 gap-y-1 border-t border-gray-100 pt-3 text-xs text-muted">
              <span>Goods cost: <strong class="text-text">₦{{ goodsCostNGN() | number: '1.0-0' }}</strong></span>
              <span>Total landed (goods + clearing + overhead): <strong class="text-text">₦{{ totalLandedNGN() | number: '1.0-0' }}</strong></span>
            </div>
          }
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
  private readonly locationsService = inject(LocationsService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  order = signal<OrderDetail | null>(null);
  products = signal<Product[]>([]);
  locations = signal<Location[]>([]);
  payments = signal<OrderPayment[]>([]);
  loading = signal(true);
  editing = signal(false);
  saving = signal(false);
  recordingPayment = signal(false);
  deliveryFxRate: number | null = null;

  editLineItems: { product_id: string; quantity: number; unit_cost: number; unit_cost_ngn: number | null; sell_price_ngn: number | null }[] = [];
  editDeletedProductIds = signal<Set<string>>(new Set());

  editForm: {
    supplier_name: string;
    expected_delivery_date: string;
    notes: string;
    shipping_cost_ngn: number;
    shipping_details: string;
    fx_rate_at_creation: number | null;
    supplier_invoice_number: string;
    supplier_invoice_date: string;
    pay_term_number: number | null;
    pay_term_type: string;
    status: string;
    order_date: string;
    payment_status: string;
    location_id: string;
  } = {
    supplier_name: '', expected_delivery_date: '', notes: '',
    shipping_cost_ngn: 0, shipping_details: '',
    fx_rate_at_creation: null,
    supplier_invoice_number: '', supplier_invoice_date: '',
    pay_term_number: null, pay_term_type: '',
    status: '', order_date: '',
    payment_status: 'UNPAID', location_id: '',
  };

  paymentForm: {
    amount: number | null;
    currency: string;
    fx_rate: number | null;
    payment_method: string;
    payment_date: string;
    reference: string;
  } = { amount: null, currency: 'USD', fx_rate: null, payment_method: 'BANK_TRANSFER', payment_date: '', reference: '' };

  private readonly statusTransitions: Record<string, string[]> = {
    ORDERED: ['PENDING', 'CANCELLED'],
    PENDING: ['IN_PRODUCTION', 'CANCELLED'],
    IN_PRODUCTION: ['SHIPPING'],
    SHIPPING: ['CLEARED'],
    CLEARED: ['DELIVERED'],
  };

  ngOnInit(): void {
    this.productsService.getAll().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (p) => this.products.set(p),
    });
    this.locationsService.getAll(undefined, true).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (r) => this.locations.set(r.items),
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
          this.loadPayments(o.id);
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

  getEditUnitCost(productId: string): number {
    return this.editLineItems.find((i) => i.product_id === productId)?.unit_cost ?? 0;
  }

  setEditUnitCost(productId: string, value: number): void {
    const item = this.editLineItems.find((i) => i.product_id === productId);
    if (item) item.unit_cost = Number(value);
  }

  getEditUnitCostNGN(productId: string): number | null {
    return this.editLineItems.find((i) => i.product_id === productId)?.unit_cost_ngn ?? null;
  }

  setEditUnitCostNGN(productId: string, value: number | string): void {
    const item = this.editLineItems.find((i) => i.product_id === productId);
    if (item) item.unit_cost_ngn = value !== '' && value != null ? Number(value) : null;
  }

  getEditSellPriceNGN(productId: string): number | null {
    return this.editLineItems.find((i) => i.product_id === productId)?.sell_price_ngn ?? null;
  }

  setEditSellPriceNGN(productId: string, value: number | string): void {
    const item = this.editLineItems.find((i) => i.product_id === productId);
    if (item) item.sell_price_ngn = this.normaliseNGN(value !== '' && value != null ? Number(value) : null);
  }

  private normaliseNGN(value: number | null | undefined): number | null {
    if (value == null || isNaN(value as number)) return null;
    return parseFloat((value as number).toFixed(2));
  }

  getEditQty(productId: string): number {
    return this.editLineItems.find((i) => i.product_id === productId)?.quantity ?? 0;
  }

  setEditQty(productId: string, value: number): void {
    const item = this.editLineItems.find((i) => i.product_id === productId);
    if (item) item.quantity = Number(value);
  }

  productSellingPrice(productId: string): number {
    return this.products().find((p) => p.id === productId)?.selling_price ?? 0;
  }

  effectiveSellPrice(item: { product_id: string; sell_price_ngn?: number | null }): number {
    return item.sell_price_ngn != null ? item.sell_price_ngn : this.productSellingPrice(item.product_id);
  }

  canComputeMargin(order: OrderDetail): boolean {
    return order.currency === 'NGN' || !!order.fx_rate_at_creation;
  }

  unitCostInNGN(item: { unit_cost: number; unit_cost_ngn?: number | null }, order: OrderDetail): number {
    if (order.currency === 'NGN') return item.unit_cost;
    if (item.unit_cost_ngn != null) return item.unit_cost_ngn;
    return order.fx_rate_at_creation ? item.unit_cost * order.fx_rate_at_creation : 0;
  }

  marginNGN(item: { product_id: string; unit_cost: number; sell_price_ngn?: number | null }, order: OrderDetail): number {
    return this.effectiveSellPrice(item) - this.unitCostInNGN(item, order);
  }

  marginPct(item: { product_id: string; unit_cost: number; sell_price_ngn?: number | null }, order: OrderDetail): number {
    const sell = this.effectiveSellPrice(item);
    if (!sell) return 0;
    return (this.marginNGN(item, order) / sell) * 100;
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

  statusOptions(status: string): string[] {
    return [status, ...this.nextStatuses(status)];
  }

  locationName(locationId: string | null): string {
    if (!locationId) return '—';
    return this.locations().find((l) => l.id === locationId)?.name ?? locationId;
  }

  removeLineItem(productId: string): void {
    this.editLineItems = this.editLineItems.filter((i) => i.product_id !== productId);
    this.editDeletedProductIds.update((s) => new Set([...s, productId]));
  }

  totalItems(): number {
    return (this.order()?.line_items ?? []).reduce((sum, i) => sum + i.quantity, 0);
  }

  goodsTotal(): number {
    return (this.order()?.line_items ?? []).reduce((sum, i) => sum + Number(i.line_total), 0);
  }

  goodsCostNGN(): number {
    const o = this.order();
    if (!o) return 0;
    return o.line_items.reduce((sum, i) => sum + this.unitCostInNGN(i, o) * i.quantity, 0);
  }

  private toNGN(foreignAmount: number): number {
    const o = this.order();
    if (!o) return 0;
    if (o.currency === 'NGN') return foreignAmount;
    return o.fx_rate_at_creation ? foreignAmount * o.fx_rate_at_creation : 0;
  }

  // Total landed = goods + clearing (USD) + clearing/shipping (NGN) + additional + tax − discount
  totalLandedNGN(): number {
    const o = this.order();
    if (!o) return 0;
    const additionalNGN = this.toNGN(this.additionalExpensesTotal());
    const taxNGN        = this.toNGN(Number(o.tax_amount));
    const discountNGN   = this.toNGN(Number(o.discount_amount));
    return this.goodsCostNGN()
      + this.toNGN(o.clearing_cost)
      + o.shipping_cost
      + additionalNGN + taxNGN - discountNGN;
  }

  totalRevenueNGN(): number {
    const o = this.order();
    if (!o) return 0;
    return o.line_items.reduce((sum, i) => sum + this.effectiveSellPrice(i) * i.quantity, 0);
  }

  // Gross Profit = Revenue − Goods cost only (purchase price, no clearing/overhead)
  grossProfit(): number {
    return this.totalRevenueNGN() - this.goodsCostNGN();
  }

  // Net Profit = Revenue − Total Landed (all costs including clearing, shipping, overhead)
  netProfit(): number {
    return this.totalRevenueNGN() - this.totalLandedNGN();
  }

  canComputeProfitOverview(): boolean {
    const o = this.order();
    if (!o || !this.canComputeMargin(o)) return false;
    return o.line_items.some(i => this.effectiveSellPrice(i) > 0);
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
      shipping_cost_ngn: o.shipping_cost,
      shipping_details: o.shipping_details ?? '',
      fx_rate_at_creation: o.fx_rate_at_creation ?? null,
      supplier_invoice_number: o.supplier_invoice_number ?? '',
      supplier_invoice_date: o.supplier_invoice_date ?? '',
      pay_term_number: o.pay_term_number ?? null,
      pay_term_type: o.pay_term_type ?? '',
      status: o.status,
      order_date: o.order_date ?? '',
      payment_status: o.payment_status ?? 'UNPAID',
      location_id: o.location_id ?? '',
    };
    this.editLineItems = o.line_items.map((i) => ({
      product_id: i.product_id,
      quantity: i.quantity,
      unit_cost: i.unit_cost,
      unit_cost_ngn: i.unit_cost_ngn ?? null,
      sell_price_ngn: this.normaliseNGN(i.sell_price_ngn ?? (Number(this.productSellingPrice(i.product_id)) || null)),
    }));
    this.editDeletedProductIds.set(new Set());
    this.paymentForm = { amount: null, currency: o.currency, fx_rate: null, payment_method: 'BANK_TRANSFER', payment_date: '', reference: '' };
    this.editing.set(true);

    // Auto-fill FX rate from live API if order is USD and rate not yet set
    if (o.currency !== 'NGN' && !o.fx_rate_at_creation) {
      this.fxService.getLiveRate().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: (r) => { if (!this.editForm.fx_rate_at_creation) this.editForm.fx_rate_at_creation = r.usd_ngn; },
      });
    }
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
      shipping_cost: this.editForm.shipping_cost_ngn,
      shipping_details: this.editForm.shipping_details || null,
      fx_rate_at_creation: this.editForm.fx_rate_at_creation ?? null,
      supplier_invoice_number: this.editForm.supplier_invoice_number || null,
      supplier_invoice_date: this.editForm.supplier_invoice_date || null,
      pay_term_number: this.editForm.pay_term_number ?? null,
      pay_term_type: this.editForm.pay_term_type || null,
      line_items: this.editLineItems.map((i) => ({
        product_id: i.product_id,
        quantity: i.quantity,
        unit_cost: i.unit_cost,
        unit_cost_ngn: i.unit_cost_ngn ?? null,
        sell_price_ngn: i.sell_price_ngn != null ? i.sell_price_ngn : (this.productSellingPrice(i.product_id) || null),
      })),
      order_date: this.editForm.order_date || null,
      location_id: this.editForm.location_id || null,
    };
    const statusChanged = this.editForm.status !== o.status;
    // Data update first (order must still be in an editable status),
    // then status transition — so CANCELLED/DELIVERED don't block the save.
    const update$ = statusChanged
      ? this.ordersService.update(o.id, payload).pipe(
          switchMap(() => this.ordersService.updateStatus(o.id, this.editForm.status)),
        )
      : this.ordersService.update(o.id, payload);

    update$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
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

  recordPayment(): void {
    const o = this.order();
    if (!o || !this.paymentForm.amount || !this.paymentForm.payment_date) return;
    this.recordingPayment.set(true);
    const payload: RecordPaymentPayload = {
      amount: this.paymentForm.amount,
      currency: this.paymentForm.currency || o.currency,
      fx_rate: this.paymentForm.currency !== 'NGN' ? (this.paymentForm.fx_rate ?? null) : null,
      payment_date: this.paymentForm.payment_date,
      payment_method: this.paymentForm.payment_method,
      reference: this.paymentForm.reference || null,
    };
    this.ordersService.recordPayment(o.id, payload)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.recordingPayment.set(false);
          this.paymentForm = { amount: null, currency: o.currency, fx_rate: null, payment_method: 'BANK_TRANSFER', payment_date: '', reference: '' };
          this.refreshPaymentsAndSummary(o.id);
          this.messageService.add({ severity: 'success', summary: 'Payment recorded' });
        },
        error: (err) => {
          this.recordingPayment.set(false);
          const detail = err?.error?.detail ?? 'Failed to record payment';
          this.messageService.add({ severity: 'error', summary: 'Error', detail });
        },
      });
  }

  voidPayment(paymentId: string): void {
    const o = this.order();
    if (!o) return;
    this.ordersService.voidPayment(o.id, paymentId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.refreshPaymentsAndSummary(o.id);
          this.messageService.add({ severity: 'info', summary: 'Payment voided' });
        },
        error: () => {
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to void payment' });
        },
      });
  }

  get paymentNgnEquivalent(): number | null {
    const { amount, currency, fx_rate } = this.paymentForm;
    if (!amount || currency === 'NGN' || !fx_rate) return null;
    return amount * fx_rate;
  }

  private loadPayments(orderId: string): void {
    this.ordersService.listPayments(orderId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: (p) => this.payments.set(p), error: () => this.payments.set([]) });
  }

  private refreshPaymentsAndSummary(orderId: string): void {
    this.loadPayments(orderId);
    this.ordersService.getById(orderId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({ next: (updated) => this.order.set(updated) });
  }
}
