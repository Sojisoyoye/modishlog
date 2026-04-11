import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe, DatePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { UIChart } from 'primeng/chart';
import { FxService, FxRate, FxForecast } from '../../../core/services/fx.service';

@Component({
  selector: 'app-fx-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, DatePipe, Toast, UIChart],
  template: `
    <p-toast />
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">FX Rates</h2>
        <p class="mt-1 text-sm text-muted">Track and forecast NGN/USD exchange rates</p>
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
              <label class="mb-1.5 block text-xs font-medium text-muted">Pair</label>
              <select
                [(ngModel)]="manualPair"
                class="rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              >
                <option value="USDNGN">USD/NGN</option>
                <option value="EURUSD">EUR/USD</option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Rate</label>
              <input
                type="number"
                [(ngModel)]="manualRate"
                [placeholder]="manualPair === 'EURUSD' ? 'e.g. 1.08' : 'e.g. 1500'"
                step="0.01"
                class="w-36 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Date</label>
              <input
                type="date"
                [(ngModel)]="manualDate"
                class="w-40 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Source</label>
              <select
                [(ngModel)]="manualSource"
                class="rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
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
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-chart-line text-sm text-secondary"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Historical Rates (90 days)</h3>
        </div>
        @if (historyChartData()) {
          <p-chart
            type="line"
            [data]="historyChartData()!"
            [options]="chartOptions"
            height="300px"
          />
        } @else {
          <div class="flex h-[300px] items-center justify-center">
            <p class="text-muted"><i class="pi pi-spinner pi-spin mr-2"></i>Loading chart...</p>
          </div>
        }
      </div>

      <!-- Forecast -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
            <i class="pi pi-sparkles text-sm text-warning"></i>
          </div>
          <h3 class="text-base font-semibold text-text">30-Day Forecast</h3>
        </div>
        @if (forecastChartData()) {
          <p-chart
            type="line"
            [data]="forecastChartData()!"
            [options]="chartOptions"
            height="300px"
          />
        } @else {
          <div class="flex h-[300px] items-center justify-center">
            <p class="text-muted"><i class="pi pi-spinner pi-spin mr-2"></i>Loading forecast...</p>
          </div>
        }

        <!-- Forecast Table -->
        @if (forecasts().length > 0) {
          <div class="mt-5 overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
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
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FxPageComponent implements OnInit {
  private readonly fxService = inject(FxService);
  private readonly messageService = inject(MessageService);

  latestRate = signal<FxRate | null>(null);
  latestEurUsd = signal<FxRate | null>(null);
  historyChartData = signal<unknown>(null);
  forecastChartData = signal<unknown>(null);
  forecasts = signal<FxForecast[]>([]);

  manualRate = 0;
  manualDate = new Date().toISOString().split('T')[0];
  manualSource = 'PARALLEL_MARKET';
  manualPair = 'USDNGN';

  readonly chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    scales: { y: { beginAtZero: false } },
  };

  ngOnInit(): void {
    this.fxService.getLatest().subscribe({ next: (r) => this.latestRate.set(r) });
    this.fxService.getLatestEurUsd().subscribe({ next: (r) => this.latestEurUsd.set(r) });
    this.fxService.getHistory(90).subscribe({
      next: (rates) => {
        this.historyChartData.set({
          labels: rates.map((r) => r.rate_date),
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
    this.fxService.getForecast(30).subscribe({
      next: (fc) => {
        this.forecasts.set(fc);
        this.forecastChartData.set({
          labels: fc.map((f) => f.date),
          datasets: [
            {
              label: 'Base',
              data: fc.map((f) => f.base),
              borderColor: '#1F4E79',
              backgroundColor: 'rgba(31, 78, 121, 0.05)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
            },
            {
              label: 'Best Case',
              data: fc.map((f) => f.best_case),
              borderColor: '#1A7A4A',
              fill: false,
              borderDash: [5, 5],
              tension: 0.3,
              pointRadius: 0,
            },
            {
              label: 'Worst Case',
              data: fc.map((f) => f.worst_case),
              borderColor: '#C0392B',
              fill: false,
              borderDash: [5, 5],
              tension: 0.3,
              pointRadius: 0,
            },
          ],
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
}
