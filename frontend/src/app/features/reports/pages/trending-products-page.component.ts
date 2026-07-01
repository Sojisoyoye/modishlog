import { Component, ChangeDetectionStrategy, inject, signal, OnInit, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ReportsService, TrendingProductsReport } from '../../../core/services/reports.service';
import { SettingsService } from '../../../core/services/settings.service';
import { computeDefaultDateRange } from '../../../core/utils/fiscal-year.utils';
import { DATE_PRESETS, DatePreset } from '../../../core/utils/date-presets.utils';

@Component({
  selector: 'app-trending-products-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, Toast, RouterLink],
  providers: [MessageService],
  template: `
    <p-toast />
    <div>
      <div class="mb-4 flex items-center gap-2 text-sm">
        <a routerLink="/reports" class="flex min-h-[44px] items-center gap-1.5 font-medium text-gray-500 transition-colors hover:text-gray-900">
          <i class="pi pi-arrow-left text-xs"></i> Reports
        </a>
        <span class="text-gray-400">/</span>
        <span class="font-semibold text-gray-900">Trending Products</span>
      </div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-gray-900">Trending Products</h2>
        <p class="mt-1 text-sm text-gray-500">Top-selling products ranked by revenue or quantity</p>
      </div>

      <!-- Filters -->
      <div class="mb-6 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <h3 class="mb-3 text-sm font-semibold text-gray-900">Filters</h3>
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
            <label for="tp-start-date" class="text-xs font-medium text-gray-500">From</label>
            <input
              id="tp-start-date"
              type="date"
              [(ngModel)]="startDate"
              (ngModelChange)="activePreset = null"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label for="tp-end-date" class="text-xs font-medium text-gray-500">To</label>
            <input
              id="tp-end-date"
              type="date"
              [(ngModel)]="endDate"
              (ngModelChange)="activePreset = null"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label for="tp-sort-by" class="text-xs font-medium text-gray-500">Sort By</label>
            <select
              id="tp-sort-by"
              [(ngModel)]="sortBy"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            >
              <option value="revenue">Revenue</option>
              <option value="quantity">Quantity</option>
            </select>
          </div>
          <div class="flex flex-col gap-1">
            <label for="tp-limit" class="text-xs font-medium text-gray-500">Top N</label>
            <select
              id="tp-limit"
              [(ngModel)]="limit"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            >
              <option [ngValue]="5">Top 5</option>
              <option [ngValue]="10">Top 10</option>
              <option [ngValue]="20">Top 20</option>
            </select>
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

      <!-- Results -->
      @if (report(); as r) {
        @if (r.rows.length === 0) {
          <div class="flex flex-col items-center justify-center rounded-xl border border-gray-100 bg-white py-20 shadow-sm">
            <i class="pi pi-chart-bar mb-4 text-4xl text-gray-300"></i>
            <p class="text-base font-medium text-gray-500">No sales data for this period</p>
          </div>
        } @else {
          <div class="overflow-hidden rounded-xl border border-gray-100 bg-white shadow-sm">
            <div class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-100">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Rank</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">SKU</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Product</th>
                    <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Category</th>
                    <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Qty Sold</th>
                    <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Revenue</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  @for (row of r.rows; track row.product_id) {
                    <tr class="hover:bg-gray-50 transition-colors">
                      <td class="px-4 py-3">
                        <span
                          class="inline-flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold"
                          [class]="row.rank <= 3 ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'"
                        >{{ row.rank }}</span>
                      </td>
                      <td class="px-4 py-3 text-sm font-mono text-gray-600">{{ row.sku }}</td>
                      <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ row.product_name }}</td>
                      <td class="px-4 py-3 text-sm text-gray-500">{{ row.category ?? '—' }}</td>
                      <td class="px-4 py-3 text-right text-sm text-gray-900">{{ row.quantity_sold }}</td>
                      <td class="px-4 py-3 text-right text-sm font-semibold text-emerald-700">{{ row.total_revenue | number: '1.2-2' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        }
      } @else if (!loading()) {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-100 bg-white py-20 shadow-sm">
          <i class="pi pi-chart-bar mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-gray-500">Select a date range and click Generate Report</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TrendingProductsPageComponent implements OnInit {
  private readonly reportsService = inject(ReportsService);
  private readonly settingsService = inject(SettingsService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  startDate = '';
  endDate = '';
  sortBy = 'revenue';
  limit = 10;
  loading = signal(false);
  report = signal<TrendingProductsReport | null>(null);
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
    this.loadReport();
  }

  loadReport(): void {
    this.loading.set(true);
    this.reportsService
      .getTrendingProducts({
        startDate: this.startDate || undefined,
        endDate: this.endDate || undefined,
        limit: this.limit,
        sortBy: this.sortBy,
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
            detail: 'Failed to load trending products',
          });
        },
      });
  }
}
