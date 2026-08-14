import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe, CurrencyPipe, DatePipe } from '@angular/common';
import { UIChart } from 'primeng/chart';
import { Tooltip } from 'primeng/tooltip';
import {
  CashflowService,
  CashflowMonth,
  LiquidityInfo,
  ScenarioResult,
  SavedScenario,
} from '../../../core/services/cashflow.service';

@Component({
  selector: 'app-cashflow-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, CurrencyPipe, DatePipe, UIChart, Tooltip],
  template: `
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Cashflow</h2>
        <p class="mt-1 text-sm text-muted">Monitor liquidity and project future cashflows</p>
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Liquidity Metrics -->
        <div class="space-y-4">
          @if (liquidityLoadFailed()) {
            <div class="rounded-xl border border-red-200 bg-red-50 p-5 shadow-sm">
              <div class="mb-2 flex items-center gap-2">
                <i class="pi pi-exclamation-triangle text-sm text-red-600"></i>
                <p class="text-sm font-medium text-red-800">Failed to load Cash Runway/DSCR data</p>
              </div>
              <button
                (click)="loadLiquidity()"
                class="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-100"
              >
                <i class="pi pi-refresh mr-1 text-xs"></i> Retry
              </button>
            </div>
          } @else {
          <div class="rounded-xl border bg-white p-5 shadow-sm" [class]="liquidityBorder()">
            <div class="mb-2 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
                <i class="pi pi-clock text-sm text-blue-700"></i>
              </div>
              <p class="text-sm font-medium text-muted">Cash Runway</p>
              <i
                class="pi pi-info-circle cursor-help text-[10px] text-muted"
                pTooltip="How many months your money would last if it kept going out at the current rate and nothing new came in."
                tooltipPosition="top"
              ></i>
            </div>
            <p class="text-3xl font-bold text-text">
              {{ liquidity().runway_is_finite ? runwayMonths() + ' months' : 'No burn' }}
              @if (trendIcon(liquidity().runway_trend); as icon) {
                <i
                  [class]="icon.icon + ' ml-1 align-middle text-base ' + icon.colorClass"
                  [attr.aria-label]="'7-day trend: ' + liquidity().runway_trend"
                  [title]="'vs. 7 days ago'"
                ></i>
              }
            </p>
          </div>
          <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
            <div class="mb-2 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
                <i class="pi pi-chart-line text-sm text-emerald-700"></i>
              </div>
              <p class="text-sm font-medium text-muted">Loan Repayment Health <span class="text-muted">(DSCR)</span></p>
              <i
                class="pi pi-info-circle cursor-help text-[10px] text-muted"
                pTooltip="Compares the money coming into your business to your loan payments. Above 1.5 is healthy. Below 1.0 means your income can't fully cover what you owe this month."
                tooltipPosition="top"
              ></i>
            </div>
            <p class="text-3xl font-bold" [class]="dscrColor()">
              {{ liquidity().dscr_is_finite ? (liquidity().dscr | number: '1.2-2') : 'No debt' }}
              @if (trendIcon(liquidity().dscr_trend); as icon) {
                <i
                  [class]="icon.icon + ' ml-1 align-middle text-base ' + icon.colorClass"
                  [attr.aria-label]="'7-day trend: ' + liquidity().dscr_trend"
                  [title]="'vs. 7 days ago'"
                ></i>
              }
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
          }
        </div>

        <!-- Projection Chart -->
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm lg:col-span-2">
          <div class="mb-1 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
              <i class="pi pi-chart-bar text-sm text-emerald-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">6-Month Projection</h3>
          </div>
          <p class="mb-4 ml-10 text-xs text-muted">
            An estimate of how much cash you'll have on hand each month for the next 6 months, based on your typical sales, costs, and loan payments.
          </p>
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
        <div class="mb-1 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
            <i class="pi pi-table text-sm text-emerald-700"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Month-by-Month</h3>
        </div>
        <p class="mb-4 ml-10 text-xs text-muted">
          The detail behind the chart above — see exactly what's expected to come in and go out
          each month, so you can spot a shortfall before it happens.
        </p>
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
                  Loan
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Opex
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  FX
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">Net</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Cumulative
                </th>
                <th
                  class="cursor-help px-4 py-3 text-right text-xs font-semibold uppercase text-muted"
                  pTooltip="Debt Service Coverage Ratio — can that month's income cover that month's loan payments? Above 1.5 is healthy, below 1.0 is a warning."
                  tooltipPosition="top"
                >
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
                    {{ m.loan_payment | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right font-medium text-danger">
                    {{ m.operating_costs | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right font-medium text-danger">
                    {{ m.fx_obligations | currency: 'NGN' : 'symbol' : '1.0-0' }}
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
        <div class="mb-1 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
            <i class="pi pi-sliders-h text-sm text-emerald-700"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Scenario Simulator</h3>
          <i
            class="pi pi-info-circle cursor-help text-[10px] text-muted"
            pTooltip="Test how your cash flow would hold up under bad news — a weaker exchange rate or a drop in sales — before it actually happens, so you can prepare."
            tooltipPosition="top"
          ></i>
        </div>
        <p class="mb-4 ml-10 text-xs text-muted">
          See what would happen to your cash position if the exchange rate got worse or sales
          dropped — before it actually happens.
        </p>
        <div class="flex flex-wrap items-end gap-4">
          <div>
            <label for="cf-fx-shock" class="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted">
              FX Shock (%)
              <i
                class="pi pi-info-circle cursor-help text-[10px]"
                pTooltip="How much worse the exchange rate could get. 10 means 'what if the Naira weakens by 10%?' — your import costs would rise by that much in Naira terms."
                tooltipPosition="top"
              ></i>
            </label>
            <input
              id="cf-fx-shock"
              type="number"
              [(ngModel)]="fxShock"
              class="w-28 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
              step="5"
            />
          </div>
          <div>
            <label for="cf-demand-drop" class="mb-1.5 flex items-center gap-1 text-xs font-medium text-muted">
              Demand Drop (%)
              <i
                class="pi pi-info-circle cursor-help text-[10px]"
                pTooltip="How much your sales could fall. 20 means 'what if customers buy 20% less than usual?'"
                tooltipPosition="top"
              ></i>
            </label>
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
              <div>
                <p class="text-xs font-medium text-muted">Portfolio Margin</p>
                <p class="mt-1 text-lg font-semibold"
                  [class]="scenarioResult()!.margin_pct >= 35 ? 'text-success' : scenarioResult()!.margin_pct >= 25 ? 'text-warning' : 'text-danger'"
                >
                  {{ scenarioResult()!.margin_pct | number: '1.1-1' }}%
                  @if (scenarioResult()!.risk_rating) {
                    <span class="ml-1 rounded-full px-2 py-0.5 text-xs font-medium"
                      [class]="scenarioResult()!.risk_rating === 'HIGH' ? 'bg-red-100 text-red-700' : scenarioResult()!.risk_rating === 'MEDIUM' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'"
                    >{{ scenarioResult()!.risk_rating }}</span>
                  }
                </p>
              </div>
            </div>
          </div>
        }
      </div>

      <!-- Saved Scenarios — task 188 (ST-703 criterion 4): the backend has
           always persisted every scenario run, but there was no frontend
           surface to view or compare them. -->
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
              <i class="pi pi-bookmark text-sm text-amber-600"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Saved Scenarios</h3>
          </div>
          <button
            (click)="loadSavedScenarios()"
            class="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
          >
            <i class="pi pi-refresh text-xs"></i> Refresh
          </button>
        </div>

        @if (savedScenarios().length > 0) {
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Saved stress scenarios</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted"></th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Name</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">FX Shock</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Revenue Shock</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">DSCR</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Runway (mo)</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Saved</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (s of savedScenarios(); track s.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5">
                      <input
                        type="checkbox"
                        [attr.data-testid]="'compare-checkbox-' + s.id"
                        [checked]="isSelectedForCompare(s.id)"
                        [disabled]="!isSelectedForCompare(s.id) && compareSelection().length >= 2"
                        (change)="toggleCompareSelection(s.id)"
                      />
                    </td>
                    <td class="px-3 py-2.5 font-medium text-text">{{ s.name }}</td>
                    <td class="px-3 py-2.5 text-right">{{ s.fx_shock_pct }}%</td>
                    <td class="px-3 py-2.5 text-right">{{ s.revenue_shock_pct }}%</td>
                    <td class="px-3 py-2.5 text-right font-semibold">{{ s.stressed_dscr_is_finite ? (s.stressed_dscr | number: '1.2-2') : 'No debt' }}</td>
                    <td class="px-3 py-2.5 text-right">{{ s.stressed_runway_is_finite ? s.stressed_runway_months : 'No burn' }}</td>
                    <td class="px-3 py-2.5 text-muted">{{ s.created_at | date: 'short' }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          @if (compareSelection().length === 2) {
            <div class="mt-5 grid grid-cols-2 gap-4">
              @for (s of comparedScenarios(); track s.id) {
                <div class="rounded-xl border border-gray-100 bg-gray-50 p-4">
                  <p class="text-sm font-bold text-text">{{ s.name }}</p>
                  <dl class="mt-2 space-y-1 text-sm">
                    <div class="flex justify-between">
                      <dt class="text-muted">DSCR</dt>
                      <dd class="font-semibold">{{ s.stressed_dscr_is_finite ? (s.stressed_dscr | number: '1.2-2') : 'No debt' }}</dd>
                    </div>
                    <div class="flex justify-between">
                      <dt class="text-muted">Cash Runway</dt>
                      <dd class="font-semibold">{{ s.stressed_runway_is_finite ? (s.stressed_runway_months + ' months') : 'No burn' }}</dd>
                    </div>
                    <div class="flex justify-between">
                      <dt class="text-muted">FX Shock</dt>
                      <dd class="font-semibold">{{ s.fx_shock_pct }}%</dd>
                    </div>
                    <div class="flex justify-between">
                      <dt class="text-muted">Revenue Shock</dt>
                      <dd class="font-semibold">{{ s.revenue_shock_pct }}%</dd>
                    </div>
                  </dl>
                </div>
              }
            </div>
          } @else {
            <p class="mt-3 text-xs text-muted">
              <i class="pi pi-info-circle mr-1"></i> Select two scenarios to compare them side-by-side.
            </p>
          }
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> No saved scenarios yet. Run a simulation above to save one.
          </p>
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
    runway_trend: null,
    dscr: 0,
    dscr_is_finite: true,
    dscr_trend: null,
    risk_rating: 'UNKNOWN',
    alerts: [],
  });
  // Task 193 — distinguishes "no data loaded yet" from "load failed", so a
  // /cash-runway or /dscr failure shows a visible error instead of silently
  // leaving the placeholder liquidity signal (which looks like real
  // debt-free/zero data) on screen indefinitely.
  liquidityLoadFailed = signal(false);
  scenarioResult = signal<ScenarioResult | null>(null);
  fxShock = 0;
  demandDrop = 0;

  // Task 188 (ST-703 criterion 4) — saved-scenario list + side-by-side compare.
  savedScenarios = signal<SavedScenario[]>([]);
  compareSelection = signal<string[]>([]);

  comparedScenarios = computed(() => {
    const ids = this.compareSelection();
    return this.savedScenarios().filter((s) => ids.includes(s.id));
  });

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
    this.loadLiquidity();
    this.loadSavedScenarios();
  }

  private buildChart(months: CashflowMonth[]): void {
    // Task 188 (ST-701 criterion 4, PRD 8.2.5): one bar per month for net
    // cashflow, colored by sign — not separate always-green/always-red
    // inflow/outflow bars.
    this.projectionChart.set({
      labels: months.map((m) => m.month),
      datasets: [
        {
          label: 'Net Cashflow',
          data: months.map((m) => m.net_cashflow),
          backgroundColor: months.map((m) => (m.net_cashflow >= 0 ? '#1A7A4A' : '#C0392B')),
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

  // Task 191 (ST-702 criterion 4) — 7-day trend arrows on Cash Runway/DSCR.
  // Null means no snapshot from ~7 days ago exists yet (e.g. a business
  // less than a week old) — show nothing rather than a misleading flat icon.
  trendIcon(trend: 'up' | 'down' | 'flat' | null): { icon: string; colorClass: string } | null {
    if (trend === 'up') return { icon: 'pi pi-arrow-up', colorClass: 'text-success' };
    if (trend === 'down') return { icon: 'pi pi-arrow-down', colorClass: 'text-danger' };
    if (trend === 'flat') return { icon: 'pi pi-minus', colorClass: 'text-muted' };
    return null;
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
        next: (r) => {
          this.scenarioResult.set(r);
          // Backend auto-saves every scenario run — refresh the list so it
          // shows up without a manual click.
          this.loadSavedScenarios();
        },
      });
  }

  loadSavedScenarios(): void {
    this.cashflowService.getScenarios().subscribe({
      next: (scenarios) => this.savedScenarios.set(scenarios),
    });
  }

  loadLiquidity(): void {
    this.liquidityLoadFailed.set(false);
    this.cashflowService.getLiquidity().subscribe({
      next: (l) => this.liquidity.set(l),
      error: () => this.liquidityLoadFailed.set(true),
    });
  }

  isSelectedForCompare(id: string): boolean {
    return this.compareSelection().includes(id);
  }

  toggleCompareSelection(id: string): void {
    this.compareSelection.update((ids) => {
      if (ids.includes(id)) return ids.filter((x) => x !== id);
      if (ids.length >= 2) return ids;
      return [...ids, id];
    });
  }
}
