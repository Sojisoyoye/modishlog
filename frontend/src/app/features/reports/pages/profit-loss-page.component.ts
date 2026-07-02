import { Component, ChangeDetectionStrategy, inject, signal, OnInit, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { catchError, of } from 'rxjs';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ReportsService, ProfitLossReport } from '../../../core/services/reports.service';
import { SettingsService } from '../../../core/services/settings.service';
import { computeDefaultDateRange } from '../../../core/utils/fiscal-year.utils';
import { DATE_PRESETS, DatePreset } from '../../../core/utils/date-presets.utils';

interface SummaryCard {
  label: string;
  key: keyof ProfitLossReport;
  highlight?: 'profit' | 'neutral';
}

@Component({
  selector: 'app-profit-loss-page',
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
        <span class="font-semibold text-gray-900">Profit & Loss</span>
      </div>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-gray-900">Profit & Loss Report</h2>
          <p class="mt-1 text-sm text-gray-500">Revenue, costs, and net profit over a period</p>
        </div>
        @if (report()) {
          <button
            type="button"
            (click)="printReport()"
            class="flex min-h-[44px] items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-50 hover:text-gray-900"
          >
            <i class="pi pi-print text-sm"></i> Print
          </button>
        }
      </div>

      <!-- Date Filters -->
      <div class="mb-6 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
        <h3 class="mb-3 text-sm font-semibold text-gray-900">Date Range</h3>
        <!-- Quick presets -->
        <div class="mb-4 flex flex-wrap gap-2">
          @for (preset of presets; track preset.key) {
            <button
              type="button"
              (click)="applyPreset(preset)"
              class="min-h-[44px] rounded-full border px-3 py-2 text-xs font-medium transition-colors"
              [class]="activePreset === preset.key
                ? 'border-emerald-600 bg-emerald-600 text-white'
                : 'border-gray-300 bg-white text-gray-500 hover:border-emerald-500 hover:text-emerald-600'"
            >{{ preset.label }}</button>
          }
        </div>
        <div class="flex flex-wrap items-end gap-4">
          <div class="flex flex-col gap-1">
            <label for="pl-start-date" class="text-xs font-medium text-gray-500">From</label>
            <input
              id="pl-start-date"
              type="date"
              [(ngModel)]="startDate"
              (ngModelChange)="activePreset = null"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label for="pl-end-date" class="text-xs font-medium text-gray-500">To</label>
            <input
              id="pl-end-date"
              type="date"
              [(ngModel)]="endDate"
              (ngModelChange)="activePreset = null"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
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

      <!-- Results -->
      @if (loading()) {
        <div class="space-y-3 p-4">
          @for (i of [1,2,3,4,5,6,7,8]; track i) {
            <div class="animate-pulse flex gap-4">
              <div class="h-4 bg-gray-200 rounded w-32"></div>
              <div class="h-4 bg-gray-200 rounded flex-1"></div>
              <div class="h-4 bg-gray-200 rounded w-24"></div>
              <div class="h-4 bg-gray-200 rounded w-20"></div>
            </div>
          }
        </div>
      } @else if (report(); as r) {
        <div class="space-y-4">
          <!-- Net Profit - prominent display -->
          <div
            class="rounded-xl border p-6 shadow-sm"
            [class.border-emerald-200]="r.net_profit >= 0"
            [class.bg-emerald-50]="r.net_profit >= 0"
            [class.border-red-200]="r.net_profit < 0"
            [class.bg-red-50]="r.net_profit < 0"
          >
            <p class="text-sm font-medium text-gray-500">Net Profit</p>
            <p
              class="mt-1 text-4xl font-bold"
              [class.text-emerald-700]="r.net_profit >= 0"
              [class.text-red-700]="r.net_profit < 0"
            >
              {{ r.net_profit | number: '1.2-2' }}
            </p>
          </div>

          <!-- Summary cards grid -->
          <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
            @for (card of summaryCards; track card.key) {
              <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
                <p class="text-xs font-medium text-gray-500">{{ card.label }}</p>
                <p
                  class="mt-1 text-xl font-bold"
                  [class.text-emerald-700]="card.highlight === 'profit' && r[card.key] >= 0"
                  [class.text-red-600]="card.highlight === 'profit' && r[card.key] < 0"
                  [class.text-gray-900]="!card.highlight || card.highlight === 'neutral'"
                >
                  {{ r[card.key] | number: '1.2-2' }}
                </p>
              </div>
            }
          </div>
        </div>
      } @else {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-100 bg-white py-20 shadow-sm">
          <i class="pi pi-chart-line mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-gray-500">Select a date range and click Generate Report</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfitLossPageComponent implements OnInit {
  private readonly reportsService = inject(ReportsService);
  private readonly settingsService = inject(SettingsService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  startDate = '';
  endDate = '';
  loading = signal(false);
  report = signal<ProfitLossReport | null>(null);
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
        this.generateReport();
      });
  }

  readonly summaryCards: SummaryCard[] = [
    { label: 'Total Purchases', key: 'total_purchase_excl_tax' },
    { label: 'Purchase Returns', key: 'purchase_returns_total' },
    { label: 'Total Sales', key: 'total_sales' },
    { label: 'Sales Returns', key: 'total_sales_returns' },
    { label: 'Gross Profit', key: 'gross_profit', highlight: 'profit' },
    { label: 'Operating Costs', key: 'total_operating_costs' },
    { label: 'Opening Stock Value', key: 'opening_stock_value' },
    { label: 'Closing Stock Value', key: 'closing_stock_value' },
    { label: 'Purchase Due', key: 'purchase_due' },
    { label: 'Sales Due', key: 'sales_due' },
  ];

  applyPreset(preset: DatePreset): void {
    const { start, end } = preset.range();
    this.startDate = start;
    this.endDate = end;
    this.activePreset = preset.key;
    this.generateReport();
  }

  generateReport(): void {
    this.loading.set(true);
    this.reportsService
      .getProfitLoss(this.startDate || undefined, this.endDate || undefined)
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
            detail: 'Failed to generate Profit & Loss report',
          });
        },
      });
  }

  printReport(): void {
    window.print();
  }
}
