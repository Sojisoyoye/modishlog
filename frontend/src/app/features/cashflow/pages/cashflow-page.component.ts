import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe, CurrencyPipe } from '@angular/common';
import { UIChart } from 'primeng/chart';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  CashflowService,
  CashflowMonth,
  LiquidityInfo,
  ScenarioResult,
} from '../../../core/services/cashflow.service';

@Component({
  selector: 'app-cashflow-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, CurrencyPipe, UIChart, StatusBadgeComponent],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Cashflow</h2>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Liquidity Metrics -->
        <div class="space-y-4">
          <div class="rounded-lg border bg-surface p-5" [class]="liquidityBorder()">
            <p class="text-sm text-muted">Cash Runway</p>
            <p class="mt-1 text-3xl font-bold text-text">{{ liquidity().cash_runway_days }} days</p>
          </div>
          <div class="rounded-lg border border-gray-200 bg-surface p-5">
            <p class="text-sm text-muted">DSCR</p>
            <p class="mt-1 text-3xl font-bold" [class]="dscrColor()">
              {{ liquidity().dscr | number: '1.2-2' }}
            </p>
          </div>
          <div class="rounded-lg border border-gray-200 bg-surface p-5">
            <div class="flex items-center justify-between">
              <p class="text-sm text-muted">Risk Rating</p>
              <app-status-badge [label]="liquidity().risk_rating" [status]="riskStatus()" />
            </div>
          </div>

          <!-- Alerts -->
          @if (liquidity().alerts.length > 0) {
            <div class="space-y-2">
              @for (alert of liquidity().alerts; track alert.message) {
                <div
                  class="rounded-lg border-l-4 bg-surface p-3 text-sm"
                  [class]="alert.severity === 'HIGH' ? 'border-l-danger' : 'border-l-warning'"
                >
                  {{ alert.message }}
                </div>
              }
            </div>
          }
        </div>

        <!-- Projection Chart -->
        <div class="rounded-lg border border-gray-200 bg-surface p-5 lg:col-span-2">
          <h3 class="mb-4 text-base font-semibold text-text">6-Month Projection</h3>
          @if (projectionChart()) {
            <p-chart type="bar" [data]="projectionChart()!" [options]="projectionOptions" height="300px" />
          } @else {
            <p class="text-muted">Loading...</p>
          }
        </div>
      </div>

      <!-- Projection Table -->
      <div class="mt-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Month-by-Month</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-muted">Month</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Inflows</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Outflows</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Net</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Cumulative</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">DSCR</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              @for (m of projection(); track m.month) {
                <tr class="hover:bg-gray-50">
                  <td class="px-4 py-3 font-medium">{{ m.month }}</td>
                  <td class="px-4 py-3 text-right text-success">
                    {{ m.inflows | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right text-danger">
                    {{ m.outflows | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right font-medium" [class]="m.net_cashflow >= 0 ? 'text-success' : 'text-danger'">
                    {{ m.net_cashflow | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    {{ m.cumulative | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right" [class]="m.dscr >= 1.5 ? 'text-success' : m.dscr >= 1.0 ? 'text-warning' : 'text-danger'">
                    {{ m.dscr | number: '1.2-2' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Scenario Simulator -->
      <div class="mt-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Scenario Simulator</h3>
        <div class="flex flex-wrap items-end gap-4">
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">FX Shock (%)</label>
            <input
              type="number"
              [(ngModel)]="fxShock"
              class="w-28 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              step="5"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Demand Drop (%)</label>
            <input
              type="number"
              [(ngModel)]="demandDrop"
              class="w-28 rounded-lg border border-gray-300 px-3 py-2 text-sm"
              step="5"
            />
          </div>
          <div class="flex gap-2">
            <button
              (click)="fxShock = 10; demandDrop = 0; runScenario()"
              class="rounded border border-gray-300 px-3 py-2 text-xs hover:bg-gray-50"
            >
              FX +10%
            </button>
            <button
              (click)="fxShock = 20; demandDrop = 0; runScenario()"
              class="rounded border border-gray-300 px-3 py-2 text-xs hover:bg-gray-50"
            >
              FX +20%
            </button>
            <button
              (click)="fxShock = 0; demandDrop = 20; runScenario()"
              class="rounded border border-gray-300 px-3 py-2 text-xs hover:bg-gray-50"
            >
              Demand -20%
            </button>
          </div>
          <button
            (click)="runScenario()"
            class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
          >
            Simulate
          </button>
        </div>
        @if (scenarioResult()) {
          <div class="mt-4 rounded-lg border border-gray-200 p-4">
            <p class="text-sm font-semibold text-text">{{ scenarioResult()!.label }}</p>
            <div class="mt-2 grid grid-cols-2 gap-4 text-sm">
              <div>
                <p class="text-xs text-muted">Worst DSCR</p>
                <p class="font-bold" [class]="scenarioResult()!.worst_dscr >= 1.0 ? 'text-success' : 'text-danger'">
                  {{ scenarioResult()!.worst_dscr | number: '1.2-2' }}
                </p>
              </div>
              <div>
                <p class="text-xs text-muted">Cash Runway</p>
                <p class="font-bold">{{ scenarioResult()!.cash_runway_days }} days</p>
              </div>
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
    dscr: 0,
    risk_rating: 'UNKNOWN',
    alerts: [],
  });
  scenarioResult = signal<ScenarioResult | null>(null);
  fxShock = 0;
  demandDrop = 0;

  readonly projectionOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const } },
    scales: { y: { beginAtZero: true } },
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
        },
        {
          label: 'Outflows',
          data: months.map((m) => -Math.abs(m.outflows)),
          backgroundColor: '#C0392B',
        },
        {
          label: 'Cumulative',
          data: months.map((m) => m.cumulative),
          type: 'line',
          borderColor: '#1F4E79',
          fill: false,
          tension: 0.3,
        },
      ],
    });
  }

  dscrColor(): string {
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
    if (s === 'success') return 'border-success';
    if (s === 'warning') return 'border-warning';
    if (s === 'danger') return 'border-danger';
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
