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
        <a routerLink="/reports" class="flex items-center gap-1.5 font-medium text-muted transition-colors hover:text-text">
          <i class="pi pi-arrow-left text-xs"></i> Reports
        </a>
        <span class="text-muted">/</span>
        <span class="font-semibold text-text">Profit & Loss</span>
      </div>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-text">Profit & Loss Report</h2>
          <p class="mt-1 text-sm text-muted">Revenue, costs, and net profit over a period</p>
        </div>
        @if (report()) {
          <button
            type="button"
            (click)="printReport()"
            class="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
          >
            <i class="pi pi-print text-sm"></i> Print
          </button>
        }
      </div>

      <!-- Date Filters -->
      <div class="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 class="mb-3 text-sm font-semibold text-text">Date Range</h3>
        <!-- Quick presets -->
        <div class="mb-4 flex flex-wrap gap-2">
          @for (preset of presets; track preset.key) {
            <button
              type="button"
              (click)="applyPreset(preset)"
              class="rounded-full border px-3 py-1 text-xs font-medium transition-colors"
              [class]="activePreset === preset.key
                ? 'border-primary bg-primary text-white'
                : 'border-gray-300 bg-white text-muted hover:border-primary hover:text-primary'"
            >{{ preset.label }}</button>
          }
        </div>
        <div class="flex flex-wrap items-end gap-4">
          <div class="flex flex-col gap-1">
            <label for="pl-start-date" class="text-xs font-medium text-muted">From</label>
            <input
              id="pl-start-date"
              type="date"
              [(ngModel)]="startDate"
              (ngModelChange)="activePreset = null"
              class="rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label for="pl-end-date" class="text-xs font-medium text-muted">To</label>
            <input
              id="pl-end-date"
              type="date"
              [(ngModel)]="endDate"
              (ngModelChange)="activePreset = null"
              class="rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
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

      <!-- Results -->
      @if (report(); as r) {
        <div class="space-y-4">
          <!-- Net Profit - prominent display -->
          <div
            class="rounded-xl border p-6 shadow-sm"
            [class.border-green-200]="r.net_profit >= 0"
            [class.bg-green-50]="r.net_profit >= 0"
            [class.border-red-200]="r.net_profit < 0"
            [class.bg-red-50]="r.net_profit < 0"
          >
            <p class="text-sm font-medium text-muted">Net Profit</p>
            <p
              class="mt-1 text-4xl font-bold"
              [class.text-green-700]="r.net_profit >= 0"
              [class.text-red-700]="r.net_profit < 0"
            >
              {{ r.net_profit | number: '1.2-2' }}
            </p>
          </div>

          <!-- Summary cards grid -->
          <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
            @for (card of summaryCards; track card.key) {
              <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p class="text-xs font-medium text-muted">{{ card.label }}</p>
                <p
                  class="mt-1 text-xl font-bold"
                  [class.text-green-600]="card.highlight === 'profit' && r[card.key] >= 0"
                  [class.text-red-600]="card.highlight === 'profit' && r[card.key] < 0"
                  [class.text-text]="!card.highlight || card.highlight === 'neutral'"
                >
                  {{ r[card.key] | number: '1.2-2' }}
                </p>
              </div>
            }
          </div>
        </div>
      } @else if (!loading()) {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-200 bg-white py-20 shadow-sm">
          <i class="pi pi-chart-line mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-muted">Select a date range and click Generate Report</p>
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
