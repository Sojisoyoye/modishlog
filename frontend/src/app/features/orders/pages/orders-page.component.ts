import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CurrencyPipe, DatePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  OrdersService,
  Order,
  ProfitProjection,
  CreateOrderPayload,
} from '../../../core/services/orders.service';
import { ProductsService, Product } from '../../../core/services/products.service';

@Component({
  selector: 'app-orders-page',
  standalone: true,
  imports: [FormsModule, CurrencyPipe, DatePipe, Toast, Dialog, StatusBadgeComponent],
  template: `
    <p-toast />
    <div>
      <div class="mb-6 flex items-center justify-between">
        <h2 class="text-xl font-bold text-text">Orders</h2>
        <button
          (click)="showCreate = true"
          class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
        >
          <i class="pi pi-plus mr-1"></i> New Order
        </button>
      </div>

      <!-- Pipeline View -->
      <div class="mb-6 flex gap-4 overflow-x-auto pb-2">
        @for (status of pipelineStatuses; track status) {
          <div class="min-w-48 rounded-lg border border-gray-200 bg-surface p-4">
            <h4 class="mb-3 text-xs font-semibold uppercase text-muted">{{ status }}</h4>
            <div class="space-y-2">
              @for (order of ordersByStatus(status); track order.id) {
                <div
                  (click)="viewOrder(order)"
                  class="cursor-pointer rounded-lg border border-gray-100 p-3 hover:border-secondary"
                >
                  <p class="text-sm font-medium text-text">{{ order.order_number }}</p>
                  <p class="text-xs text-muted">{{ order.supplier }}</p>
                  <p class="mt-1 text-sm font-semibold text-text">
                    {{ order.total_usd | currency: 'USD' : 'symbol' : '1.0-0' }}
                  </p>
                </div>
              }
              @if (ordersByStatus(status).length === 0) {
                <p class="text-xs text-muted">No orders</p>
              }
            </div>
          </div>
        }
      </div>

      <!-- Orders Table -->
      <div class="rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">All Orders</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Order #</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Supplier</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Total (USD)</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Status</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">ETA</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">FX Locked</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">FX Float</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              @for (order of orders(); track order.id) {
                <tr class="cursor-pointer hover:bg-gray-50" (click)="viewOrder(order)">
                  <td class="px-3 py-2 font-medium text-secondary">{{ order.order_number }}</td>
                  <td class="px-3 py-2">{{ order.supplier }}</td>
                  <td class="px-3 py-2 text-right">
                    {{ order.total_usd | currency: 'USD' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2">
                    <app-status-badge [label]="order.status" [status]="orderStatus(order.status)" />
                  </td>
                  <td class="px-3 py-2 text-muted">
                    {{ order.estimated_arrival_date ? (order.estimated_arrival_date | date: 'mediumDate') : '--' }}
                  </td>
                  <td class="px-3 py-2 text-right text-success">
                    {{ order.locked_amount_usd | currency: 'USD' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-3 py-2 text-right text-warning">
                    {{ order.floating_amount_usd | currency: 'USD' : 'symbol' : '1.0-0' }}
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7" class="px-3 py-8 text-center text-muted">No orders found</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Order Detail Dialog -->
    <p-dialog
      header="Order Details"
      [(visible)]="detailVisible"
      [modal]="true"
      [style]="{ width: '600px' }"
    >
      @if (selectedOrder()) {
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <h4 class="font-bold text-text">{{ selectedOrder()!.order_number }}</h4>
            <app-status-badge [label]="selectedOrder()!.status" [status]="orderStatus(selectedOrder()!.status)" />
          </div>
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p class="text-xs text-muted">Supplier</p>
              <p class="font-medium">{{ selectedOrder()!.supplier }}</p>
            </div>
            <div>
              <p class="text-xs text-muted">Order Date</p>
              <p class="font-medium">{{ selectedOrder()!.order_date | date: 'mediumDate' }}</p>
            </div>
            <div>
              <p class="text-xs text-muted">Total (USD)</p>
              <p class="font-medium">{{ selectedOrder()!.total_usd | currency: 'USD' }}</p>
            </div>
            <div>
              <p class="text-xs text-muted">ETA</p>
              <p class="font-medium">
                {{ selectedOrder()!.estimated_arrival_date ? (selectedOrder()!.estimated_arrival_date | date: 'mediumDate') : 'TBD' }}
              </p>
            </div>
          </div>

          <!-- FX Exposure -->
          <div class="rounded-lg border border-gray-200 p-3">
            <p class="mb-2 text-xs font-semibold uppercase text-muted">FX Exposure</p>
            <div class="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p class="text-xs text-muted">Locked (30%)</p>
                <p class="font-medium text-success">
                  {{ selectedOrder()!.locked_amount_usd | currency: 'USD' }}
                </p>
              </div>
              <div>
                <p class="text-xs text-muted">Floating (70%)</p>
                <p class="font-medium text-warning">
                  {{ selectedOrder()!.floating_amount_usd | currency: 'USD' }}
                </p>
              </div>
            </div>
          </div>

          <!-- Status Transitions -->
          @if (nextStatuses(selectedOrder()!.status).length > 0) {
            <div class="flex gap-2">
              @for (ns of nextStatuses(selectedOrder()!.status); track ns) {
                <button
                  (click)="transitionStatus(selectedOrder()!.id, ns)"
                  class="rounded-lg border border-secondary px-3 py-1.5 text-sm font-medium text-secondary hover:bg-secondary hover:text-white"
                >
                  Move to {{ ns }}
                </button>
              }
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
      [style]="{ width: '600px' }"
    >
      <div class="space-y-4">
        <div>
          <label class="mb-1 block text-xs font-medium text-muted">Supplier</label>
          <input
            [(ngModel)]="newOrder.supplier"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            placeholder="Supplier name"
          />
        </div>

        <div>
          <label class="mb-1 block text-xs font-medium text-muted">Items</label>
          @for (item of newOrderItems(); track $index) {
            <div class="mb-2 flex gap-2">
              <select
                [(ngModel)]="item.product_id"
                class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="">Select product</option>
                @for (p of products(); track p.id) {
                  <option [value]="p.id">{{ p.name }}</option>
                }
              </select>
              <input
                type="number"
                [(ngModel)]="item.quantity"
                placeholder="Qty"
                min="1"
                class="w-20 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
              <input
                type="number"
                [(ngModel)]="item.unit_cost_usd"
                placeholder="$/unit"
                min="0"
                step="0.01"
                class="w-24 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
          }
          <button
            (click)="addOrderItem()"
            class="text-xs text-secondary hover:underline"
            type="button"
          >
            + Add item
          </button>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Production (days)</label>
            <input
              type="number"
              [(ngModel)]="newOrder.production_days"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Shipping (days)</label>
            <input
              type="number"
              [(ngModel)]="newOrder.shipping_days"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Clearing (days)</label>
            <input
              type="number"
              [(ngModel)]="newOrder.clearing_days"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
        </div>

        <button
          (click)="createOrder()"
          [disabled]="creating()"
          class="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
        >
          {{ creating() ? 'Creating...' : 'Create Order' }}
        </button>
      </div>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrdersPageComponent implements OnInit {
  private readonly ordersService = inject(OrdersService);
  private readonly productsService = inject(ProductsService);
  private readonly messageService = inject(MessageService);

  orders = signal<Order[]>([]);
  products = signal<Product[]>([]);
  selectedOrder = signal<Order | null>(null);
  detailVisible = false;
  showCreate = false;
  creating = signal(false);

  newOrder = { supplier: '', production_days: 30, shipping_days: 21, clearing_days: 14 };
  newOrderItems = signal<{ product_id: string; quantity: number; unit_cost_usd: number }[]>([
    { product_id: '', quantity: 1, unit_cost_usd: 0 },
  ]);

  readonly pipelineStatuses = ['PENDING', 'IN_PRODUCTION', 'SHIPPED', 'CLEARING', 'DELIVERED'];

  private readonly statusTransitions: Record<string, string[]> = {
    PENDING: ['IN_PRODUCTION'],
    IN_PRODUCTION: ['SHIPPED'],
    SHIPPED: ['CLEARING'],
    CLEARING: ['DELIVERED'],
  };

  ngOnInit(): void {
    this.loadOrders();
    this.productsService.getAll().subscribe({ next: (p) => this.products.set(p) });
  }

  private loadOrders(): void {
    this.ordersService.getAll().subscribe({ next: (o) => this.orders.set(o) });
  }

  ordersByStatus(status: string): Order[] {
    return this.orders().filter((o) => o.status === status);
  }

  orderStatus(status: string): 'info' | 'warning' | 'success' | 'neutral' {
    if (status === 'DELIVERED') return 'success';
    if (status === 'SHIPPED' || status === 'CLEARING') return 'warning';
    if (status === 'IN_PRODUCTION') return 'info';
    return 'neutral';
  }

  viewOrder(order: Order): void {
    this.selectedOrder.set(order);
    this.detailVisible = true;
  }

  nextStatuses(status: string): string[] {
    return this.statusTransitions[status] ?? [];
  }

  transitionStatus(id: string, newStatus: string): void {
    this.ordersService.updateStatus(id, newStatus).subscribe({
      next: (updated) => {
        this.selectedOrder.set(updated);
        this.messageService.add({
          severity: 'success',
          summary: 'Updated',
          detail: `Order moved to ${newStatus}`,
        });
        this.loadOrders();
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Status update failed' });
      },
    });
  }

  addOrderItem(): void {
    this.newOrderItems.update((items) => [...items, { product_id: '', quantity: 1, unit_cost_usd: 0 }]);
  }

  createOrder(): void {
    const validItems = this.newOrderItems().filter((i) => i.product_id && i.quantity > 0);
    if (!this.newOrder.supplier || validItems.length === 0) return;

    this.creating.set(true);
    const payload: CreateOrderPayload = { ...this.newOrder, items: validItems };
    this.ordersService.create(payload).subscribe({
      next: () => {
        this.creating.set(false);
        this.showCreate = false;
        this.newOrder = { supplier: '', production_days: 30, shipping_days: 21, clearing_days: 14 };
        this.newOrderItems.set([{ product_id: '', quantity: 1, unit_cost_usd: 0 }]);
        this.messageService.add({ severity: 'success', summary: 'Created', detail: 'Order created successfully' });
        this.loadOrders();
      },
      error: () => {
        this.creating.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create order' });
      },
    });
  }
}
