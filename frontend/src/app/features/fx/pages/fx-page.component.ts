import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { switchMap, of } from 'rxjs';

function fmtChartDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}
import { FormsModule } from '@angular/forms';
import { DecimalPipe, DatePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { UIChart } from 'primeng/chart';
import {
  FxService,
  FxRate,
  FxForecast,
  FXAlertRead,
} from '../../../core/services/fx.service';

@Component({
  selector: 'app-fx-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, DatePipe, Toast, UIChart],
  template: `
    <p-toast />
    <div>
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-text">FX Rates</h2>
          <p class="mt-1 text-sm text-muted">Track and forecast NGN/USD exchange rates</p>
        </div>
        <button
          type="button"
          data-testid="export-fx-csv"
          (click)="exportFxCsv()"
          class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
        >
          <i class="pi pi-download text-xs"></i>
          Export CSV
        </button>
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Current NGN/USD Rate -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-4 flex items-center gap-2">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <i class="pi pi-money-bill text-lg text-primary"></i>
            </div>
          </div>
          <p class="text-sm font-medium text-muted">Current NGN/USD Rate</p>
          @if (latestRate()) {
            <p class="mt-2 text-4xl font-bold text-text">
              &#8358;{{ latestRate()!.rate | number: '1.2-2' }}
            </p>
            <p class="mt-2 text-xs text-muted">
              <i class="pi pi-calendar mr-1 text-[10px]"></i>
              {{ latestRate()!.rate_date | date: 'mediumDate' }}
              <span class="mx-1">&middot;</span>
              {{ latestRate()!.source }}
            </p>
          } @else {
            <div class="mt-2 h-10 w-32 skeleton"></div>
          }
          <!-- EUR/USD sub-card -->
          <div class="mt-4 border-t border-gray-100 pt-3">
            <p class="text-xs font-medium text-muted">EUR/USD Rate</p>
            @if (latestEurUsd()) {
              <p class="mt-1 text-xl font-bold text-secondary">
                {{ latestEurUsd()!.rate | number: '1.4-4' }}
              </p>
            } @else {
              <p class="mt-1 text-sm text-muted">No EUR/USD rate recorded</p>
            }
          </div>
        </div>

        <!-- Manual Entry -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
              <i class="pi pi-plus text-sm text-success"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Add Rate</h3>
          </div>
          <div class="flex flex-wrap items-end gap-3">
            <div>
              <label for="fx-manual-pair" class="mb-1.5 block text-xs font-medium text-muted">Pair</label>
              <select
                id="fx-manual-pair"
                [(ngModel)]="manualPair"
                class="rounded-lg border border-gray-300 py-2.5 pl-3 pr-8 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="USDNGN">USD/NGN</option>
                <option value="EURUSD">EUR/USD</option>
              </select>
            </div>
            <div>
              <label for="fx-manual-rate" class="mb-1.5 block text-xs font-medium text-muted">Rate</label>
              <input
                id="fx-manual-rate"
                type="number"
                [(ngModel)]="manualRate"
                [placeholder]="manualPair === 'EURUSD' ? 'e.g. 1.08' : 'e.g. 1500'"
                step="0.01"
                class="w-36 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label for="fx-manual-date" class="mb-1.5 block text-xs font-medium text-muted">Date</label>
              <input
                id="fx-manual-date"
                type="date"
                [(ngModel)]="manualDate"
                class="w-40 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label for="fx-manual-source" class="mb-1.5 block text-xs font-medium text-muted">Source</label>
              <select
                id="fx-manual-source"
                [(ngModel)]="manualSource"
                class="rounded-lg border border-gray-300 py-2.5 pl-3 pr-8 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="MANUAL">Manual</option>
                <option value="PARALLEL_MARKET">Parallel Market</option>
                <option value="CBN_OFFICIAL">CBN Official</option>
              </select>
            </div>
            <button
              (click)="addRate()"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
            >
              <i class="pi pi-check text-sm"></i> Add
            </button>
          </div>
        </div>
      </div>

      <!-- Historical Chart -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-chart-line text-sm text-secondary"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Historical Rates (90 days)</h3>
          </div>
          <div class="flex items-center gap-2">
            <button
              (click)="loadHistoricalRates()"
              [disabled]="backfilling()"
              title="Pull 90 days of NGN/USD from exchange-api.pages.dev (free)"
              class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:opacity-50"
            >
              <i class="pi text-xs" [class]="backfilling() ? 'pi-spinner pi-spin' : 'pi-cloud-download'"></i>
              {{ backfilling() ? 'Fetching…' : 'Load History' }}
            </button>
            @if (historyRates().length > 0) {
              <button
                (click)="exportHistoryCsv()"
                class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
              >
                <i class="pi pi-download text-xs"></i> Export CSV
              </button>
            }
          </div>
        </div>
        @if (backfilling()) {
          <div class="flex h-[300px] flex-col items-center justify-center gap-3">
            <i class="pi pi-spinner pi-spin text-2xl text-primary"></i>
            <p class="text-sm text-muted">Fetching 90 days of NGN/USD rates from exchange-api.pages.dev…</p>
          </div>
        } @else if (historyChartData()) {
          <p-chart
            type="line"
            [data]="historyChartData()!"
            [options]="chartOptions"
            height="300px"
          />
        } @else {
          <div class="flex h-[300px] flex-col items-center justify-center gap-3">
            <i class="pi pi-chart-line text-2xl text-muted"></i>
            <p class="text-sm text-muted">No rate history yet.</p>
            <button
              (click)="loadHistoricalRates()"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary/90"
            >
              <i class="pi pi-cloud-download text-xs"></i> Load 90-Day History
            </button>
          </div>
        }
      </div>

      <!-- Forecast -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
              <i class="pi pi-sparkles text-sm text-warning"></i>
            </div>
            <h3 class="text-base font-semibold text-text">{{ forecastDays() }}-Day Forecast</h3>
          </div>
          <div class="flex items-center gap-2">
            <button
              (click)="refreshForecast()"
              [disabled]="forecastGenerating()"
              class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:opacity-50"
              title="Regenerate forecast using latest rate data"
            >
              <i class="pi text-xs" [class]="forecastGenerating() ? 'pi-spinner pi-spin' : 'pi-refresh'"></i>
              {{ forecastGenerating() ? 'Generating…' : 'Refresh' }}
            </button>
            <div class="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-0.5">
              @for (range of forecastRangeOptions; track range) {
                <button
                  (click)="setForecastRange(range)"
                  [disabled]="forecastGenerating()"
                  class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40"
                  [class]="forecastDays() === range
                    ? 'bg-white text-primary shadow-sm'
                    : 'text-muted hover:text-text'"
                >
                  {{ range }}d
                </button>
              }
            </div>
          </div>
        </div>
        @if (forecastGenerating()) {
          <div class="flex h-[300px] flex-col items-center justify-center gap-3">
            <i class="pi pi-spinner pi-spin text-2xl text-primary"></i>
            <p class="text-sm text-muted">Training forecast model — this takes about 30 seconds…</p>
          </div>
        } @else if (forecastChartData()) {
          <p-chart
            type="line"
            [data]="forecastChartData()!"
            [options]="chartOptions"
            height="300px"
          />
        } @else {
          <div class="flex h-[300px] flex-col items-center justify-center gap-3">
            <i class="pi pi-chart-line text-2xl text-muted"></i>
            <p class="text-sm text-muted">No forecast data yet.</p>
            <button
              (click)="refreshForecast()"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary/90"
            >
              <i class="pi pi-sparkles text-xs"></i> Generate Forecast
            </button>
          </div>
        }

        <!-- Forecast Table -->
        @if (forecasts().length > 0) {
          <div class="mt-5 overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">FX rate forecast data</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Date
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Base
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Best
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Worst
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (f of forecasts(); track f.date) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 text-muted">{{ f.date | date: 'mediumDate' }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold">
                      {{ f.base | number: '1.2-2' }}
                    </td>
                    <td class="px-3 py-2.5 text-right font-medium text-success">
                      {{ f.best_case | number: '1.2-2' }}
                    </td>
                    <td class="px-3 py-2.5 text-right font-medium text-danger">
                      {{ f.worst_case | number: '1.2-2' }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>

      <!-- Rate Alerts -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50">
            <i class="pi pi-bell text-sm text-danger"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Rate Alerts</h3>
        </div>

        <!-- Create Alert Form -->
        <div class="mb-5 flex flex-wrap items-end gap-3">
          <div>
            <label for="fx-alert-pair" class="mb-1.5 block text-xs font-medium text-muted">Pair</label>
            <select
              id="fx-alert-pair"
              [(ngModel)]="alertPair"
              class="rounded-lg border border-gray-300 py-2.5 pl-3 pr-8 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="USDNGN">USD/NGN</option>
              <option value="EURUSD">EUR/USD</option>
            </select>
          </div>
          <div>
            <label for="fx-alert-direction" class="mb-1.5 block text-xs font-medium text-muted">Direction</label>
            <select
              id="fx-alert-direction"
              [(ngModel)]="alertDirection"
              class="rounded-lg border border-gray-300 py-2.5 pl-3 pr-8 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
          </div>
          <div>
            <label for="fx-alert-threshold" class="mb-1.5 block text-xs font-medium text-muted">Threshold Rate</label>
            <input
              id="fx-alert-threshold"
              type="number"
              [(ngModel)]="alertThreshold"
              placeholder="e.g. 1600"
              step="0.01"
              class="w-40 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            (click)="createAlert()"
            class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
          >
            <i class="pi pi-plus text-sm"></i> Create Alert
          </button>
        </div>

        <!-- Alerts List -->
        @if (alerts().length > 0) {
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">FX rate alerts</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Pair
                  </th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Direction
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Threshold
                  </th>
                  <th class="px-3 py-2.5 text-center text-xs font-semibold uppercase text-muted">
                    Status
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (alert of alerts(); track alert.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 font-medium text-text">{{ alert.pair }}</td>
                    <td class="px-3 py-2.5">
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                        [class]="
                          alert.direction === 'above'
                            ? 'bg-green-100 text-green-700'
                            : 'bg-red-100 text-red-700'
                        "
                      >
                        <i
                          class="pi mr-1 text-[10px]"
                          [class]="
                            alert.direction === 'above' ? 'pi-arrow-up' : 'pi-arrow-down'
                          "
                        ></i>
                        {{ alert.direction }}
                      </span>
                    </td>
                    <td class="px-3 py-2.5 text-right font-semibold">
                      {{ alert.threshold_rate | number: '1.2-2' }}
                    </td>
                    <td class="px-3 py-2.5 text-center">
                      <button
                        (click)="toggleAlert(alert)"
                        class="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors"
                        [class]="
                          alert.is_enabled
                            ? 'bg-green-100 text-green-700 hover:bg-green-200'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        "
                      >
                        <i
                          class="pi text-[10px]"
                          [class]="alert.is_enabled ? 'pi-check-circle' : 'pi-times-circle'"
                        ></i>
                        {{ alert.is_enabled ? 'Enabled' : 'Disabled' }}
                      </button>
                    </td>
                    <td class="px-3 py-2.5 text-right">
                      <button
                        (click)="deleteAlert(alert.id)"
                        class="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-danger"
                        title="Delete alert"
                      >
                        <i class="pi pi-trash text-sm"></i>
                      </button>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-bell-slash mr-1"></i> No alerts configured
          </p>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FxPageComponent implements OnInit {
  private readonly fxService = inject(FxService);
  private readonly messageService = inject(MessageService);

  latestRate = signal<FxRate | null>(null);
  latestEurUsd = signal<FxRate | null>(null);
  historyRates = signal<FxRate[]>([]);
  historyChartData = signal<unknown>(null);
  forecastChartData = signal<unknown>(null);
  forecasts = signal<FxForecast[]>([]);

  alerts = signal<FXAlertRead[]>([]);
  forecastDays = signal(180);
  forecastGenerating = signal(false);
  backfilling = signal(false);
  readonly forecastRangeOptions = [30, 90, 180];

  manualRate = 0;
  manualDate = new Date().toISOString().split('T')[0];
  manualSource = 'PARALLEL_MARKET';
  manualPair = 'USDNGN';

  alertPair = 'USDNGN';
  alertDirection: 'above' | 'below' = 'above';
  alertThreshold = 0;

  readonly chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    scales: {
      x: { ticks: { maxTicksLimit: 12, maxRotation: 0 } },
      y: { beginAtZero: false },
    },
  };

  ngOnInit(): void {
    this.fxService.getLatest().subscribe({ next: (r) => this.latestRate.set(r) });
    this.fxService.getLatestEurUsd().subscribe({ next: (r) => this.latestEurUsd.set(r) });
    this.fxService.getAlerts().subscribe({ next: (a) => this.alerts.set(a) });
    this.fxService.getHistory(90).subscribe({
      next: (rates) => {
        this.historyRates.set(rates);
        this.historyChartData.set({
          labels: rates.map((r) => fmtChartDate(r.rate_date)),
          datasets: [
            {
              label: 'NGN/USD',
              data: rates.map((r) => r.rate),
              borderColor: '#1F4E79',
              backgroundColor: 'rgba(31, 78, 121, 0.05)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
              pointHoverRadius: 5,
            },
          ],
        });
      },
    });
    this.loadForecast(180);
  }

  private buildForecastDatasets(fc: FxForecast[]) {
    return {
      labels: fc.map((f) => fmtChartDate(f.date)),
      datasets: [
        {
          label: 'Worst Case',
          data: fc.map((f) => f.worst_case),
          borderColor: 'rgba(192, 57, 43, 0.5)',
          fill: false,
          borderWidth: 1.5,
          tension: 0.4,
          pointRadius: 0,
        },
        {
          label: 'Best Case',
          data: fc.map((f) => f.best_case),
          borderColor: 'rgba(26, 122, 74, 0.5)',
          backgroundColor: 'rgba(100, 160, 130, 0.1)',
          fill: '-1',
          borderWidth: 1.5,
          tension: 0.4,
          pointRadius: 0,
        },
        {
          label: 'Base',
          data: fc.map((f) => f.base),
          borderColor: '#1F4E79',
          backgroundColor: 'rgba(31, 78, 121, 0)',
          fill: false,
          borderWidth: 2.5,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 6,
        },
      ],
    };
  }

  private loadForecast(days: number): void {
    this.forecastChartData.set(null);
    this.forecasts.set([]);
    this.fxService.getForecast(days).pipe(
      switchMap((fc) => {
        if (fc.length > 0) return of(fc);
        // No stored forecast — generate one now
        this.forecastGenerating.set(true);
        return this.fxService.generateForecast('USDNGN', days).pipe(
          switchMap(() => this.fxService.getForecast(days)),
        );
      }),
    ).subscribe({
      next: (fc) => {
        this.forecastGenerating.set(false);
        this.forecasts.set(fc);
        this.forecastChartData.set(this.buildForecastDatasets(fc));
      },
      error: () => {
        this.forecastGenerating.set(false);
        this.messageService.add({
          severity: 'warn',
          summary: 'Forecast unavailable',
          detail: 'At least 30 days of rate history is needed to generate a forecast. Add more historical rates and try again.',
        });
      },
    });
  }

  setForecastRange(days: number): void {
    this.forecastDays.set(days);
    this.loadForecast(days);
  }

  refreshForecast(): void {
    this.forecastGenerating.set(true);
    this.forecastChartData.set(null);
    this.forecasts.set([]);
    this.fxService.generateForecast('USDNGN', this.forecastDays()).pipe(
      switchMap(() => this.fxService.getForecast(this.forecastDays())),
    ).subscribe({
      next: (fc) => {
        this.forecastGenerating.set(false);
        this.forecasts.set(fc);
        this.forecastChartData.set(this.buildForecastDatasets(fc));
        this.messageService.add({ severity: 'success', summary: 'Forecast updated', detail: 'New forecast generated.' });
      },
      error: () => {
        this.forecastGenerating.set(false);
        this.messageService.add({
          severity: 'warn',
          summary: 'Forecast failed',
          detail: 'At least 30 days of rate history is needed to generate a forecast.',
        });
      },
    });
  }

  loadHistoricalRates(): void {
    this.backfilling.set(true);
    this.fxService.backfillFreeRates('USDNGN', 90).subscribe({
      next: ({ records_inserted }) => {
        this.backfilling.set(false);
        this.messageService.add({
          severity: 'success',
          summary: 'History loaded',
          detail: records_inserted > 0
            ? `${records_inserted} days of NGN/USD rates added. Generating forecast…`
            : 'Rate history is already up to date.',
        });
        // Reload the chart and auto-generate forecast with fresh data
        this.fxService.getHistory(90).subscribe({
          next: (rates) => {
            this.historyRates.set(rates);
            this.historyChartData.set({
              labels: rates.map((r) => fmtChartDate(r.rate_date)),
              datasets: [{
                label: 'NGN/USD',
                data: rates.map((r) => r.rate),
                borderColor: '#1F4E79',
                backgroundColor: 'rgba(31, 78, 121, 0.05)',
                fill: true,
                tension: 0.3,
                pointRadius: 2,
                pointHoverRadius: 5,
              }],
            });
          },
        });
        if (records_inserted > 0) {
          this.refreshForecast();
        }
      },
      error: () => {
        this.backfilling.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Failed',
          detail: 'Could not fetch historical rates. Check your connection and try again.',
        });
      },
    });
  }

  addRate(): void {
    if (!this.manualRate || this.manualRate <= 0) return;
    this.fxService
      .addManualRate({
        rate: this.manualRate,
        rate_date: this.manualDate,
        rate_type: this.manualPair,
        source: this.manualSource,
      })
      .subscribe({
        next: (r) => {
          if (this.manualPair === 'EURUSD') {
            this.latestEurUsd.set(r);
          } else {
            this.latestRate.set(r);
          }
          this.messageService.add({
            severity: 'success',
            summary: 'Added',
            detail: `${this.manualPair} rate recorded`,
          });
          // If no forecast exists yet, try generating one now that we have fresh data
          if (this.forecasts().length === 0 && this.manualPair === 'USDNGN') {
            this.loadForecast(this.forecastDays());
          }
        },
        error: () => {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to add rate',
          });
        },
      });
  }

  createAlert(): void {
    if (!this.alertThreshold || this.alertThreshold <= 0) return;
    this.fxService
      .createAlert({
        pair: this.alertPair,
        direction: this.alertDirection,
        threshold_rate: this.alertThreshold,
      })
      .subscribe({
        next: (alert) => {
          this.alerts.update((list) => [...list, alert]);
          this.alertThreshold = 0;
          this.messageService.add({
            severity: 'success',
            summary: 'Alert Created',
            detail: `Alert for ${alert.pair} ${alert.direction} ${alert.threshold_rate}`,
          });
        },
        error: () => {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to create alert',
          });
        },
      });
  }

  toggleAlert(alert: FXAlertRead): void {
    this.fxService
      .updateAlert(alert.id, { is_enabled: !alert.is_enabled })
      .subscribe({
        next: (updated) => {
          this.alerts.update((list) =>
            list.map((a) => (a.id === updated.id ? updated : a)),
          );
        },
        error: () => {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to update alert',
          });
        },
      });
  }

  exportHistoryCsv(): void {
    const rates = this.historyRates();
    if (rates.length === 0) return;
    const header = 'Date,Rate,Source';
    const lines = rates.map(
      (r) => `${r.rate_date},${r.rate},${r.source}`,
    );
    const csv = [header, ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'fx_rates_history.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  exportFxCsv(): void {
    this.fxService.exportCsv().subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'fx_rates_export.csv';
        link.click();
        URL.revokeObjectURL(url);
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to export FX rates CSV',
        });
      },
    });
  }

  deleteAlert(id: string): void {
    this.fxService.deleteAlert(id).subscribe({
      next: () => {
        this.alerts.update((list) => list.filter((a) => a.id !== id));
        this.messageService.add({
          severity: 'info',
          summary: 'Deleted',
          detail: 'Alert removed',
        });
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to delete alert',
        });
      },
    });
  }
}
