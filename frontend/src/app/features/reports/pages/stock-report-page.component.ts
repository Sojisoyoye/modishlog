import { Component, ChangeDetectionStrategy, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ReportsService, StockReport } from '../../../core/services/reports.service';

@Component({
  selector: 'app-stock-report-page',
  standalone: true,
  imports: [DecimalPipe, Toast],
  providers: [MessageService],
  template: `
    <p-toast />
    <div>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-text">Stock Report</h2>
          <p class="mt-1 text-sm text-muted">Current inventory valuation and potential profit</p>
        </div>
        <div class="flex items-center gap-3">
          @if (report()) {
            <button
              type="button"
              (click)="exportCsv()"
              class="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
            >
              <i class="pi pi-download text-sm"></i> Export CSV
            </button>
          }
          <button
            type="button"
            (click)="generateReport()"
            [disabled]="loading()"
            class="flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
          >
            @if (loading()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Generating...
            } @else {
              <i class="pi pi-play text-sm"></i> Generate Report
            }
          </button>
        </div>
      </div>

      @if (report(); as r) {
        <!-- Summary cards -->
        <div class="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-muted">Total Stock Value</p>
            <p class="mt-1 text-2xl font-bold text-text">{{ r.total_stock_value | number: '1.2-2' }}</p>
          </div>
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-muted">Total Potential Profit</p>
            <p class="mt-1 text-2xl font-bold text-green-600">{{ r.total_potential_profit | number: '1.2-2' }}</p>
          </div>
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-muted">Total Units Sold</p>
            <p class="mt-1 text-2xl font-bold text-text">{{ r.total_sold | number: '1.0-0' }}</p>
          </div>
        </div>

        <!-- Table -->
        <div class="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Stock report items</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">SKU</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Product</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Category</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Unit Cost</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Qty</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Stock Value</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Potential Profit</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Total Sold</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (item of r.items; track item.product_id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 font-mono text-xs text-muted">{{ item.sku }}</td>
                    <td class="px-3 py-2.5 font-medium text-text">{{ item.product_name }}</td>
                    <td class="px-3 py-2.5 text-muted">{{ item.category ?? '—' }}</td>
                    <td class="px-3 py-2.5 text-right">{{ item.unit_cost | number: '1.2-2' }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold">{{ item.quantity_on_hand | number: '1.0-0' }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold text-text">{{ item.stock_value | number: '1.2-2' }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold text-green-600">{{ item.potential_profit | number: '1.2-2' }}</td>
                    <td class="px-3 py-2.5 text-right">{{ item.total_sold | number: '1.0-0' }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="8" class="px-3 py-10 text-center text-muted">
                      <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                      No stock data available
                    </td>
                  </tr>
                }
              </tbody>
              <!-- Footer totals -->
              <tfoot>
                <tr class="border-t-2 border-gray-300 bg-gray-50 font-semibold">
                  <td colspan="5" class="px-3 py-2.5 text-xs font-bold uppercase text-muted">Totals</td>
                  <td class="px-3 py-2.5 text-right font-bold text-text">{{ r.total_stock_value | number: '1.2-2' }}</td>
                  <td class="px-3 py-2.5 text-right font-bold text-green-600">{{ r.total_potential_profit | number: '1.2-2' }}</td>
                  <td class="px-3 py-2.5 text-right font-bold text-text">{{ r.total_sold | number: '1.0-0' }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      } @else if (!loading()) {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-200 bg-white py-20 shadow-sm">
          <i class="pi pi-box mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-muted">Click Generate Report to view current stock data</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StockReportPageComponent {
  private readonly reportsService = inject(ReportsService);
  private readonly messageService = inject(MessageService);

  loading = signal(false);
  report = signal<StockReport | null>(null);

  generateReport(): void {
    this.loading.set(true);
    this.reportsService.getStockReport().subscribe({
      next: (data) => {
        this.report.set(data);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to generate stock report',
        });
      },
    });
  }

  exportCsv(): void {
    this.reportsService.exportStockCsv().subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'stock_report.csv';
        link.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to export stock CSV',
        });
      },
    });
  }
}
