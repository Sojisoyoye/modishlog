import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, CurrencyPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { SalesService, SaleRecord, SalesHistoryResponse } from '../../../core/services/sales.service';
import { ProductsService, Product } from '../../../core/services/products.service';

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
      <h2 class="mb-6 text-xl font-bold text-text">Sales</h2>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <!-- Entry Form -->
        <div class="rounded-lg border border-gray-200 bg-surface p-5">
          <h3 class="mb-4 text-base font-semibold text-text">Record Sales</h3>

          @for (row of entryRows(); track $index) {
            <div class="mb-3 flex items-end gap-3">
              <div class="flex-1">
                @if ($index === 0) {
                  <label class="mb-1 block text-xs font-medium text-muted">Product</label>
                }
                <select
                  [(ngModel)]="row.product_id"
                  [name]="'product_' + $index"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                >
                  <option value="">Select product</option>
                  @for (p of products(); track p.id) {
                    <option [value]="p.id">{{ p.name }}</option>
                  }
                </select>
              </div>
              <div class="w-24">
                @if ($index === 0) {
                  <label class="mb-1 block text-xs font-medium text-muted">Qty</label>
                }
                <input
                  type="number"
                  [(ngModel)]="row.quantity"
                  [name]="'qty_' + $index"
                  min="1"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
              <div class="w-36">
                @if ($index === 0) {
                  <label class="mb-1 block text-xs font-medium text-muted">Date</label>
                }
                <input
                  type="date"
                  [(ngModel)]="row.sale_date"
                  [name]="'date_' + $index"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                />
              </div>
              @if (entryRows().length > 1) {
                <button
                  (click)="removeRow($index)"
                  class="rounded p-2 text-danger hover:bg-red-50"
                  type="button"
                >
                  <i class="pi pi-trash text-sm"></i>
                </button>
              }
            </div>
          }

          <div class="mt-3 flex gap-3">
            <button
              (click)="addRow()"
              class="rounded-lg border border-gray-300 px-3 py-2 text-sm text-muted hover:bg-gray-50"
              type="button"
            >
              <i class="pi pi-plus mr-1"></i> Add Row
            </button>
            <button
              (click)="submitEntries()"
              [disabled]="submitting()"
              class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
            >
              @if (submitting()) {
                Saving...
              } @else {
                Record Sales
              }
            </button>
          </div>
        </div>

        <!-- Sales History -->
        <div class="rounded-lg border border-gray-200 bg-surface p-5">
          <h3 class="mb-4 text-base font-semibold text-text">Recent Sales</h3>

          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Date</th>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Product</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Qty</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Total</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                @for (sale of history(); track sale.id) {
                  <tr class="hover:bg-gray-50">
                    <td class="px-3 py-2 text-muted">{{ sale.sale_date | date: 'mediumDate' }}</td>
                    <td class="px-3 py-2">{{ sale.product_name }}</td>
                    <td class="px-3 py-2 text-right">{{ sale.quantity }}</td>
                    <td class="px-3 py-2 text-right">
                      {{ sale.total_amount | currency: 'NGN' : 'symbol' : '1.0-0' }}
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="4" class="px-3 py-6 text-center text-muted">No sales recorded yet</td>
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
  private readonly messageService = inject(MessageService);

  products = signal<Product[]>([]);
  history = signal<SaleRecord[]>([]);
  entryRows = signal<EntryRow[]>([this.newRow()]);
  submitting = signal(false);

  ngOnInit(): void {
    this.productsService.getAll().subscribe({ next: (p) => this.products.set(p) });
    this.loadHistory();
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
