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
      <h2 class="mb-6 text-xl font-bold text-text">FX Rates</h2>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Current Rate -->
        <div class="rounded-lg border border-gray-200 bg-surface p-6 text-center">
          <p class="text-sm text-muted">Current NGN/USD Rate</p>
          @if (latestRate()) {
            <p class="mt-2 text-4xl font-bold text-primary">
              &#8358;{{ latestRate()!.rate | number: '1.2-2' }}
            </p>
            <p class="mt-1 text-xs text-muted">
              {{ latestRate()!.rate_date | date: 'mediumDate' }} &middot; {{ latestRate()!.source }}
            </p>
          } @else {
            <p class="mt-2 text-lg text-muted">Loading...</p>
          }
        </div>

        <!-- Manual Entry -->
        <div class="rounded-lg border border-gray-200 bg-surface p-5 lg:col-span-2">
          <h3 class="mb-4 text-base font-semibold text-text">Add Rate</h3>
          <div class="flex flex-wrap gap-3">
            <input
              type="number"
              [(ngModel)]="manualRate"
              placeholder="Rate (e.g. 1500)"
              step="0.01"
              class="w-36 rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              type="date"
              [(ngModel)]="manualDate"
              class="w-40 rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <select [(ngModel)]="manualSource" class="rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="MANUAL">Manual</option>
              <option value="PARALLEL_MARKET">Parallel Market</option>
              <option value="CBN_OFFICIAL">CBN Official</option>
            </select>
            <button
              (click)="addRate()"
              class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
            >
              Add
            </button>
          </div>
        </div>
      </div>

      <!-- Historical Chart -->
      <div class="mt-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Historical Rates (90 days)</h3>
        @if (historyChartData()) {
          <p-chart type="line" [data]="historyChartData()!" [options]="chartOptions" height="300px" />
        } @else {
          <p class="text-muted">Loading chart...</p>
        }
      </div>

      <!-- Forecast -->
      <div class="mt-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">30-Day Forecast</h3>
        @if (forecastChartData()) {
          <p-chart type="line" [data]="forecastChartData()!" [options]="chartOptions" height="300px" />
        } @else {
          <p class="text-muted">Loading forecast...</p>
        }

        <!-- Forecast Table -->
        @if (forecasts().length > 0) {
          <div class="mt-4 overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <thead class="bg-gray-50">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Date</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Base</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Best</th>
                  <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Worst</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200">
                @for (f of forecasts(); track f.date) {
                  <tr class="hover:bg-gray-50">
                    <td class="px-3 py-2 text-muted">{{ f.date | date: 'mediumDate' }}</td>
                    <td class="px-3 py-2 text-right font-medium">{{ f.base | number: '1.2-2' }}</td>
                    <td class="px-3 py-2 text-right text-success">{{ f.best_case | number: '1.2-2' }}</td>
                    <td class="px-3 py-2 text-right text-danger">{{ f.worst_case | number: '1.2-2' }}</td>
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
  historyChartData = signal<unknown>(null);
  forecastChartData = signal<unknown>(null);
  forecasts = signal<FxForecast[]>([]);

  manualRate = 0;
  manualDate = new Date().toISOString().split('T')[0];
  manualSource = 'PARALLEL_MARKET';

  readonly chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    scales: { y: { beginAtZero: false } },
  };

  ngOnInit(): void {
    this.fxService.getLatest().subscribe({ next: (r) => this.latestRate.set(r) });
    this.fxService.getHistory(90).subscribe({
      next: (rates) => {
        this.historyChartData.set({
          labels: rates.map((r) => r.rate_date),
          datasets: [
            {
              label: 'NGN/USD',
              data: rates.map((r) => r.rate),
              borderColor: '#1F4E79',
              fill: false,
              tension: 0.3,
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
              fill: false,
              tension: 0.3,
            },
            {
              label: 'Best Case',
              data: fc.map((f) => f.best_case),
              borderColor: '#1A7A4A',
              fill: false,
              borderDash: [5, 5],
              tension: 0.3,
            },
            {
              label: 'Worst Case',
              data: fc.map((f) => f.worst_case),
              borderColor: '#C0392B',
              fill: false,
              borderDash: [5, 5],
              tension: 0.3,
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
        rate_type: 'USDNGN',
        source: this.manualSource,
      })
      .subscribe({
        next: (r) => {
          this.latestRate.set(r);
          this.messageService.add({
            severity: 'success',
            summary: 'Added',
            detail: 'Rate recorded',
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
