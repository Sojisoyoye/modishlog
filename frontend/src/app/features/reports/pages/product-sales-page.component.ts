import { Component, ChangeDetectionStrategy, inject, signal, OnInit, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ReportsService, ProductSalesReport, ProductSalesRow } from '../../../core/services/reports.service';
import { SettingsService } from '../../../core/services/settings.service';
import { computeDefaultDateRange } from '../../../core/utils/fiscal-year.utils';
import { DATE_PRESETS, DatePreset } from '../../../core/utils/date-presets.utils';

@Component({
  selector: 'app-product-sales-page',
  standalone: true,
  imports: [FormsModule, ReactiveFormsModule, DecimalPipe, Toast, RouterLink],
  providers: [MessageService],
  template: `
    <p-toast />
    <div>
      <div class="mb-4 flex items-center gap-2 text-sm">
        <a routerLink="/reports" class="flex min-h-[44px] items-center gap-1.5 font-medium text-gray-500 transition-colors hover:text-gray-900">
          <i class="pi pi-arrow-left text-xs"></i> Reports
        </a>
        <span class="text-gray-400">/</span>
        <span class="font-semibold text-gray-900">Product Sales</span>
      </div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-gray-900">Product Sales Report</h2>
        <p class="mt-1 text-sm text-gray-500">Sales breakdown by product for a given period</p>
      </div>

      <!-- Filters -->
      <div class="mb-6 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <h3 class="mb-3 text-sm font-semibold text-gray-900">Date Range</h3>
        <div class="mb-4 flex flex-wrap gap-2">
          @for (preset of presets; track preset.key) {
            <button
              type="button"
              (click)="applyPreset(preset)"
              class="rounded-full border px-3 py-1 text-xs font-medium transition-colors"
              [class]="activePreset === preset.key
                ? 'border-emerald-600 bg-emerald-600 text-white'
                : 'border-gray-300 bg-white text-gray-500 hover:border-emerald-500 hover:text-emerald-600'"
            >{{ preset.label }}</button>
          }
        </div>
        <div class="flex flex-wrap items-end gap-4">
          <div class="flex flex-col gap-1">
            <label for="ps-start-date" class="text-xs font-medium text-gray-500">From</label>
            <input
              id="ps-start-date"
              type="date"
              [(ngModel)]="startDate"
              (ngModelChange)="activePreset = null"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label for="ps-end-date" class="text-xs font-medium text-gray-500">To</label>
            <input
              id="ps-end-date"
              type="date"
              [(ngModel)]="endDate"
              (ngModelChange)="activePreset = null"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <button
            type="button"
            (click)="loadReport()"
            [disabled]="loading()"
            class="flex min-h-[44px] items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50"
          >
            @if (loading()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Loading...
            } @else {
              <i class="pi pi-play text-sm"></i> Generate Report
            }
          </button>
        </div>
      </div>

      <!-- Summary -->
      @if (report(); as r) {
        <div class="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <p class="text-xs font-medium text-gray-500">Total Products</p>
            <p class="mt-1 text-2xl font-bold text-gray-900">{{ r.total }}</p>
          </div>
          <div class="rounded-xl border border-emerald-100 bg-emerald-50 p-5 shadow-sm">
            <p class="text-xs font-medium text-gray-500">Total Revenue</p>
            <p class="mt-1 text-2xl font-bold text-emerald-700">{{ r.total_revenue | number: '1.2-2' }}</p>
          </div>
        </div>

        <!-- Table -->
        <div class="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-100">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">SKU</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Product</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Category</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Qty Sold</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Returns</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Net Qty</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Revenue</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Avg Price</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-50">
                @if (r.rows.length === 0) {
                  <tr>
                    <td colspan="8" class="px-4 py-12 text-center text-sm text-gray-400">No sales data for this period</td>
                  </tr>
                }
                @for (row of r.rows; track row.product_id) {
                  <tr class="hover:bg-gray-50 transition-colors">
                    <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ row.sku }}</td>
                    <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ row.product_name }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ row.category ?? '—' }}</td>
                    <td class="px-4 py-3 text-right text-sm text-gray-900">{{ row.quantity_sold }}</td>
                    <td class="px-4 py-3 text-right text-sm" [class.text-red-600]="row.return_quantity > 0" [class.text-gray-400]="row.return_quantity === 0">
                      {{ row.return_quantity > 0 ? row.return_quantity : '—' }}
                    </td>
                    <td class="px-4 py-3 text-right text-sm font-semibold text-gray-900">{{ row.net_quantity }}</td>
                    <td class="px-4 py-3 text-right text-sm font-semibold text-emerald-700">{{ row.total_revenue | number: '1.2-2' }}</td>
                    <td class="px-4 py-3 text-right text-sm text-gray-500">{{ row.avg_unit_price | number: '1.2-2' }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          @if (r.total > r.page_size) {
            <div class="flex items-center justify-between border-t border-gray-100 px-4 py-3">
              <p class="text-xs text-gray-500">
                Page {{ r.page }} of {{ Math.ceil(r.total / r.page_size) }} ({{ r.total }} products)
              </p>
              <div class="flex gap-2">
                <button
                  type="button"
                  (click)="changePage(currentPage() - 1)"
                  [disabled]="currentPage() <= 1"
                  class="rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-40"
                >Prev</button>
                <button
                  type="button"
                  (click)="changePage(currentPage() + 1)"
                  [disabled]="currentPage() >= Math.ceil(r.total / r.page_size)"
                  class="rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-40"
                >Next</button>
              </div>
            </div>
          }
        </div>
      } @else if (!loading()) {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-100 bg-white py-20 shadow-sm">
          <i class="pi pi-table mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-gray-500">Select a date range and click Generate Report</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductSalesPageComponent implements OnInit {
  private readonly reportsService = inject(ReportsService);
  private readonly settingsService = inject(SettingsService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  readonly Math = Math;

  startDate = '';
  endDate = '';
  loading = signal(false);
  report = signal<ProductSalesReport | null>(null);
  currentPage = signal(1);
  readonly presets: DatePreset[] = DATE_PRESETS;
  activePreset: string | null = null;

  ngOnInit(): void {
    this.settingsService
      .getFiscalYearStart()
      .pipe(
        catchError(() => of({ fiscal_year_start_month: null, fiscal_year_start_day: null })),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((fy) => {
        const { start, end } = computeDefaultDateRange(
          fy.fiscal_year_start_month,
          fy.fiscal_year_start_day,
        );
        this.startDate = start;
        this.endDate = end;
        this.loadReport();
      });
  }

  applyPreset(preset: DatePreset): void {
    const { start, end } = preset.range();
    this.startDate = start;
    this.endDate = end;
    this.activePreset = preset.key;
    this.currentPage.set(1);
    this.loadReport();
  }

  loadReport(): void {
    this.loading.set(true);
    this.reportsService
      .getProductSalesReport({
        startDate: this.startDate || undefined,
        endDate: this.endDate || undefined,
        page: this.currentPage(),
        pageSize: 20,
      })
      .subscribe({
        next: (data) => {
          this.report.set(data);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to load product sales report',
          });
        },
      });
  }

  changePage(page: number): void {
    this.currentPage.set(page);
    this.loadReport();
  }
}
