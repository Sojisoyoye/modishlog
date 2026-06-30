import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ReportsService, StockReport } from '../../../core/services/reports.service';

@Component({
  selector: 'app-stock-report-page',
  standalone: true,
  imports: [DecimalPipe, Toast, RouterLink],
  providers: [MessageService],
  template: `
    <p-toast />
    <div>
      <div class="mb-4 flex items-center gap-2 text-sm">
        <a routerLink="/reports" class="flex min-h-[44px] items-center gap-1.5 font-medium text-gray-500 transition-colors hover:text-gray-900">
          <i class="pi pi-arrow-left text-xs"></i> Reports
        </a>
        <span class="text-gray-400">/</span>
        <span class="font-semibold text-gray-900">Stock Report</span>
      </div>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <div class="mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-700">
            <i class="pi pi-box text-lg"></i>
          </div>
          <h2 class="text-2xl font-bold text-gray-900">Stock Report</h2>
          <p class="mt-1 text-sm text-gray-500">Current inventory valuation and potential profit</p>
        </div>
        <div class="flex items-center gap-3">
          @if (report()) {
            <button
              type="button"
              (click)="exportCsv()"
              class="flex min-h-[44px] items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
            >
              <i class="pi pi-download text-sm"></i> Export CSV
            </button>
          }
          <button
            type="button"
            (click)="generateReport()"
            [disabled]="loading()"
            class="flex min-h-[44px] items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:opacity-50"
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
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-gray-500">Total Stock Value</p>
            <p class="mt-1 text-2xl font-bold text-gray-900">{{ r.total_stock_value | number: '1.2-2' }}</p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-gray-500">Total Potential Profit</p>
            <p class="mt-1 text-2xl font-bold text-emerald-700">{{ r.total_potential_profit | number: '1.2-2' }}</p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-gray-500">Total Units Sold</p>
            <p class="mt-1 text-2xl font-bold text-gray-900">{{ r.total_sold | number: '1.0-0' }}</p>
          </div>
        </div>

        <!-- Table -->
        <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Stock report items</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-gray-500">SKU</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-gray-500">Product</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-gray-500">Category</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-gray-500">Unit Cost</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-gray-500">Qty</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-gray-500">Stock Value</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-gray-500">Potential Profit</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-gray-500">Total Sold</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (item of r.items; track item.product_id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 font-mono text-xs text-gray-500">{{ item.sku }}</td>
                    <td class="px-3 py-2.5 font-medium text-gray-900">{{ item.product_name }}</td>
                    <td class="px-3 py-2.5 text-gray-500">{{ item.category ?? '—' }}</td>
                    <td class="px-3 py-2.5 text-right text-gray-700">{{ item.unit_cost | number: '1.2-2' }}</td>
                    <td
                      class="px-3 py-2.5 text-right font-semibold"
                      [class.text-emerald-700]="item.quantity_on_hand > 10"
                      [class.text-amber-600]="item.quantity_on_hand > 0 && item.quantity_on_hand <= 10"
                      [class.text-red-600]="item.quantity_on_hand === 0"
                    >{{ item.quantity_on_hand | number: '1.0-0' }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold text-gray-900">{{ item.stock_value | number: '1.2-2' }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold text-emerald-700">{{ item.potential_profit | number: '1.2-2' }}</td>
                    <td class="px-3 py-2.5 text-right text-gray-700">{{ item.total_sold | number: '1.0-0' }}</td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="8" class="px-3 py-10 text-center text-gray-500">
                      <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                      No stock data available
                    </td>
                  </tr>
                }
              </tbody>
              <!-- Footer totals -->
              <tfoot>
                <tr class="border-t-2 border-gray-200 bg-gray-50 font-semibold">
                  <td colspan="5" class="px-3 py-2.5 text-xs font-bold uppercase text-gray-500">Totals</td>
                  <td class="px-3 py-2.5 text-right font-bold text-gray-900">{{ r.total_stock_value | number: '1.2-2' }}</td>
                  <td class="px-3 py-2.5 text-right font-bold text-emerald-700">{{ r.total_potential_profit | number: '1.2-2' }}</td>
                  <td class="px-3 py-2.5 text-right font-bold text-gray-900">{{ r.total_sold | number: '1.0-0' }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      } @else if (!loading()) {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-100 bg-white py-20 shadow-sm">
          <i class="pi pi-box mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-gray-500">Click Generate Report to view current stock data</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StockReportPageComponent implements OnInit {
  private readonly reportsService = inject(ReportsService);
  private readonly messageService = inject(MessageService);

  loading = signal(false);
  report = signal<StockReport | null>(null);

  ngOnInit(): void {
    this.generateReport();
  }

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
