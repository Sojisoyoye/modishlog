import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe, CurrencyPipe } from '@angular/common';
import { UIChart } from 'primeng/chart';
import {
  CashflowService,
  CashflowMonth,
  LiquidityInfo,
  ScenarioResult,
} from '../../../core/services/cashflow.service';

@Component({
  selector: 'app-cashflow-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, CurrencyPipe, UIChart],
  template: `
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Cashflow</h2>
        <p class="mt-1 text-sm text-muted">Monitor liquidity and project future cashflows</p>
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Liquidity Metrics -->
        <div class="space-y-4">
          <div class="rounded-xl border bg-white p-5 shadow-sm" [class]="liquidityBorder()">
            <div class="mb-2 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
                <i class="pi pi-clock text-sm text-blue-700"></i>
              </div>
              <p class="text-sm font-medium text-muted">Cash Runway</p>
            </div>
            <p class="text-3xl font-bold text-text">
              {{ liquidity().runway_is_finite ? runwayMonths() + ' months' : 'No burn' }}
            </p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div class="mb-2 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
                <i class="pi pi-chart-line text-sm text-emerald-700"></i>
              </div>
              <p class="text-sm font-medium text-muted">DSCR</p>
            </div>
            <p class="text-3xl font-bold" [class]="dscrColor()">
              {{ liquidity().dscr_is_finite ? (liquidity().dscr | number: '1.2-2') : 'No debt' }}
            </p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
                  <i class="pi pi-shield text-sm text-amber-700"></i>
                </div>
                <p class="text-sm font-medium text-muted">Risk Rating</p>
              </div>
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                [class]="
                  riskStatus() === 'success'
                    ? 'bg-emerald-100 text-emerald-800'
                    : riskStatus() === 'warning'
                      ? 'bg-amber-100 text-amber-800'
                      : riskStatus() === 'danger'
                        ? 'bg-red-100 text-red-800'
                        : 'bg-gray-100 text-gray-700'
                "
              >{{ liquidity().risk_rating }}</span>
            </div>
          </div>

          <!-- Alerts -->
          @if (liquidity().alerts.length > 0) {
            <div class="space-y-2">
              @for (alert of liquidity().alerts; track alert.message) {
                <div
                  role="alert"
                  class="rounded-lg border-l-4 p-4 text-sm"
                  [class]="
                    alert.severity === 'HIGH'
                      ? 'border-l-red-500 bg-red-50'
                      : alert.severity === 'MEDIUM'
                        ? 'border-l-amber-500 bg-amber-50'
                        : 'border-l-emerald-500 bg-emerald-50'
                  "
                >
                  <i
                    class="pi pi-exclamation-triangle mr-1 text-xs"
                    [class]="alert.severity === 'HIGH' ? 'text-red-600' : alert.severity === 'MEDIUM' ? 'text-amber-600' : 'text-emerald-700'"
                  ></i>
                  {{ alert.message }}
                </div>
              }
            </div>
          }
        </div>

        <!-- Projection Chart -->
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
              <i class="pi pi-chart-bar text-sm text-emerald-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">6-Month Projection</h3>
          </div>
          @if (projectionChart()) {
            <p-chart
              type="bar"
              [data]="projectionChart()!"
              [options]="projectionOptions"
              height="300px"
            />
          } @else {
            <div class="flex h-[300px] items-center justify-center">
              <p class="text-muted"><i class="pi pi-spinner pi-spin mr-2"></i>Loading...</p>
            </div>
          }
        </div>
      </div>

      <!-- Projection Table -->
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
            <i class="pi pi-table text-sm text-emerald-700"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Month-by-Month</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Monthly cashflow projection</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Month
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Inflows
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Outflows
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">Net</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Cumulative
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  DSCR
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (m of projection(); track m.month) {
                <tr class="transition-colors hover:bg-gray-50/50">
                  <td class="px-4 py-3 font-semibold text-text">{{ m.month }}</td>
                  <td class="px-4 py-3 text-right font-medium text-success">
                    {{ m.inflows | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right font-medium text-danger">
                    {{ m.outflows | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td
                    class="px-4 py-3 text-right font-bold"
                    [class]="m.net_cashflow >= 0 ? 'text-success' : 'text-danger'"
                  >
                    {{ m.net_cashflow | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    {{ m.cumulative | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td
                    class="px-4 py-3 text-right font-semibold"
                    [class]="
                      !m.dscr_is_finite || m.dscr >= 1.5
                        ? 'text-success'
                        : m.dscr >= 1.0
                          ? 'text-warning'
                          : 'text-danger'
                    "
                  >
                    {{ m.dscr_is_finite ? (m.dscr | number: '1.2-2') : 'No debt' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Scenario Simulator -->
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
            <i class="pi pi-sliders-h text-sm text-emerald-700"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Scenario Simulator</h3>
        </div>
        <div class="flex flex-wrap items-end gap-4">
          <div>
            <label for="cf-fx-shock" class="mb-1.5 block text-xs font-medium text-muted">FX Shock (%)</label>
            <input
              id="cf-fx-shock"
              type="number"
              [(ngModel)]="fxShock"
              class="w-28 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
              step="5"
            />
          </div>
          <div>
            <label for="cf-demand-drop" class="mb-1.5 block text-xs font-medium text-muted">Demand Drop (%)</label>
            <input
              id="cf-demand-drop"
              type="number"
              [(ngModel)]="demandDrop"
              class="w-28 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
              step="5"
            />
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              (click)="fxShock = 10; demandDrop = 0; runScenario()"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2.5 text-xs font-medium transition-colors hover:bg-gray-50"
            >
              FX +10%
            </button>
            <button
              (click)="fxShock = 20; demandDrop = 0; runScenario()"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2.5 text-xs font-medium transition-colors hover:bg-gray-50"
            >
              FX +20%
            </button>
            <button
              (click)="fxShock = 0; demandDrop = 10; runScenario()"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2.5 text-xs font-medium transition-colors hover:bg-gray-50"
            >
              Demand -10%
            </button>
            <button
              (click)="fxShock = 0; demandDrop = 20; runScenario()"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2.5 text-xs font-medium transition-colors hover:bg-gray-50"
            >
              Demand -20%
            </button>
            <button
              (click)="fxShock = 20; demandDrop = 20; runScenario()"
              class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-2.5 text-xs font-medium transition-colors hover:bg-gray-50"
            >
              Combined Stress
            </button>
          </div>
          <button
            (click)="runScenario()"
            class="flex min-h-[44px] items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md"
          >
            <i class="pi pi-play text-sm"></i> Simulate
          </button>
        </div>
        @if (scenarioResult()) {
          <div class="mt-5 rounded-xl border border-gray-100 bg-gray-50 p-5">
            <p class="text-sm font-bold text-text">{{ scenarioResult()!.label }}</p>
            <div class="mt-3 grid grid-cols-3 gap-6 text-sm">
              <div>
                <p class="text-xs font-medium text-muted">Worst DSCR</p>
                <p
                  class="mt-1 text-2xl font-bold"
                  [class]="
                    !scenarioResult()!.worst_dscr_is_finite || scenarioResult()!.worst_dscr >= 1.0
                      ? 'text-success'
                      : 'text-danger'
                  "
                >
                  {{
                    scenarioResult()!.worst_dscr_is_finite
                      ? (scenarioResult()!.worst_dscr | number: '1.2-2')
                      : 'No debt'
                  }}
                </p>
              </div>
              <div>
                <p class="text-xs font-medium text-muted">Cash Runway</p>
                <p class="mt-1 text-2xl font-bold text-text">
                  {{
                    scenarioResult()!.cash_runway_is_finite
                      ? scenarioRunwayMonths() + ' months'
                      : 'No burn'
                  }}
                </p>
              </div>
              @if (scenarioResult()!.risk_rating) {
                <div>
                  <p class="text-xs font-medium text-muted">Portfolio Margin</p>
                  <p class="mt-1 text-lg font-semibold"
                    [class]="scenarioResult()!.risk_rating === 'HIGH' ? 'text-danger' : scenarioResult()!.risk_rating === 'MEDIUM' ? 'text-warning' : 'text-success'"
                  >
                    Likely impacted
                    <span class="ml-1 rounded-full px-2 py-0.5 text-xs font-medium"
                      [class]="scenarioResult()!.risk_rating === 'HIGH' ? 'bg-red-100 text-red-700' : scenarioResult()!.risk_rating === 'MEDIUM' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'"
                    >{{ scenarioResult()!.risk_rating }}</span>
                  </p>
                </div>
              }
            </div>
          </div>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CashflowPageComponent implements OnInit {
  private readonly cashflowService = inject(CashflowService);

  projection = signal<CashflowMonth[]>([]);
  projectionChart = signal<unknown>(null);
  liquidity = signal<LiquidityInfo>({
    cash_runway_days: 0,
    runway_is_finite: true,
    dscr: 0,
    dscr_is_finite: true,
    risk_rating: 'UNKNOWN',
    alerts: [],
  });
  scenarioResult = signal<ScenarioResult | null>(null);
  fxShock = 0;
  demandDrop = 0;

  runwayMonths = computed(() => {
    const days = this.liquidity().cash_runway_days;
    return (days / 30).toFixed(1);
  });

  scenarioRunwayMonths = computed(() => {
    const result = this.scenarioResult();
    if (!result) return '0.0';
    return (result.cash_runway_days / 30).toFixed(1);
  });

  readonly projectionOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    scales: {
      y: { beginAtZero: true },
      x: { grid: { display: false } },
    },
  };

  ngOnInit(): void {
    this.cashflowService.getProjection(6).subscribe({
      next: (months) => {
        this.projection.set(months);
        this.buildChart(months);
      },
    });
    this.cashflowService.getLiquidity().subscribe({
      next: (l) => this.liquidity.set(l),
    });
  }

  private buildChart(months: CashflowMonth[]): void {
    this.projectionChart.set({
      labels: months.map((m) => m.month),
      datasets: [
        {
          label: 'Inflows',
          data: months.map((m) => m.inflows),
          backgroundColor: '#1A7A4A',
          borderRadius: 4,
        },
        {
          label: 'Outflows',
          data: months.map((m) => -Math.abs(m.outflows)),
          backgroundColor: '#C0392B',
          borderRadius: 4,
        },
        {
          label: 'Cumulative',
          data: months.map((m) => m.cumulative),
          type: 'line',
          borderColor: '#1F4E79',
          fill: false,
          tension: 0.3,
          pointRadius: 3,
          pointHoverRadius: 6,
        },
      ],
    });
  }

  dscrColor(): string {
    // No debt is the best case, not a risk signal.
    if (!this.liquidity().dscr_is_finite) return 'text-success';
    const d = this.liquidity().dscr;
    if (d >= 1.5) return 'text-success';
    if (d >= 1.0) return 'text-warning';
    return 'text-danger';
  }

  riskStatus(): 'success' | 'warning' | 'danger' | 'neutral' {
    const r = this.liquidity().risk_rating;
    if (r === 'LOW') return 'success';
    if (r === 'MEDIUM') return 'warning';
    if (r === 'HIGH') return 'danger';
    return 'neutral';
  }

  liquidityBorder(): string {
    const s = this.riskStatus();
    if (s === 'success')
      return 'border-l-4 border-l-success border-t-gray-200 border-r-gray-200 border-b-gray-200';
    if (s === 'warning')
      return 'border-l-4 border-l-warning border-t-gray-200 border-r-gray-200 border-b-gray-200';
    if (s === 'danger')
      return 'border-l-4 border-l-danger border-t-gray-200 border-r-gray-200 border-b-gray-200';
    return 'border-gray-200';
  }

  runScenario(): void {
    this.cashflowService
      .simulateScenario({ fx_shock_pct: this.fxShock, demand_drop_pct: this.demandDrop })
      .subscribe({
        next: (r) => this.scenarioResult.set(r),
      });
  }
}
