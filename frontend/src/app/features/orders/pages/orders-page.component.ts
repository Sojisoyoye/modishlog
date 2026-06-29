import { Component, ChangeDetectionStrategy, DestroyRef, inject, signal, computed, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  OrdersService,
  Order,
  CreateOrderPayload,
  BulkImportResult,
  ImportRowError,
  ParsedLineItem,
} from '../../../core/services/orders.service';
import { ProductsService, Product } from '../../../core/services/products.service';
import { FxService } from '../../../core/services/fx.service';

@Component({
  selector: 'app-orders-page',
  standalone: true,
  imports: [FormsModule, CurrencyPipe, DatePipe, DecimalPipe, Toast, Dialog, StatusBadgeComponent],
  template: `
    <p-toast />
    <div>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-text">Orders</h2>
          <p class="mt-1 text-sm text-muted">Track purchase orders and pipeline</p>
        </div>
        <div class="flex gap-2">
          <button
            (click)="openImportDialog()"
            class="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-text shadow-sm transition-all hover:bg-gray-50"
          >
            <i class="pi pi-upload text-sm"></i> Import Orders
          </button>
          <button
            (click)="showCreate = true"
            class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
          >
            <i class="pi pi-plus text-sm"></i> New Order
          </button>
        </div>
      </div>

      <!-- Pipeline View -->
      <div class="mb-4 flex flex-wrap gap-2">
        <!-- "All" reset chip -->
        <button
          type="button"
          (click)="togglePipelineFilter(null)"
          class="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-all"
          [class]="pipelineFilter() === null
            ? 'border-secondary bg-secondary/10 text-secondary ring-1 ring-secondary'
            : 'border-gray-200 bg-white text-muted hover:border-secondary/50 hover:text-text'"
        >
          All
          <span class="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs font-bold text-text">{{ orders().length }}</span>
        </button>
        @for (status of pipelineStatuses; track status) {
          <button
            type="button"
            (click)="togglePipelineFilter(status)"
            class="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium transition-all"
            [class]="pipelineFilter() === status
              ? 'border-secondary bg-secondary/10 text-secondary ring-1 ring-secondary'
              : 'border-gray-200 bg-white text-muted hover:border-secondary/50 hover:text-text'"
          >
            {{ statusLabel[status] }}
            <span class="rounded-full bg-gray-100 px-1.5 py-0.5 text-xs font-bold text-text">{{ ordersByStatus(status).length }}</span>
          </button>
        }
      </div>

      <!-- Orders Table -->
      <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-list text-sm text-secondary"></i>
            </div>
            <h3 class="text-base font-semibold text-text">
              {{ pipelineFilter() ? statusLabel[pipelineFilter()!] + ' Orders' : 'All Orders' }}
            </h3>
          </div>
          <button
            type="button"
            data-testid="export-orders-csv"
            (click)="exportOrdersCsv()"
            class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
          >
            <i class="pi pi-download text-xs"></i>
            Export CSV
          </button>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">All purchase orders</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Order #
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Supplier
                </th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                  Total (USD)
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Type
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Status
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  ETA
                </th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                  Est. Locked (30%)
                </th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                  Est. Float (70%)
                </th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                  Paid
                </th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                  Balance
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Payment
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @if (pageLoading()) {
                @for (i of [1,2,3,4,5,6]; track i) {
                  <tr class="animate-pulse">
                    <td class="px-3 py-2.5"><div class="h-4 w-20 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="h-4 w-28 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="h-5 w-10 rounded-full bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="h-5 w-20 rounded-full bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="h-4 w-20 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="ml-auto h-4 w-16 rounded bg-gray-200"></div></td>
                    <td class="px-3 py-2.5"><div class="h-5 w-16 rounded-full bg-gray-200"></div></td>
                  </tr>
                }
              } @else {
              @for (order of displayedOrders(); track order.id) {
                <tr
                  class="cursor-pointer transition-colors hover:bg-gray-50/50"
                  (click)="viewOrder(order)"
                >
                  <td class="px-3 py-2.5 font-semibold text-secondary">{{ order.order_number }}</td>
                  <td class="px-3 py-2.5">{{ order.supplier_name }}</td>
                  <td class="px-3 py-2.5 text-right font-semibold">
                    {{ order.total_amount | currency: 'USD' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2.5">
                    <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                      [class]="order.is_purchase_order ? 'bg-blue-100 text-blue-700' : 'bg-green-100 text-green-700'">
                      {{ order.is_purchase_order ? 'PO' : 'Purchase' }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5">
                    <app-status-badge [label]="order.status" [status]="orderStatus(order.status)" />
                  </td>
                  <td class="px-3 py-2.5 text-muted">
                    {{
                      order.expected_delivery_date
                        ? (order.expected_delivery_date | date: 'mediumDate')
                        : '--'
                    }}
                  </td>
                  <td class="px-3 py-2.5 text-right font-medium text-muted">
                    {{ order.total_amount * 0.3 | currency: (order.currency || 'USD') : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2.5 text-right font-medium text-muted">
                    {{ order.total_amount * 0.7 | currency: (order.currency || 'USD') : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2.5 text-right font-medium text-success">
                    {{ order.total_paid | currency: (order.currency || 'USD') : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2.5 text-right font-medium"
                    [class.text-warning]="order.balance_remaining > 0"
                    [class.text-success]="order.balance_remaining <= 0">
                    {{ order.balance_remaining | currency: (order.currency || 'USD') : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2.5">
                    <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                      [class]="order.payment_status === 'PAID' ? 'bg-green-100 text-green-700' :
                               order.payment_status === 'PARTIAL' ? 'bg-yellow-100 text-yellow-700' :
                               'bg-red-100 text-red-700'">
                      {{ order.payment_status === 'PAID' ? 'Paid' :
                         order.payment_status === 'PARTIAL' ? 'Partially Paid' : 'Unpaid' }}
                    </span>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="11" class="px-3 py-10 text-center text-muted">
                    <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                    No orders found
                  </td>
                </tr>
              }
              } <!-- end @else (pageLoading) -->
            </tbody>
          </table>
        </div>
        <!-- Pagination controls -->
        @if (ordersTotal() > 0) {
          <div class="mt-4 flex items-center justify-between text-sm text-muted">
            <span>Showing {{ ordersShowingFrom() }}–{{ ordersShowingTo() }} of {{ ordersTotal() }} orders</span>
            <div class="flex items-center gap-1">
              <button
                type="button"
                (click)="ordersGoToPage(ordersPage() - 1)"
                [disabled]="ordersPage() === 1"
                class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
              >
                <i class="pi pi-chevron-left text-xs"></i>
              </button>
              @for (n of ordersPageNumbers(); track n) {
                <button
                  type="button"
                  (click)="ordersGoToPage(n)"
                  [class]="n === ordersPage() ? 'rounded bg-primary px-2.5 py-1 text-xs font-semibold text-white' : 'rounded px-2.5 py-1 text-xs hover:bg-gray-100'"
                >
                  {{ n }}
                </button>
              }
              <button
                type="button"
                (click)="ordersGoToPage(ordersPage() + 1)"
                [disabled]="ordersPage() === ordersTotalPages()"
                class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
              >
                <i class="pi pi-chevron-right text-xs"></i>
              </button>
            </div>
          </div>
        }
      </div>
    </div>

    <!-- Order Detail Dialog -->
    <p-dialog
      header="Order Details"
      [(visible)]="detailVisible"
      [modal]="true"
      [style]="{ width: '600px' }"
      [breakpoints]="{ '960px': '90vw', '640px': '95vw' }"
    >
      @if (selectedOrder()) {
        <div class="space-y-5">
          <div class="flex items-center justify-between">
            <h4 class="text-lg font-bold text-text">{{ selectedOrder()!.order_number }}</h4>
            <app-status-badge
              [label]="selectedOrder()!.status"
              [status]="orderStatus(selectedOrder()!.status)"
            />
          </div>
          <div class="grid grid-cols-1 gap-4 rounded-lg bg-gray-50 p-4 text-sm sm:grid-cols-2">
            <div>
              <p class="text-xs font-medium text-muted">Supplier</p>
              <p class="mt-0.5 font-semibold text-text">{{ selectedOrder()!.supplier_name }}</p>
            </div>
            <div>
              <p class="text-xs font-medium text-muted">Order Date</p>
              <p class="mt-0.5 font-semibold text-text">
                {{ selectedOrder()!.created_at | date: 'mediumDate' }}
              </p>
            </div>
            <div>
              <p class="text-xs font-medium text-muted">Total (USD)</p>
              <p class="mt-0.5 font-semibold text-text">
                {{ selectedOrder()!.total_amount | currency: 'USD' }}
              </p>
            </div>
            <div>
              <p class="text-xs font-medium text-muted">ETA</p>
              <p class="mt-0.5 font-semibold text-text">
                {{
                  selectedOrder()!.expected_delivery_date
                    ? (selectedOrder()!.expected_delivery_date | date: 'mediumDate')
                    : 'TBD'
                }}
              </p>
            </div>
          </div>

          <!-- Line Items -->
          @if (selectedOrder()!.line_items.length) {
            <div class="rounded-lg border border-gray-200 p-4">
              <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Line Items</p>
              <table class="min-w-full divide-y divide-gray-200 text-sm" data-testid="line-items-table">
                <thead>
                  <tr class="bg-gray-50/80">
                    <th class="px-3 py-2 text-left text-xs font-semibold uppercase text-muted">Product</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase text-muted">Qty</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase text-muted">Unit Cost</th>
                    <th class="px-3 py-2 text-right text-xs font-semibold uppercase text-muted">Line Total</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  @for (item of selectedOrder()!.line_items; track item.id) {
                    <tr>
                      <td class="px-3 py-2 text-text">
                        {{ productName(item.product_id) }}
                      </td>
                      <td class="px-3 py-2 text-right text-text">{{ item.quantity }}</td>
                      <td class="px-3 py-2 text-right text-text">
                        {{ item.unit_cost | currency: 'USD' }}
                      </td>
                      <td class="px-3 py-2 text-right font-semibold text-text">
                        {{ item.line_total | currency: 'USD' }}
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }

          <!-- FX Exposure -->
          <div class="rounded-lg border border-gray-200 p-4">
            <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">FX Exposure</p>
            <div class="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
              <div>
                <p class="text-xs text-muted">Locked (30%)</p>
                <p class="mt-0.5 text-lg font-bold text-success">
                  {{ selectedOrder()!.total_amount * 0.3 | currency: 'USD' }}
                </p>
              </div>
              <div>
                <p class="text-xs text-muted">Floating (70%)</p>
                <p class="mt-0.5 text-lg font-bold text-warning">
                  {{ selectedOrder()!.total_amount * 0.7 | currency: 'USD' }}
                </p>
              </div>
            </div>
            @if (selectedOrder()!.fx_rate_at_creation && selectedOrder()!.fx_rate_at_delivery) {
              <div class="mt-4 rounded-lg bg-gray-50 p-3">
                <p class="mb-2 text-xs font-bold uppercase tracking-wider text-muted">
                  Predicted vs Actual FX Rate
                </p>
                <div class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
                  <div>
                    <p class="text-xs text-muted">At Creation</p>
                    <p class="mt-0.5 font-semibold text-text">
                      {{ selectedOrder()!.fx_rate_at_creation | number: '1.2-2' }}
                    </p>
                  </div>
                  <div>
                    <p class="text-xs text-muted">At Delivery</p>
                    <p class="mt-0.5 font-semibold text-text">
                      {{ selectedOrder()!.fx_rate_at_delivery | number: '1.2-2' }}
                    </p>
                  </div>
                  <div>
                    <p class="text-xs text-muted">Difference</p>
                    <p
                      class="mt-0.5 font-semibold"
                      [class.text-success]="selectedOrder()!.fx_rate_at_delivery! <= selectedOrder()!.fx_rate_at_creation!"
                      [class.text-danger]="selectedOrder()!.fx_rate_at_delivery! > selectedOrder()!.fx_rate_at_creation!"
                    >
                      {{ (selectedOrder()!.fx_rate_at_delivery! - selectedOrder()!.fx_rate_at_creation!) | number: '1.2-2' }}
                    </p>
                  </div>
                </div>
              </div>
            }
          </div>

          <!-- FX Scenarios (best / base / worst) -->
          @if (selectedOrder()!.fx_rate_at_creation) {
            <div class="rounded-lg border border-gray-200 p-4">
              <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">
                FX Scenarios
              </p>
              <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 text-sm">
                  <thead>
                    <tr class="bg-gray-50/80">
                      <th class="px-3 py-2 text-left text-xs font-semibold uppercase text-muted">Scenario</th>
                      <th class="px-3 py-2 text-right text-xs font-semibold uppercase text-muted">FX Rate</th>
                      <th class="px-3 py-2 text-right text-xs font-semibold uppercase text-muted">Total Cost (NGN)</th>
                      <th class="px-3 py-2 text-right text-xs font-semibold uppercase text-muted">Profit (NGN)</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    @for (scenario of fxScenarios(); track scenario.label) {
                      <tr class="transition-colors hover:bg-gray-50/50">
                        <td class="px-3 py-2 font-medium" [class]="scenario.colorClass">
                          <i class="pi mr-1 text-[10px]" [class]="scenario.icon"></i>
                          {{ scenario.label }}
                        </td>
                        <td class="px-3 py-2 text-right font-semibold">
                          {{ scenario.fxRate | number: '1.2-2' }}
                        </td>
                        <td class="px-3 py-2 text-right font-semibold">
                          {{ scenario.totalCostNgn | number: '1.0-0' }}
                        </td>
                        <td class="px-3 py-2 text-right font-semibold" [class]="scenario.profit >= 0 ? 'text-success' : 'text-danger'">
                          {{ scenario.profit | number: '1.0-0' }}
                        </td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
              <p class="mt-2 text-xs text-muted">
                Based on order FX rate {{ selectedOrder()!.fx_rate_at_creation | number: '1.2-2' }}.
                Revenue estimated as cost &times; 1.3 markup.
              </p>
            </div>
          }

          <!-- Status Transitions -->
          @if (nextStatuses(selectedOrder()!.status).length > 0) {
            <div class="space-y-3">
              @if (nextStatuses(selectedOrder()!.status).includes('DELIVERED')) {
                <div class="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <label for="order-delivery-fx-rate" class="mb-1.5 block text-xs font-medium text-muted">
                    FX Rate at Delivery (USDNGN)
                  </label>
                  <input
                    id="order-delivery-fx-rate"
                    type="number"
                    [(ngModel)]="deliveryFxRate"
                    step="0.01"
                    min="0"
                    placeholder="Enter current FX rate"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  />
                  @if (deliveryFxRate) {
                    <p class="mt-1 text-xs text-muted">
                      This rate will be recorded for cost comparison
                    </p>
                  }
                </div>
              }
              <div class="flex gap-2">
                @for (ns of nextStatuses(selectedOrder()!.status); track ns) {
                  <button
                    (click)="transitionStatus(selectedOrder()!.id, ns)"
                    class="flex items-center gap-1.5 rounded-lg border border-secondary px-4 py-2 text-sm font-semibold text-secondary transition-all hover:bg-secondary hover:text-white"
                  >
                    <i class="pi pi-arrow-right text-xs"></i> Move to {{ statusLabel[ns] }}
                  </button>
                }
              </div>
            </div>
          }
        </div>
      }
    </p-dialog>

    <!-- Create Order Dialog -->
    <p-dialog
      header="New Order"
      [(visible)]="showCreate"
      [modal]="true"
      [style]="{ width: '680px' }"
      [breakpoints]="{ '960px': '95vw' }"
    >
      <div class="space-y-4">
        <!-- PO vs Purchase toggle -->
        <div class="flex gap-4 rounded-lg bg-gray-50 p-3">
          <label class="flex cursor-pointer items-center gap-2 text-sm font-medium text-text">
            <input
              type="radio"
              name="order-type"
              [value]="false"
              [(ngModel)]="newOrder.is_purchase_order"
              class="accent-primary"
            />
            <span>Received Purchase</span>
            <span class="ml-1 rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">Updates stock</span>
          </label>
          <label class="flex cursor-pointer items-center gap-2 text-sm font-medium text-text">
            <input
              type="radio"
              name="order-type"
              [value]="true"
              [(ngModel)]="newOrder.is_purchase_order"
              class="accent-primary"
            />
            <span>Purchase Order</span>
            <span class="ml-1 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-700">No stock impact</span>
          </label>
        </div>

        <!-- Supplier & pay terms -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div class="sm:col-span-2">
            <label for="order-supplier" class="mb-1.5 block text-xs font-medium text-muted">Supplier</label>
            <input
              id="order-supplier"
              [(ngModel)]="newOrder.supplier_name"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              placeholder="Supplier name"
            />
          </div>
          <div>
            <label for="order-pay-term" class="mb-1.5 block text-xs font-medium text-muted">Pay Term</label>
            <div class="flex gap-1">
              <input
                id="order-pay-term"
                type="number"
                [(ngModel)]="newOrder.pay_term_number"
                placeholder="30"
                min="1"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              />
              <select
                [(ngModel)]="newOrder.pay_term_type"
                class="rounded-lg border border-gray-300 px-2 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="">—</option>
                <option value="days">Days</option>
                <option value="months">Months</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Line items -->
        <div>
          <div class="mb-2 flex items-center justify-between">
            <label class="text-xs font-medium text-muted">Items</label>
            <div class="flex items-center gap-3">
              <a [href]="productsTemplateUrl" download="products_import_template.csv"
                class="text-xs text-muted hover:text-secondary hover:underline">
                <i class="pi pi-download text-[10px]"></i> Template
              </a>
              <label class="flex cursor-pointer items-center gap-1 text-xs font-medium text-secondary hover:text-primary hover:underline">
                <i class="pi pi-upload text-[10px]"></i> Import Products
                <input type="file" accept=".csv,.xlsx,.xls" class="hidden" (change)="onImportProductsFile($event)" />
              </label>
            </div>
          </div>

          @if (parseProductsErrors().length > 0) {
            <div class="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              <p class="font-semibold">Import errors:</p>
              @for (e of parseProductsErrors(); track $index) {
                <p>Row {{ e.row }}: {{ e.message }}</p>
              }
            </div>
          }

          @for (item of newOrderItems(); track $index) {
            <div class="mb-2 flex flex-wrap gap-2">
              <select
                [(ngModel)]="item.product_id"
                class="flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="">Select product</option>
                @for (p of products(); track p.id) {
                  <option [value]="p.id">{{ p.name }}</option>
                }
              </select>
              <input type="number" [(ngModel)]="item.quantity" placeholder="Qty" min="1"
                class="w-20 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
              <input type="number" [(ngModel)]="item.unit_cost" placeholder="$/unit" min="0" step="0.01"
                class="w-24 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
              <button type="button" (click)="removeOrderItem($index)"
                class="rounded p-1.5 text-muted hover:bg-red-50 hover:text-red-500">
                <i class="pi pi-times text-xs"></i>
              </button>
            </div>
          }
          <button (click)="addOrderItem()" type="button"
            class="text-xs font-medium text-secondary hover:text-primary hover:underline">
            <i class="pi pi-plus text-[10px]"></i> Add item
          </button>
        </div>

        <!-- Lead times -->
        <div class="grid grid-cols-3 gap-3">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Production (days)</label>
            <input type="number" [(ngModel)]="newOrder.production_days" min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Shipping (days)</label>
            <input type="number" [(ngModel)]="newOrder.shipping_days" min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Clearing (days)</label>
            <input type="number" [(ngModel)]="newOrder.clearing_days" min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
        </div>

        <!-- Shipping charges -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Shipping Charges</label>
            <input type="number" [(ngModel)]="newOrder.shipping_cost" min="0" step="0.01" placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Clearing Charges</label>
            <input type="number" [(ngModel)]="newOrder.clearing_cost" min="0" step="0.01" placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
        </div>

        <!-- Additional expenses -->
        <div>
          <p class="mb-2 text-xs font-semibold uppercase text-muted">Additional Expenses</p>
          @for (exp of newOrder.expenses; track $index) {
            <div class="mb-2 flex gap-2">
              <input type="text" [(ngModel)]="exp.key" placeholder="Label (e.g. Customs)"
                class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
              <input type="number" [(ngModel)]="exp.value" placeholder="Amount" min="0" step="0.01"
                class="w-32 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
            </div>
          }
          @if (newOrder.expenses.length < 4) {
            <button type="button" (click)="addExpense()"
              class="text-xs font-medium text-secondary hover:text-primary hover:underline">
              <i class="pi pi-plus text-[10px]"></i> Add expense
            </button>
          }
        </div>

        <!-- Discount & Tax -->
        <div class="grid grid-cols-3 gap-3">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Discount</label>
            <div class="flex gap-1">
              <select [(ngModel)]="newOrder.discount_type"
                class="rounded-lg border border-gray-300 px-2 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary">
                <option value="">None</option>
                <option value="percentage">%</option>
                <option value="fixed">Fixed</option>
              </select>
              <input type="number" [(ngModel)]="newOrder.discount_amount" min="0" step="0.01" placeholder="0"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
            </div>
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Tax Rate (%)</label>
            <input type="number" [(ngModel)]="newOrder.tax_rate" min="0" step="0.1" placeholder="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Supplier Invoice #</label>
            <input type="text" [(ngModel)]="newOrder.supplier_invoice_number" placeholder="INV-001"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary" />
          </div>
        </div>

        <!-- Shipping details -->
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Shipping Details / Notes</label>
          <textarea [(ngModel)]="newOrder.shipping_details" rows="2" placeholder="Delivery instructions, container number, etc."
            class="w-full resize-none rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"></textarea>
        </div>

        <button
          (click)="createOrder()"
          [disabled]="creating()"
          class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
        >
          @if (creating()) {
            <i class="pi pi-spinner pi-spin text-sm"></i> Creating...
          } @else {
            <i class="pi pi-check text-sm"></i>
            {{ newOrder.is_purchase_order ? 'Create Purchase Order' : 'Create Purchase' }}
          }
        </button>
      </div>
    </p-dialog>

    <!-- Import Orders Dialog -->
    <p-dialog
      header="Import Orders"
      [(visible)]="showImport"
      [modal]="true"
      [style]="{ width: '520px' }"
      [breakpoints]="{ '768px': '95vw' }"
    >
      <div class="space-y-5">
        <!-- Step 1: Download template -->
        <div class="rounded-lg border border-gray-200 p-4">
          <p class="mb-1 text-sm font-semibold text-text">Step 1 — Download the template</p>
          <p class="mb-3 text-xs text-muted">
            One row per product. Order-level fields (shipping, discount, tax…) go on the
            <strong>first row</strong> of each order only — leave them blank on subsequent rows
            for the same order. Start a new order by filling in <code>supplier_name</code> again.
          </p>
          <a
            [href]="templateUrl"
            download="orders_import_template.csv"
            class="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-text transition-colors hover:bg-gray-50"
          >
            <i class="pi pi-download text-sm"></i> Download Template (CSV)
          </a>
        </div>

        <!-- Step 2: Upload file -->
        <div class="rounded-lg border border-gray-200 p-4">
          <p class="mb-1 text-sm font-semibold text-text">Step 2 — Upload your file</p>
          <p class="mb-3 text-xs text-muted">Accepts .csv and .xlsx files.</p>
          <label
            class="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-gray-300 p-6 text-center transition-colors hover:border-primary hover:bg-primary/5"
            (dragover)="$event.preventDefault()"
            (drop)="onFileDrop($event)"
          >
            <i class="pi pi-file-import mb-2 text-2xl text-muted"></i>
            @if (importFile()) {
              <p class="text-sm font-medium text-text">{{ importFile()!.name }}</p>
              <p class="text-xs text-muted">{{ importRowCount() }} row(s) detected</p>
            } @else {
              <p class="text-sm text-muted">Click or drag a file here</p>
            }
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              class="hidden"
              (change)="onFileSelect($event)"
            />
          </label>
        </div>

        <!-- Error table -->
        @if (importErrors().length > 0) {
          <div class="rounded-lg border border-red-200 bg-red-50 p-3">
            <p class="mb-2 text-sm font-semibold text-red-700">
              Import failed — {{ importErrors().length }} error(s):
            </p>
            <div class="max-h-40 overflow-y-auto">
              <table class="min-w-full text-xs">
                <thead>
                  <tr>
                    <th class="pr-4 text-left font-semibold text-red-700">Row</th>
                    <th class="text-left font-semibold text-red-700">Error</th>
                  </tr>
                </thead>
                <tbody>
                  @for (err of importErrors(); track $index) {
                    <tr>
                      <td class="pr-4 text-red-600">{{ err.row }}</td>
                      <td class="text-red-600">{{ err.message }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        }

        <button
          (click)="submitImport()"
          [disabled]="!importFile() || importing()"
          class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50"
        >
          @if (importing()) {
            <i class="pi pi-spinner pi-spin text-sm"></i> Importing...
          } @else {
            <i class="pi pi-check text-sm"></i> Submit Import
          }
        </button>
      </div>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrdersPageComponent implements OnInit {
  private readonly ordersService = inject(OrdersService);
  private readonly productsService = inject(ProductsService);
  private readonly fxService = inject(FxService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly router = inject(Router);

  pageLoading = signal(true);
  orders = signal<Order[]>([]);
  ordersTotal = signal(0);
  ordersPage = signal(1);
  ordersPageSize = signal(20);
  ordersTotalPages = computed(() => Math.max(1, Math.ceil(this.ordersTotal() / this.ordersPageSize())));
  ordersShowingFrom = computed(() => this.ordersTotal() === 0 ? 0 : (this.ordersPage() - 1) * this.ordersPageSize() + 1);
  ordersShowingTo = computed(() => Math.min(this.ordersPage() * this.ordersPageSize(), this.ordersTotal()));
  ordersPageNumbers = computed(() => {
    const total = this.ordersTotalPages();
    const current = this.ordersPage();
    const start = Math.max(1, Math.min(current - 2, total - 4));
    const end = Math.min(total, start + 4);
    const pages: number[] = [];
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  });
  products = signal<Product[]>([]);
  selectedOrder = signal<Order | null>(null);
  pipelineFilter = signal<string | null>(null);
  displayedOrders = computed(() => this.orders());
  detailVisible = false;
  showCreate = false;
  creating = signal(false);

  // Import state
  showImport = false;
  importFile = signal<File | null>(null);
  importRowCount = signal(0);
  importing = signal(false);
  importErrors = signal<ImportRowError[]>([]);
  readonly templateUrl = this.ordersService.getImportTemplateUrl();
  deliveryFxRate: number | null = null;

  fxScenarios = computed(() => {
    const order = this.selectedOrder();
    if (!order || !order.fx_rate_at_creation) return [];
    const baseRate = order.fx_rate_at_creation;
    const totalUsd = order.total_amount;
    // Revenue is fixed in NGN at the time of pricing (cost × 1.3 at creation rate).
    // Profit = fixedRevenueNgn − costAtScenarioRate, so profit falls as FX rate rises.
    const revenueNgn = totalUsd * baseRate * 1.3;
    return [
      {
        label: 'Best Case',
        fxRate: baseRate * 0.9,
        totalCostNgn: totalUsd * baseRate * 0.9,
        profit: revenueNgn - totalUsd * baseRate * 0.9,
        colorClass: 'text-success',
        icon: 'pi-arrow-down',
      },
      {
        label: 'Base',
        fxRate: baseRate,
        totalCostNgn: totalUsd * baseRate,
        profit: revenueNgn - totalUsd * baseRate,
        colorClass: 'text-text',
        icon: 'pi-minus',
      },
      {
        label: 'Worst Case',
        fxRate: baseRate * 1.1,
        totalCostNgn: totalUsd * baseRate * 1.1,
        profit: revenueNgn - totalUsd * baseRate * 1.1,
        colorClass: 'text-danger',
        icon: 'pi-arrow-up',
      },
    ];
  });

  newOrder: {
    supplier_name: string;
    is_purchase_order: boolean;
    production_days: number;
    shipping_days: number;
    clearing_days: number;
    shipping_cost: number;
    clearing_cost: number;
    pay_term_number: number | null;
    pay_term_type: string;
    discount_type: string;
    discount_amount: number;
    tax_rate: number | null;
    supplier_invoice_number: string;
    shipping_details: string;
    expenses: { key: string; value: number | null }[];
  } = this.emptyOrder();
  newOrderItems = signal<{ product_id: string; quantity: number; unit_cost: number }[]>([
    { product_id: '', quantity: 1, unit_cost: 0 },
  ]);

  parseProductsErrors = signal<{ row: number; message: string }[]>([]);
  readonly productsTemplateUrl = this.ordersService.getProductsTemplateUrl();

  readonly pipelineStatuses = ['ORDERED', 'PENDING', 'IN_PRODUCTION', 'SHIPPING', 'CLEARED', 'DELIVERED'] as const;

  readonly statusLabel: Record<string, string> = {
    ORDERED: 'Ordered',
    PENDING: 'Pending',
    IN_PRODUCTION: 'In Production',
    SHIPPING: 'Shipping',
    CLEARED: 'Cleared',
    DELIVERED: 'Delivered',
  };

  private readonly statusTransitions: Record<string, string[]> = {
    ORDERED: ['PENDING'],
    PENDING: ['IN_PRODUCTION'],
    IN_PRODUCTION: ['SHIPPING'],
    SHIPPING: ['CLEARED'],
    CLEARED: ['DELIVERED'],
  };

  ngOnInit(): void {
    this.loadOrders();
    this.productsService.getAll().subscribe({ next: (p) => this.products.set(p) });
  }

  private loadOrders(): void {
    this.pageLoading.set(true);
    const params: Record<string, string> = {
      page: String(this.ordersPage()),
      page_size: String(this.ordersPageSize()),
    };
    const filter = this.pipelineFilter();
    if (filter) params['order_status'] = filter;
    this.ordersService.getAll(params).subscribe({
      next: ({ items, total }) => {
        this.orders.set(items);
        this.ordersTotal.set(total);
        this.pageLoading.set(false);
      },
      error: () => { this.pageLoading.set(false); },
    });
  }

  ordersGoToPage(page: number): void {
    const p = Math.max(1, Math.min(page, this.ordersTotalPages()));
    this.ordersPage.set(p);
    this.loadOrders();
  }

  ordersByStatus(status: string): Order[] {
    return this.orders().filter((o) => o.status === status);
  }

  togglePipelineFilter(status: string | null): void {
    this.pipelineFilter.set(this.pipelineFilter() === status ? null : status);
    this.ordersPage.set(1);
    this.loadOrders();
  }

  orderStatus(status: string): 'info' | 'warning' | 'success' | 'neutral' {
    if (status === 'DELIVERED') return 'success';
    if (status === 'SHIPPING' || status === 'CLEARED') return 'warning';
    if (status === 'IN_PRODUCTION' || status === 'ORDERED' || status === 'PENDING') return 'info';
    return 'neutral';
  }

  productName(productId: string): string {
    return this.products().find((p) => p.id === productId)?.name ?? productId;
  }

  viewOrder(order: Order): void {
    this.router.navigate(['/orders', order.id]);
  }

  nextStatuses(status: string): string[] {
    return this.statusTransitions[status] ?? [];
  }

  transitionStatus(id: string, newStatus: string): void {
    const fxRate = newStatus === 'DELIVERED' && this.deliveryFxRate
      ? this.deliveryFxRate
      : undefined;
    this.ordersService.updateStatus(id, newStatus, fxRate).subscribe({
      next: (updated) => {
        this.selectedOrder.set(updated);
        this.deliveryFxRate = null;
        this.messageService.add({
          severity: 'success',
          summary: 'Updated',
          detail: `Order moved to ${this.statusLabel[newStatus] ?? newStatus}`,
        });
        this.loadOrders();
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Status update failed',
        });
      },
    });
  }

  addOrderItem(): void {
    this.newOrderItems.update((items) => [
      ...items,
      { product_id: '', quantity: 1, unit_cost: 0 },
    ]);
  }

  removeOrderItem(index: number): void {
    this.newOrderItems.update((items) => items.filter((_, i) => i !== index));
  }

  onImportProductsFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    input.value = '';
    this.parseProductsErrors.set([]);
    this.ordersService.parseProducts(file).subscribe({
      next: (result) => {
        if (result.errors.length > 0) {
          this.parseProductsErrors.set(result.errors);
        }
        if (result.items.length > 0) {
          const imported = result.items.map((item: ParsedLineItem) => ({
            product_id: item.product_id,
            quantity: item.quantity,
            unit_cost: item.unit_cost,
          }));
          // Replace any empty placeholder rows, then append imported
          const existing = this.newOrderItems().filter(
            (i) => i.product_id || i.quantity > 0 || i.unit_cost > 0,
          );
          this.newOrderItems.set([...existing, ...imported]);
        }
      },
      error: () => {
        this.parseProductsErrors.set([
          { row: 0, message: 'Failed to parse file. Check format and try again.' },
        ]);
      },
    });
  }

  createOrder(): void {
    const validItems = this.newOrderItems().filter((i) => i.product_id && i.quantity > 0 && i.unit_cost > 0);
    if (!this.newOrder.supplier_name || validItems.length === 0) return;

    this.creating.set(true);
    const exps = this.newOrder.expenses.filter(e => e.key && e.value != null);
    const payload: CreateOrderPayload = {
      supplier_name: this.newOrder.supplier_name,
      is_purchase_order: this.newOrder.is_purchase_order,
      line_items: validItems,
      production_days: this.newOrder.production_days,
      shipping_days: this.newOrder.shipping_days,
      clearing_days: this.newOrder.clearing_days,
      shipping_cost: this.newOrder.shipping_cost || 0,
      clearing_cost: this.newOrder.clearing_cost || 0,
      pay_term_number: this.newOrder.pay_term_number,
      pay_term_type: this.newOrder.pay_term_type || null,
      shipping_details: this.newOrder.shipping_details || null,
      discount_type: this.newOrder.discount_type || null,
      discount_amount: this.newOrder.discount_amount || 0,
      tax_rate: this.newOrder.tax_rate,
      supplier_invoice_number: this.newOrder.supplier_invoice_number || null,
      additional_expense_key_1: exps[0]?.key ?? null,
      additional_expense_value_1: exps[0]?.value ?? null,
      additional_expense_key_2: exps[1]?.key ?? null,
      additional_expense_value_2: exps[1]?.value ?? null,
      additional_expense_key_3: exps[2]?.key ?? null,
      additional_expense_value_3: exps[2]?.value ?? null,
      additional_expense_key_4: exps[3]?.key ?? null,
      additional_expense_value_4: exps[3]?.value ?? null,
    };
    this.ordersService.create(payload).subscribe({
      next: () => {
        this.creating.set(false);
        this.showCreate = false;
        this.newOrder = this.emptyOrder();
        this.newOrderItems.set([{ product_id: '', quantity: 1, unit_cost: 0 }]);
        this.parseProductsErrors.set([]);
        this.messageService.add({
          severity: 'success',
          summary: 'Created',
          detail: 'Order created successfully',
        });
        this.loadOrders();
      },
      error: () => {
        this.creating.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to create order',
        });
      },
    });
  }

  private emptyOrder() {
    return {
      supplier_name: '',
      is_purchase_order: false,
      production_days: 30,
      shipping_days: 21,
      clearing_days: 14,
      shipping_cost: 0,
      clearing_cost: 0,
      pay_term_number: null as number | null,
      pay_term_type: '',
      discount_type: '',
      discount_amount: 0,
      tax_rate: null as number | null,
      supplier_invoice_number: '',
      shipping_details: '',
      expenses: [] as { key: string; value: number | null }[],
    };
  }

  addExpense(): void {
    if (this.newOrder.expenses.length < 4) {
      this.newOrder.expenses = [...this.newOrder.expenses, { key: '', value: null }];
    }
  }

  exportOrdersCsv(): void {
    this.ordersService.exportCsv().subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'orders_export.csv';
        link.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to export orders CSV',
        });
      },
    });
  }

  openImportDialog(): void {
    this.importFile.set(null);
    this.importRowCount.set(0);
    this.importErrors.set([]);
    this.showImport = true;
  }

  onFileSelect(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.setImportFile(file);
  }

  onFileDrop(event: DragEvent): void {
    event.preventDefault();
    const file = event.dataTransfer?.files[0] ?? null;
    this.setImportFile(file);
  }

  private setImportFile(file: File | null): void {
    this.importFile.set(file);
    this.importErrors.set([]);
    if (!file) {
      this.importRowCount.set(0);
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? '';
      const lines = text.split('\n').filter((l) => l.trim().length > 0);
      this.importRowCount.set(Math.max(0, lines.length - 1)); // subtract header
    };
    reader.readAsText(file);
  }

  submitImport(): void {
    const file = this.importFile();
    if (!file) return;
    this.importing.set(true);
    this.importErrors.set([]);
    this.ordersService.importOrders(file).subscribe({
      next: (result: BulkImportResult) => {
        this.importing.set(false);
        if (result.errors.length > 0) {
          this.importErrors.set(result.errors);
        } else {
          this.showImport = false;
          this.messageService.add({
            severity: 'success',
            summary: 'Import complete',
            detail: `${result.created} order(s) created successfully`,
          });
          this.loadOrders();
        }
      },
      error: (err) => {
        this.importing.set(false);
        const detail =
          err?.error?.detail ?? 'Failed to import orders. Check the file format.';
        this.messageService.add({ severity: 'error', summary: 'Import failed', detail });
      },
    });
  }
}
