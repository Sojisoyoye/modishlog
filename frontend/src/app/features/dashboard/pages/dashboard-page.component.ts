import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, CurrencyPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { DashboardService, DashboardData } from '../../../core/services/dashboard.service';
import { CashflowService, GlobalExposure } from '../../../core/services/cashflow.service';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [DecimalPipe, CurrencyPipe, RouterLink, StatusBadgeComponent],
  template: `
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Dashboard</h2>
        <p class="mt-1 text-sm text-muted">Business overview at a glance</p>
      </div>

      @if (loading()) {
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          @for (i of [1, 2, 3, 4]; track i) {
            <div class="h-32 rounded-xl skeleton"></div>
          }
          @for (i of [1, 2]; track i) {
            <div class="h-48 rounded-xl skeleton md:col-span-2"></div>
          }
        </div>
      } @else {
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <!-- Liquidity Risk -->
          <div class="rounded-xl border bg-white p-5 shadow-sm" [class]="liquidityBorder()">
            <div class="mb-3 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
                  <i class="pi pi-shield text-sm text-secondary"></i>
                </div>
                <p class="text-sm font-semibold text-text">Liquidity</p>
              </div>
              <app-status-badge [label]="data().liquidity.risk_rating" [status]="riskStatus()" />
            </div>
            <div class="space-y-3">
              <div>
                <p class="text-xs text-muted">Cash Runway</p>
                <p class="text-xl font-bold text-text">
                  {{ data().liquidity.cash_runway_days }} days
                </p>
              </div>
              <div>
                <p class="text-xs text-muted">DSCR</p>
                <p class="text-xl font-bold" [class]="dscrColor()">
                  {{ data().liquidity.dscr | number: '1.2-2' }}
                </p>
              </div>
            </div>
          </div>

          <!-- FX Exposure -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
                <i class="pi pi-money-bill text-sm text-success"></i>
              </div>
              <p class="text-sm font-semibold text-text">FX Exposure</p>
            </div>
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-xs text-muted">Locked (USD)</span>
                <span class="text-sm font-bold text-success">
                  {{ data().fxExposure.total_locked_usd | currency: 'USD' : 'symbol' : '1.0-0' }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-xs text-muted">Floating (USD)</span>
                <span class="text-sm font-bold text-warning">
                  {{ data().fxExposure.total_floating_usd | currency: 'USD' : 'symbol' : '1.0-0' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Portfolio Margin -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
                <i class="pi pi-percentage text-sm text-purple-600"></i>
              </div>
              <p class="text-sm font-semibold text-text">Portfolio Margin</p>
            </div>
            <div class="flex items-baseline gap-2">
              <p class="text-2xl font-bold text-text">
                {{ data().portfolioMargin.blended_margin | number: '1.1-1' }}%
              </p>
              <span class="text-xs font-medium" [class]="marginGapColor()">
                @if (data().portfolioMargin.gap >= 0) {
                  +{{ data().portfolioMargin.gap | number: '1.1-1' }}%
                } @else {
                  {{ data().portfolioMargin.gap | number: '1.1-1' }}%
                }
              </span>
            </div>
            <div class="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div
                class="h-2 rounded-full transition-all"
                [class]="data().portfolioMargin.gap >= 0 ? 'bg-success' : 'bg-warning'"
                [style.width.%]="marginBarWidth()"
              ></div>
            </div>
            <p class="mt-1 text-xs text-muted">
              Target: {{ data().portfolioMargin.target_margin }}%
            </p>
          </div>

          <!-- Orders Pipeline -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-3 flex items-center gap-2">
              <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
                <i class="pi pi-truck text-sm text-warning"></i>
              </div>
              <p class="text-sm font-semibold text-text">Orders Pipeline</p>
            </div>
            <div class="space-y-2">
              @for (entry of pipelineEntries(); track entry[0]) {
                <div class="flex items-center justify-between">
                  <span class="text-xs text-muted">{{ entry[0] }}</span>
                  <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-bold text-text">{{
                    entry[1]
                  }}</span>
                </div>
              }
              @if (pipelineEntries().length === 0) {
                <p class="text-xs text-muted">No active orders</p>
              }
            </div>
          </div>

          <!-- Global Exposure -->
          @if (globalExposure()) {
            <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm md:col-span-2">
              <div class="mb-3 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                    <i class="pi pi-globe text-sm text-indigo-600"></i>
                  </div>
                  <p class="text-sm font-semibold text-text">Global Exposure</p>
                </div>
                <div class="flex items-center gap-1.5">
                  @for (cur of currencies; track cur) {
                    <button
                      (click)="exposureCurrency.set(cur)"
                      [class]="exposureCurrency() === cur
                        ? 'rounded-md bg-primary px-2 py-0.5 text-xs font-semibold text-white'
                        : 'rounded-md bg-gray-100 px-2 py-0.5 text-xs font-medium text-muted hover:bg-gray-200'"
                    >{{ cur }}</button>
                  }
                </div>
              </div>
              <div class="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div>
                  <p class="text-xs text-muted">EUR Debt</p>
                  <p class="text-lg font-bold text-text">{{ formatExposureValue(globalExposure()!.eur_loan_balance_eur, 'EUR') }}</p>
                </div>
                <div>
                  <p class="text-xs text-muted">USD Obligations</p>
                  <p class="text-lg font-bold text-text">{{ formatExposureValue(globalExposure()!.open_order_usd_obligations, 'USD') }}</p>
                </div>
                <div>
                  <p class="text-xs text-muted">Total Exposure (NGN)</p>
                  <p class="text-lg font-bold text-primary">{{ globalExposure()!.total_global_exposure_ngn | number: '1.0-0' }}</p>
                </div>
                <div>
                  <p class="text-xs text-muted">Debt/Trade Ratio</p>
                  <p class="text-lg font-bold" [class]="globalExposure()!.debt_to_trade_ratio > 1.5 ? 'text-danger' : globalExposure()!.debt_to_trade_ratio > 0.8 ? 'text-warning' : 'text-success'">
                    {{ globalExposure()!.debt_to_trade_ratio | number: '1.2-2' }}
                    <i [class]="globalExposure()!.debt_to_trade_ratio > 1.5 ? 'pi pi-arrow-up text-xs text-danger' : 'pi pi-arrow-down text-xs text-success'"></i>
                  </p>
                </div>
              </div>
              <div class="mt-3 flex items-center gap-4 border-t border-gray-100 pt-3 text-xs text-muted">
                <span>EUR/USD: {{ globalExposure()!.eur_usd_rate | number: '1.4-4' }}</span>
                <span>NGN/USD: {{ globalExposure()!.ngn_usd_rate | number: '1.2-2' }}</span>
                <span>EUR/NGN: {{ globalExposure()!.eur_ngn_derived_rate | number: '1.2-2' }}</span>
              </div>
            </div>
          }

          <!-- Inventory Alerts -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm md:col-span-2">
            <div class="mb-3 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50">
                  <i class="pi pi-box text-sm text-danger"></i>
                </div>
                <p class="text-sm font-semibold text-text">Inventory Alerts</p>
              </div>
              <a
                routerLink="/inventory"
                class="text-xs font-medium text-secondary transition-colors hover:text-primary hover:underline"
              >
                View all <i class="pi pi-arrow-right text-[10px]"></i>
              </a>
            </div>
            @if (data().inventoryAlerts.length === 0) {
              <div class="flex items-center gap-2 rounded-lg bg-green-50 p-3">
                <i class="pi pi-check-circle text-success"></i>
                <p class="text-sm text-success">All stock levels healthy</p>
              </div>
            } @else {
              <div class="space-y-2">
                @for (alert of data().inventoryAlerts.slice(0, 5); track alert.product_id) {
                  <div
                    class="flex items-center justify-between rounded-lg border-l-4 border-l-danger bg-red-50 px-3 py-2.5"
                  >
                    <span class="text-sm font-medium text-text">{{ alert.product_name }}</span>
                    <span class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-bold text-danger">
                      {{ alert.current_stock }} left
                    </span>
                  </div>
                }
              </div>
            }
          </div>

          <!-- Top Recommendations -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm md:col-span-2">
            <div class="mb-3 flex items-center justify-between">
              <div class="flex items-center gap-2">
                <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <i class="pi pi-sparkles text-sm text-indigo-600"></i>
                </div>
                <p class="text-sm font-semibold text-text">AI Recommendations</p>
              </div>
              <a
                routerLink="/recommendations"
                class="text-xs font-medium text-secondary transition-colors hover:text-primary hover:underline"
              >
                View all <i class="pi pi-arrow-right text-[10px]"></i>
              </a>
            </div>
            @if (data().recommendations.length === 0) {
              <p class="text-sm text-muted">No pending recommendations</p>
            } @else {
              <div class="space-y-2">
                @for (rec of data().recommendations; track rec.id) {
                  <div
                    class="rounded-lg border border-gray-100 p-3 transition-colors hover:bg-gray-50"
                  >
                    <div class="flex items-start justify-between">
                      <div>
                        <div class="flex items-center gap-2">
                          <app-status-badge
                            [label]="rec.priority"
                            [status]="priorityStatus(rec.priority)"
                          />
                          <span class="text-xs text-muted">{{ rec.category }}</span>
                        </div>
                        <p class="mt-1.5 text-sm font-medium text-text">{{ rec.title }}</p>
                      </div>
                    </div>
                  </div>
                }
              </div>
            }
          </div>
        </div>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardPageComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  private readonly cashflowService = inject(CashflowService);

  loading = signal(true);
  globalExposure = signal<GlobalExposure | null>(null);
  exposureCurrency = signal<'NGN' | 'USD' | 'EUR'>('NGN');
  readonly currencies: ('NGN' | 'USD' | 'EUR')[] = ['NGN', 'USD', 'EUR'];
  data = signal<DashboardData>({
    liquidity: { cash_runway_days: 0, dscr: 0, risk_rating: 'UNKNOWN' },
    fxExposure: {
      total_locked_usd: 0,
      total_floating_usd: 0,
      total_locked_ngn: 0,
      total_floating_ngn: 0,
    },
    portfolioMargin: { blended_margin: 0, target_margin: 35, gap: -35 },
    ordersPipeline: {},
    inventoryAlerts: [],
    recommendations: [],
  });

  ngOnInit(): void {
    this.dashboardService.loadDashboard().subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
    this.cashflowService.getGlobalExposure().subscribe({
      next: (e) => this.globalExposure.set(e),
    });
  }

  formatExposureValue(value: number, baseCurrency: string): string {
    const cur = this.exposureCurrency();
    const ge = this.globalExposure();
    if (!ge) return value.toFixed(0);
    if (cur === baseCurrency) return value.toLocaleString('en', { maximumFractionDigits: 0 });
    if (baseCurrency === 'EUR' && cur === 'USD') return (value * ge.eur_usd_rate).toLocaleString('en', { maximumFractionDigits: 0 });
    if (baseCurrency === 'EUR' && cur === 'NGN') return (value * ge.eur_ngn_derived_rate).toLocaleString('en', { maximumFractionDigits: 0 });
    if (baseCurrency === 'USD' && cur === 'EUR') return ge.eur_usd_rate > 0 ? (value / ge.eur_usd_rate).toLocaleString('en', { maximumFractionDigits: 0 }) : '0';
    if (baseCurrency === 'USD' && cur === 'NGN') return (value * ge.ngn_usd_rate).toLocaleString('en', { maximumFractionDigits: 0 });
    return value.toLocaleString('en', { maximumFractionDigits: 0 });
  }

  riskStatus(): 'success' | 'warning' | 'danger' | 'neutral' {
    const r = this.data().liquidity.risk_rating;
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

  dscrColor(): string {
    const d = this.data().liquidity.dscr;
    if (d >= 1.5) return 'text-success';
    if (d >= 1.0) return 'text-warning';
    return 'text-danger';
  }

  marginGapColor(): string {
    return this.data().portfolioMargin.gap >= 0 ? 'text-success' : 'text-danger';
  }

  marginBarWidth(): number {
    const m = this.data().portfolioMargin.blended_margin;
    const t = this.data().portfolioMargin.target_margin || 35;
    return Math.min((m / t) * 100, 100);
  }

  pipelineEntries(): [string, number][] {
    return Object.entries(this.data().ordersPipeline);
  }

  priorityStatus(priority: string): 'danger' | 'warning' | 'info' {
    if (priority === 'HIGH') return 'danger';
    if (priority === 'MEDIUM') return 'warning';
    return 'info';
  }
}
