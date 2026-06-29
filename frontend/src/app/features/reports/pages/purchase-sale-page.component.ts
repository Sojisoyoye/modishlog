import { Component, ChangeDetectionStrategy, inject, signal, OnInit, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { catchError, of } from 'rxjs';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ReportsService, PurchaseSaleReport } from '../../../core/services/reports.service';
import { SettingsService } from '../../../core/services/settings.service';
import { computeDefaultDateRange } from '../../../core/utils/fiscal-year.utils';

interface SummaryCard {
  label: string;
  value: number;
  highlight?: 'positive' | 'negative' | 'neutral';
}

@Component({
  selector: 'app-purchase-sale-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, Toast],
  providers: [MessageService],
  template: `
    <p-toast />
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Purchase & Sale Report</h2>
        <p class="mt-1 text-sm text-muted">Summary of purchases and sales over a period</p>
      </div>

      <!-- Date Filters -->
      <div class="mb-6 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <h3 class="mb-4 text-sm font-semibold text-text">Date Range</h3>
        <div class="flex flex-wrap items-end gap-4">
          <div class="flex flex-col gap-1">
            <label for="ps-start-date" class="text-xs font-medium text-muted">Start Date</label>
            <input
              id="ps-start-date"
              type="date"
              [(ngModel)]="startDate"
              class="rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label for="ps-end-date" class="text-xs font-medium text-muted">End Date</label>
            <input
              id="ps-end-date"
              type="date"
              [(ngModel)]="endDate"
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
        <!-- Net Position - prominent -->
        <div
          class="mb-4 rounded-xl border p-6 shadow-sm"
          [class.border-green-200]="r.net_position >= 0"
          [class.bg-green-50]="r.net_position >= 0"
          [class.border-red-200]="r.net_position < 0"
          [class.bg-red-50]="r.net_position < 0"
        >
          <p class="text-sm font-medium text-muted">Net Position</p>
          <p
            class="mt-1 text-4xl font-bold"
            [class.text-green-700]="r.net_position >= 0"
            [class.text-red-700]="r.net_position < 0"
          >
            {{ r.net_position | number: '1.2-2' }}
          </p>
        </div>

        <!-- Summary cards -->
        <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
          @for (card of buildCards(r); track card.label) {
            <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <p class="text-xs font-medium text-muted">{{ card.label }}</p>
              <p
                class="mt-1 text-xl font-bold"
                [class.text-green-600]="card.highlight === 'positive'"
                [class.text-red-600]="card.highlight === 'negative'"
                [class.text-text]="!card.highlight || card.highlight === 'neutral'"
              >
                {{ card.value | number: '1.2-2' }}
              </p>
            </div>
          }
        </div>
      } @else if (!loading()) {
        <div class="flex flex-col items-center justify-center rounded-xl border border-gray-200 bg-white py-20 shadow-sm">
          <i class="pi pi-arrows-h mb-4 text-4xl text-gray-300"></i>
          <p class="text-base font-medium text-muted">Select a date range and click Generate Report</p>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PurchaseSalePageComponent implements OnInit {
  private readonly reportsService = inject(ReportsService);
  private readonly settingsService = inject(SettingsService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  startDate = '';
  endDate = '';
  loading = signal(false);
  report = signal<PurchaseSaleReport | null>(null);

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

  buildCards(r: PurchaseSaleReport): SummaryCard[] {
    return [
      { label: 'Total Purchases', value: r.total_purchase, highlight: 'neutral' },
      { label: 'Purchase Returns', value: r.total_purchase_returns, highlight: 'neutral' },
      { label: 'Total Sales', value: r.total_sales, highlight: 'positive' },
      { label: 'Sales Returns', value: r.total_sales_returns, highlight: 'neutral' },
    ];
  }

  generateReport(): void {
    this.loading.set(true);
    this.reportsService
      .getPurchaseSaleReport(this.startDate || undefined, this.endDate || undefined)
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
            detail: 'Failed to generate Purchase & Sale report',
          });
        },
      });
  }
}
