import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { switchMap, of, forkJoin, catchError } from 'rxjs';

function fmtChartDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

const SOURCE_LABELS: Record<string, string> = {
  api_provider: 'Exchange API',
  manual: 'Manual',
  parallel_market: 'Parallel Market',
  cbn_official: 'CBN Official',
};
function fmtSource(s: string): string {
  return SOURCE_LABELS[s?.toLowerCase()] ?? s;
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

type ForecastPair = 'USDNGN' | 'EURNGN';

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
          <p class="mt-1 text-sm text-muted">Track and forecast NGN exchange rates</p>
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

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <!-- USD/NGN Rate Card -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
              <i class="pi pi-dollar text-base text-primary"></i>
            </div>
            <p class="text-sm font-semibold text-muted">USD / NGN</p>
          </div>
          @if (latestRate()) {
            <p class="text-3xl font-bold text-text">
              &#8358;{{ latestRate()!.rate | number: '1.2-2' }}
            </p>
            <p class="mt-1.5 text-xs text-muted">
              <i class="pi pi-calendar mr-1 text-[10px]"></i>
              {{ latestRate()!.rate_date | date: 'mediumDate' }}
              <span class="mx-1">&middot;</span>{{ fmtSource(latestRate()!.source) }}
            </p>
          } @else {
            <div class="mt-2 h-9 w-28 skeleton rounded"></div>
          }
        </div>

        <!-- EUR/NGN Rate Card -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-3 flex items-center gap-2">
            <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-secondary/10">
              <i class="pi pi-euro text-base text-secondary"></i>
            </div>
            <p class="text-sm font-semibold text-muted">EUR / NGN</p>
          </div>
          @if (latestEurNgn()) {
            <p class="text-3xl font-bold text-text">
              &#8358;{{ latestEurNgn()!.rate | number: '1.2-2' }}
            </p>
            <p class="mt-1.5 text-xs text-muted">
              <i class="pi pi-calendar mr-1 text-[10px]"></i>
              {{ latestEurNgn()!.rate_date | date: 'mediumDate' }}
              <span class="mx-1">&middot;</span>{{ fmtSource(latestEurNgn()!.source) }}
            </p>
          } @else if (latestRate() && latestEurUsd()) {
            <p class="text-3xl font-bold text-text">
              &#8358;{{ latestRate()!.rate * latestEurUsd()!.rate | number: '1.2-2' }}
            </p>
            <p class="mt-1.5 text-xs text-muted">Derived from USD/NGN × EUR/USD</p>
          } @else {
            <div class="mt-2 h-9 w-28 skeleton rounded"></div>
            <p class="mt-1.5 text-xs text-muted">Load history to populate</p>
          }
        </div>

        <!-- Manual Entry -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-4 flex items-center gap-2">
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
                <option value="EURNGN">EUR/NGN</option>
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
              title="Pull 90 days of rates from exchange-api.pages.dev (free)"
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
            <p class="text-sm text-muted">Fetching 90 days of NGN rates…</p>
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
            <h3 class="text-base font-semibold text-text">
              {{ forecastDays() }}-Day Forecast
              <span class="ml-1.5 text-xs font-normal text-muted">({{ forecastPair() === 'USDNGN' ? 'USD/NGN' : 'EUR/NGN' }})</span>
            </h3>
          </div>
          <div class="flex items-center gap-2">
            <!-- Pair toggle -->
            <div class="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-0.5">
              <button
                (click)="switchForecastPair('USDNGN')"
                [disabled]="forecastGenerating()"
                class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40"
                [class]="forecastPair() === 'USDNGN' ? 'bg-white text-primary shadow-sm' : 'text-muted hover:text-text'"
              >USD/NGN</button>
              <button
                (click)="switchForecastPair('EURNGN')"
                [disabled]="forecastGenerating()"
                class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40"
                [class]="forecastPair() === 'EURNGN' ? 'bg-white text-secondary shadow-sm' : 'text-muted hover:text-text'"
              >EUR/NGN</button>
            </div>
            <button
              (click)="refreshForecast()"
              [disabled]="forecastGenerating()"
              class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:opacity-50"
              title="Regenerate forecast using latest rate data"
            >
              <i class="pi text-xs" [class]="forecastGenerating() ? 'pi-spinner pi-spin' : 'pi-refresh'"></i>
              {{ forecastGenerating() ? 'Generating…' : 'Refresh' }}
            </button>
            <!-- Day range toggle -->
            <div class="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-0.5">
              @for (range of forecastRangeOptions; track range) {
                <button
                  (click)="setForecastRange(range)"
                  [disabled]="forecastGenerating()"
                  class="rounded-md px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40"
                  [class]="forecastDays() === range ? 'bg-white text-primary shadow-sm' : 'text-muted hover:text-text'"
                >{{ range }}d</button>
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

        <!-- Forecast Insight Panel -->
        @if (forecastInsight(); as insight) {
          <div class="mt-5 rounded-xl border border-gray-200 bg-gray-50 p-5">
            <div class="flex items-start gap-3">
              <div class="mt-0.5 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-white shadow-sm">
                <i class="pi text-base" [class]="insight.trendIcon + ' ' + insight.trendColor"></i>
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-semibold text-text">{{ insight.headline }}</p>
                <p class="mt-1 text-xs leading-relaxed text-muted">{{ insight.summary }}</p>

                <!-- Milestone row -->
                <div class="mt-3 grid grid-cols-3 gap-3">
                  <div class="rounded-lg bg-white px-3 py-2 text-center shadow-sm">
                    <p class="text-[10px] font-medium uppercase text-muted">Today (actual)</p>
                    <p class="mt-0.5 text-sm font-bold text-text">₦{{ insight.currentRate | number:'1.2-2' }}</p>
                  </div>
                  <div class="rounded-lg bg-white px-3 py-2 text-center shadow-sm">
                    <p class="text-[10px] font-medium uppercase text-muted">30-day forecast</p>
                    <p class="mt-0.5 text-sm font-bold text-text">₦{{ insight.day30.base | number:'1.2-2' }}</p>
                  </div>
                  <div class="rounded-lg bg-white px-3 py-2 text-center shadow-sm">
                    <p class="text-[10px] font-medium uppercase text-muted">{{ insight.days }}-day forecast</p>
                    <p class="mt-0.5 text-sm font-bold text-text">₦{{ insight.last.base | number:'1.2-2' }}</p>
                  </div>
                </div>

                <!-- Action recommendation -->
                <div class="mt-3 rounded-lg border px-4 py-3" [class]="insight.actionColor">
                  <p class="text-[11px] font-semibold uppercase tracking-wide opacity-70">Importer guidance</p>
                  <p class="mt-1 text-xs leading-relaxed">{{ insight.action }}</p>
                </div>

                <p class="mt-2 text-[10px] text-muted">
                  <i class="pi pi-info-circle mr-1"></i>
                  Forecast uses Prophet + Monte Carlo simulation trained on {{ insight.days }} days of history. Not financial advice — ranges reflect 80% confidence interval.
                </p>
              </div>
            </div>
          </div>
        }

        <!-- Forecast Table -->
        @if (forecasts().length > 0) {
          <div class="mt-5">
            <!-- Page size selector -->
            <div class="mb-3 flex items-center justify-between">
              <p class="text-xs text-muted">
                Showing {{ forecastPage() * forecastPageSize() + 1 }}–{{ forecastPageEnd() }}
                of {{ forecasts().length }} days
              </p>
              <div class="flex items-center gap-2">
                <span class="text-xs text-muted">Rows per page:</span>
                <div class="flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-0.5">
                  @for (size of forecastPageSizeOptions; track size) {
                    <button
                      (click)="setForecastPageSize(size)"
                      class="rounded-md px-2.5 py-1 text-xs font-medium transition-colors"
                      [class]="forecastPageSize() === size ? 'bg-white text-primary shadow-sm' : 'text-muted hover:text-text'"
                    >{{ size }}</button>
                  }
                </div>
              </div>
            </div>

            <div class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200 text-sm">
                <caption class="sr-only">FX rate forecast data</caption>
                <thead>
                  <tr class="bg-gray-50/80">
                    <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Date</th>
                    <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Base</th>
                    <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Best</th>
                    <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Worst</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                  @for (f of pagedForecasts(); track f.date) {
                    <tr class="transition-colors hover:bg-gray-50/50">
                      <td class="px-3 py-2.5 text-muted">{{ f.date | date: 'mediumDate' }}</td>
                      <td class="px-3 py-2.5 text-right font-semibold">{{ f.base | number: '1.2-2' }}</td>
                      <td class="px-3 py-2.5 text-right font-medium text-success">{{ f.best_case | number: '1.2-2' }}</td>
                      <td class="px-3 py-2.5 text-right font-medium text-danger">{{ f.worst_case | number: '1.2-2' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>

            <!-- Pagination controls -->
            @if (forecastTotalPages() > 1) {
              <div class="mt-3 flex items-center justify-between">
                <button
                  (click)="forecastPage.set(forecastPage() - 1)"
                  [disabled]="forecastPage() === 0"
                  class="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <i class="pi pi-chevron-left text-[10px]"></i> Previous
                </button>
                <div class="flex items-center gap-1">
                  @for (p of pageRange(); track p) {
                    @if (p === -1) {
                      <span class="px-1 text-xs text-muted">…</span>
                    } @else {
                      <button
                        (click)="forecastPage.set(p)"
                        class="min-w-[28px] rounded-md px-2 py-1 text-xs font-medium transition-colors"
                        [class]="forecastPage() === p ? 'bg-primary text-white' : 'text-muted hover:bg-gray-100 hover:text-text'"
                      >{{ p + 1 }}</button>
                    }
                  }
                </div>
                <button
                  (click)="forecastPage.set(forecastPage() + 1)"
                  [disabled]="forecastPage() >= forecastTotalPages() - 1"
                  class="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next <i class="pi pi-chevron-right text-[10px]"></i>
                </button>
              </div>
            }
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
              <option value="EURNGN">EUR/NGN</option>
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
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Pair</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Direction</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Threshold</th>
                  <th class="px-3 py-2.5 text-center text-xs font-semibold uppercase text-muted">Status</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (alert of alerts(); track alert.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 font-medium text-text">{{ alert.pair }}</td>
                    <td class="px-3 py-2.5">
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                        [class]="alert.direction === 'above' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
                      >
                        <i class="pi mr-1 text-[10px]" [class]="alert.direction === 'above' ? 'pi-arrow-up' : 'pi-arrow-down'"></i>
                        {{ alert.direction }}
                      </span>
                    </td>
                    <td class="px-3 py-2.5 text-right font-semibold">{{ alert.threshold_rate | number: '1.2-2' }}</td>
                    <td class="px-3 py-2.5 text-center">
                      <button
                        (click)="toggleAlert(alert)"
                        class="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors"
                        [class]="alert.is_enabled ? 'bg-green-100 text-green-700 hover:bg-green-200' : 'bg-gray-100 text-gray-500 hover:bg-gray-200'"
                      >
                        <i class="pi text-[10px]" [class]="alert.is_enabled ? 'pi-check-circle' : 'pi-times-circle'"></i>
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
  latestEurNgn = signal<FxRate | null>(null);
  historyRates = signal<FxRate[]>([]);
  historyChartData = signal<unknown>(null);
  forecastChartData = signal<unknown>(null);
  forecasts = signal<FxForecast[]>([]);

  alerts = signal<FXAlertRead[]>([]);
  forecastDays = signal(180);
  forecastPair = signal<ForecastPair>('USDNGN');
  forecastGenerating = signal(false);
  backfilling = signal(false);
  forecastPage = signal(0);
  forecastPageSize = signal(10);
  readonly forecastRangeOptions = [30, 90, 180];
  readonly forecastPageSizeOptions = [10, 25, 50];

  pagedForecasts = computed(() => {
    const start = this.forecastPage() * this.forecastPageSize();
    return this.forecasts().slice(start, start + this.forecastPageSize());
  });

  forecastTotalPages = computed(() =>
    Math.ceil(this.forecasts().length / this.forecastPageSize()),
  );

  forecastPageEnd = computed(() =>
    Math.min(this.forecasts().length, (this.forecastPage() + 1) * this.forecastPageSize()),
  );

  forecastInsight = computed(() => {
    const fc = this.forecasts();
    if (fc.length < 2) return null;
    const pair = this.forecastPair();
    const currencyLabel = pair === 'USDNGN' ? 'USD' : 'EUR';

    // Use the actual live rate for the current rate card, not the first forecast value
    const currentRateSignal = pair === 'USDNGN' ? this.latestRate() : this.latestEurNgn();
    const currentRate = currentRateSignal?.rate ?? fc[0].base;

    const day30 = fc[Math.min(29, fc.length - 1)];  // day 30 of forecast
    const last = fc[fc.length - 1];                  // end of forecast window

    const trendPct = ((last.base - currentRate) / currentRate) * 100;
    const worstCasePct = ((last.worst_case - currentRate) / currentRate) * 100;
    const bestCasePct = ((last.best_case - currentRate) / currentRate) * 100;

    const weakening = trendPct > 1.5;
    const strengthening = trendPct < -1.5;

    let trend: 'weaken' | 'strengthen' | 'stable';
    let trendIcon: string;
    let trendColor: string;
    let headline: string;
    let summary: string;
    let action: string;
    let actionColor: string;

    if (weakening) {
      trend = 'weaken';
      trendIcon = 'pi-arrow-trend-up';
      trendColor = 'text-danger';
      headline = `NGN expected to weaken ${Math.abs(trendPct).toFixed(1)}% against ${currencyLabel} over ${fc.length} days`;
      summary = `Today's rate is ₦${currentRate.toFixed(2)}. The model forecasts it rising to ₦${last.base.toFixed(2)} by day ${fc.length}. In a worst-case scenario it could reach ₦${last.worst_case.toFixed(2)} (+${worstCasePct.toFixed(1)}% from today).`;
      action = `Consider buying ${currencyLabel} sooner rather than later. Every week you delay, the same payment could cost more NGN. If you have confirmed supplier invoices due in the next ${fc.length} days, locking in your FX now protects your margin.`;
      actionColor = 'bg-red-50 border-red-200 text-red-800';
    } else if (strengthening) {
      trend = 'strengthen';
      trendIcon = 'pi-arrow-trend-down';
      trendColor = 'text-success';
      headline = `NGN expected to strengthen ${Math.abs(trendPct).toFixed(1)}% against ${currencyLabel} over ${fc.length} days`;
      summary = `Today's rate is ₦${currentRate.toFixed(2)}. The model forecasts it falling to ₦${last.base.toFixed(2)} by day ${fc.length}. In the best case it could reach ₦${last.best_case.toFixed(2)} (${bestCasePct.toFixed(1)}% from today).`;
      action = `You may benefit from waiting before converting to ${currencyLabel}. However, do not delay beyond confirmed payment deadlines — use the 30-day checkpoint of ₦${day30.base.toFixed(2)} to reassess.`;
      actionColor = 'bg-green-50 border-green-200 text-green-800';
    } else {
      trend = 'stable';
      trendIcon = 'pi-minus';
      trendColor = 'text-muted';
      headline = `NGN / ${currencyLabel} rate expected to remain broadly stable over ${fc.length} days`;
      summary = `Today's rate is ₦${currentRate.toFixed(2)}. The model forecasts ₦${last.base.toFixed(2)} by day ${fc.length} (${trendPct >= 0 ? '+' : ''}${trendPct.toFixed(1)}%). The range runs from ₦${last.best_case.toFixed(2)} to ₦${last.worst_case.toFixed(2)}.`;
      action = `No urgent action required on timing alone. Buy ${currencyLabel} when you have confirmed invoices rather than speculating on direction.`;
      actionColor = 'bg-blue-50 border-blue-200 text-blue-800';
    }

    return { trend, trendIcon, trendColor, headline, summary, action, actionColor,
      currentRate, day30, last, trendPct, currencyLabel, days: fc.length };
  });

  pageRange = computed(() => {
    const total = this.forecastTotalPages();
    const cur = this.forecastPage();
    if (total <= 7) return Array.from({ length: total }, (_, i) => i);
    const pages: number[] = [0];
    if (cur > 2) pages.push(-1);
    for (let p = Math.max(1, cur - 1); p <= Math.min(total - 2, cur + 1); p++) pages.push(p);
    if (cur < total - 3) pages.push(-1);
    pages.push(total - 1);
    return pages;
  });

  manualRate = 0;
  manualDate = new Date().toISOString().split('T')[0];
  manualSource = 'PARALLEL_MARKET';
  manualPair = 'USDNGN';

  alertPair = 'USDNGN';
  alertDirection: 'above' | 'below' = 'above';
  alertThreshold = 0;

  readonly fmtSource = fmtSource;

  readonly chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top' as const },
      tooltip: {
        callbacks: {
          label: (ctx: { dataset: { label: string }; parsed: { y: number } }) =>
            `${ctx.dataset.label}: ₦${ctx.parsed.y.toFixed(2)}`,
        },
      },
    },
    scales: {
      x: { ticks: { maxTicksLimit: 12, maxRotation: 0 } },
      y: {
        beginAtZero: false,
        ticks: {
          callback: (v: number) => `₦${v.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        },
      },
    },
  };

  ngOnInit(): void {
    this.fxService.getLatest().subscribe({ next: (r) => this.latestRate.set(r) });
    this.fxService.getLatestEurUsd().subscribe({ next: (r) => this.latestEurUsd.set(r) });
    this.fxService.getLatestEurNgn().subscribe({ next: (r) => this.latestEurNgn.set(r) });
    this.fxService.getAlerts().subscribe({ next: (a) => this.alerts.set(a) });
    this.loadHistoryChart();
    this.loadForecast(180, 'USDNGN');
  }

  private loadHistoryChart(): void {
    forkJoin({
      usd: this.fxService.getHistory(90, 'USDNGN').pipe(catchError(() => of([] as FxRate[]))),
      eur: this.fxService.getHistory(90, 'EURNGN').pipe(catchError(() => of([] as FxRate[]))),
    }).subscribe({
      next: ({ usd, eur }) => {
        this.historyRates.set(usd);
        if (usd.length > 0) {
          const datasets: unknown[] = [
            {
              label: 'USD/NGN',
              data: usd.map((r) => r.rate),
              borderColor: '#1F4E79',
              backgroundColor: 'rgba(31, 78, 121, 0.05)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
              pointHoverRadius: 5,
            },
          ];
          if (eur.length > 0) {
            datasets.push({
              label: 'EUR/NGN',
              data: eur.map((r) => r.rate),
              borderColor: '#C0392B',
              backgroundColor: 'rgba(192, 57, 43, 0.05)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
              pointHoverRadius: 5,
            });
          }
          this.historyChartData.set({ labels: usd.map((r) => fmtChartDate(r.rate_date)), datasets });
        }
      },
    });
  }

  private buildForecastDatasets(fc: FxForecast[], pair: ForecastPair) {
    const baseColor = pair === 'USDNGN' ? '#1F4E79' : '#C0392B';
    const bandColor = pair === 'USDNGN' ? 'rgba(100, 160, 130, 0.1)' : 'rgba(220, 150, 140, 0.1)';
    const worstColor = pair === 'USDNGN' ? 'rgba(192, 57, 43, 0.5)' : 'rgba(150, 50, 50, 0.5)';
    const bestColor = pair === 'USDNGN' ? 'rgba(26, 122, 74, 0.5)' : 'rgba(26, 100, 180, 0.5)';
    return {
      labels: fc.map((f) => fmtChartDate(f.date)),
      datasets: [
        {
          label: 'Worst Case',
          data: fc.map((f) => f.worst_case),
          borderColor: worstColor,
          fill: false,
          borderWidth: 1.5,
          tension: 0.4,
          pointRadius: 0,
        },
        {
          label: 'Best Case',
          data: fc.map((f) => f.best_case),
          borderColor: bestColor,
          backgroundColor: bandColor,
          fill: '-1',
          borderWidth: 1.5,
          tension: 0.4,
          pointRadius: 0,
        },
        {
          label: 'Base',
          data: fc.map((f) => f.base),
          borderColor: baseColor,
          backgroundColor: 'rgba(0,0,0,0)',
          fill: false,
          borderWidth: 2.5,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 6,
        },
      ],
    };
  }

  private loadForecast(days: number, pair: ForecastPair): void {
    this.forecastChartData.set(null);
    this.forecasts.set([]);
    this.fxService.getForecast(days, pair).pipe(
      switchMap((fc) => {
        if (fc.length > 0) return of(fc);
        this.forecastGenerating.set(true);
        return this.fxService.generateForecast(pair, days).pipe(
          switchMap(() => this.fxService.getForecast(days, pair)),
        );
      }),
    ).subscribe({
      next: (fc) => {
        this.forecastGenerating.set(false);
        this.forecasts.set(fc);
        this.forecastPage.set(0);
        this.forecastChartData.set(this.buildForecastDatasets(fc, pair));
      },
      error: () => {
        this.forecastGenerating.set(false);
        this.messageService.add({
          severity: 'warn',
          summary: 'Forecast unavailable',
          detail: 'At least 30 days of rate history is needed. Click "Load History" first, then try again.',
        });
      },
    });
  }

  setForecastRange(days: number): void {
    this.forecastDays.set(days);
    this.forecastPage.set(0);
    this.loadForecast(days, this.forecastPair());
  }

  switchForecastPair(pair: ForecastPair): void {
    if (pair === this.forecastPair()) return;
    this.forecastPair.set(pair);
    this.forecastPage.set(0);
    this.loadForecast(this.forecastDays(), pair);
  }

  setForecastPageSize(size: number): void {
    this.forecastPageSize.set(size);
    this.forecastPage.set(0);
  }

  refreshForecast(): void {
    const pair = this.forecastPair();
    this.forecastGenerating.set(true);
    this.forecastChartData.set(null);
    this.forecasts.set([]);
    this.fxService.generateForecast(pair, this.forecastDays()).pipe(
      switchMap(() => this.fxService.getForecast(this.forecastDays(), pair)),
    ).subscribe({
      next: (fc) => {
        this.forecastGenerating.set(false);
        this.forecasts.set(fc);
        this.forecastChartData.set(this.buildForecastDatasets(fc, pair));
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
    forkJoin({
      usd: this.fxService.backfillFreeRates('USDNGN', 90),
      eur: this.fxService.backfillFreeRates('EURNGN', 90),
    }).subscribe({
      next: ({ usd, eur }) => {
        this.backfilling.set(false);
        const total = usd.records_inserted + eur.records_inserted;
        this.messageService.add({
          severity: 'success',
          summary: 'History loaded',
          detail: total > 0
            ? `${usd.records_inserted} USD/NGN + ${eur.records_inserted} EUR/NGN rates added.`
            : 'Rate history is already up to date.',
        });
        // Refresh rate cards and chart
        this.fxService.getLatestEurNgn().subscribe({ next: (r) => this.latestEurNgn.set(r) });
        this.loadHistoryChart();
        if (total > 0) {
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
          } else if (this.manualPair === 'EURNGN') {
            this.latestEurNgn.set(r);
          } else {
            this.latestRate.set(r);
          }
          this.messageService.add({
            severity: 'success',
            summary: 'Added',
            detail: `${this.manualPair} rate recorded`,
          });
          if (this.forecasts().length === 0) {
            this.loadForecast(this.forecastDays(), this.forecastPair());
          }
        },
        error: () => {
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to add rate' });
        },
      });
  }

  createAlert(): void {
    if (!this.alertThreshold || this.alertThreshold <= 0) return;
    this.fxService
      .createAlert({ pair: this.alertPair, direction: this.alertDirection, threshold_rate: this.alertThreshold })
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
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create alert' });
        },
      });
  }

  toggleAlert(alert: FXAlertRead): void {
    this.fxService.updateAlert(alert.id, { is_enabled: !alert.is_enabled }).subscribe({
      next: (updated) => {
        this.alerts.update((list) => list.map((a) => (a.id === updated.id ? updated : a)));
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update alert' });
      },
    });
  }

  exportHistoryCsv(): void {
    const rates = this.historyRates();
    if (rates.length === 0) return;
    const csv = ['Date,Rate,Source', ...rates.map((r) => `${r.rate_date},${r.rate},${r.source}`)].join('\n');
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
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to export FX rates CSV' });
      },
    });
  }

  deleteAlert(id: string): void {
    this.fxService.deleteAlert(id).subscribe({
      next: () => {
        this.alerts.update((list) => list.filter((a) => a.id !== id));
        this.messageService.add({ severity: 'info', summary: 'Deleted', detail: 'Alert removed' });
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to delete alert' });
      },
    });
  }
}
