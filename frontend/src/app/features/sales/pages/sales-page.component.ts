import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, CurrencyPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import {
  SalesService,
  SaleRecord,
  SalesHistoryResponse,
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
  imports: [FormsModule, DatePipe, CurrencyPipe, Toast],
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
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (sale of history(); track sale.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 text-muted">
                      {{ sale.sale_date | date: 'mediumDate' }}
                    </td>
                    <td class="px-3 py-2.5 font-medium">{{ sale.product_name }}</td>
                    <td class="px-3 py-2.5 text-right">{{ sale.quantity }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold">
                      {{ sale.total_amount | currency: 'NGN' : 'symbol' : '1.0-0' }}
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="4" class="px-3 py-10 text-center text-sm text-muted">
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
  stockMap = signal<Map<string, number>>(new Map());

  hasStockExceeded = computed(() => {
    const map = this.stockMap();
    return this.entryRows().some((row) => {
      if (!row.product_id) return false;
      const available = map.get(row.product_id);
      return available !== undefined && row.quantity > available;
    });
  });

  ngOnInit(): void {
    this.productsService.getAll().subscribe({ next: (p) => this.products.set(p) });
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

  exceedsStock(row: EntryRow): boolean {
    if (!row.product_id) return false;
    const available = this.stockMap().get(row.product_id);
    return available !== undefined && row.quantity > available;
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

  private loadHistory(): void {
    this.salesService.getHistory({ limit: '20' }).subscribe({
      next: (r) => this.history.set(r.items ?? []),
    });
  }
}
