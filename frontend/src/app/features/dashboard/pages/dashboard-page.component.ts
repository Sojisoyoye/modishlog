import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, EMPTY } from 'rxjs';
import { switchMap, catchError, debounceTime } from 'rxjs/operators';
import { DecimalPipe, CurrencyPipe, UpperCasePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Select } from 'primeng/select';
import { DatePicker } from 'primeng/datepicker';
import { Tooltip } from 'primeng/tooltip';
import { FormsModule } from '@angular/forms';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { KpiCardComponent, KpiSubLine } from '../../../shared/components/kpi-card/kpi-card.component';
import { DashboardService, DashboardData } from '../../../core/services/dashboard.service';
import { CashflowService, GlobalExposure, TriageStatusResponse } from '../../../core/services/cashflow.service';
import { OrdersService, LogisticsEfficiency } from '../../../core/services/orders.service';
import { FxService } from '../../../core/services/fx.service';
import { DashboardKpiService } from '../services/dashboard-kpi.service';
import { DashboardKpiSummary } from '../models/dashboard-kpi.model';
import { LocationsService, Location } from '../../../core/services/locations.service';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [
    DecimalPipe, CurrencyPipe, UpperCasePipe, RouterLink,
    StatusBadgeComponent, KpiCardComponent,
    Select, DatePicker, Tooltip, FormsModule,
  ],
  template: `
    <div>
      <!-- ============================================================
           KPI Summary Banner (Task 126)
           ============================================================ -->
      <div class="mb-6 rounded-xl bg-gradient-to-r from-blue-600 to-slate-800 p-6 text-white shadow">
        <!-- Welcome heading -->
        <h1 class="mb-4 text-2xl font-bold">Welcome {{ userName() }},</h1>

        <!-- Filters row -->
        <div class="flex flex-wrap items-center gap-3">
          <p-select
            [options]="locationOptions()"
            [(ngModel)]="selectedLocationId"
            optionLabel="label"
            optionValue="value"
            placeholder="Select location"
            [showClear]="true"
            styleClass="w-56"
            (onChange)="onLocationChange()"
            data-testid="location-dropdown"
          />
          <p-datepicker
            [(ngModel)]="dateRange"
            selectionMode="range"
            [readonlyInput]="true"
            placeholder="Filter by date"
            (onSelect)="onDateChange()"
            (onClearClick)="onDateChange()"
            [showButtonBar]="true"
            [iconDisplay]="'input'"
            [showIcon]="true"
          >
            <ng-template pTemplate="inputicon" let-clickCallBack="clickCallBack">
              <i class="pi pi-calendar cursor-pointer" (click)="clickCallBack($event)"></i>
            </ng-template>
          </p-datepicker>
        </div>
      </div>

      <!-- KPI cards grid -->
      <div class="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <!-- Row 1 -->
        <app-kpi-card
          label="TOTAL SALES"
          iconClass="pi pi-shopping-cart"
          iconBgColor="#17A2B8"
          [value]="kpi()?.total_sales ?? '0.00'"
          [loading]="kpiLoading()"
        />
        <app-kpi-card
          label="NET"
          iconClass="pi pi-file"
          iconBgColor="#28A745"
          [value]="kpi()?.net ?? '0.00'"
          [loading]="kpiLoading()"
          [tooltipText]="'Net = Total Sales − Cost of Goods Sold − Expenses'"
        />
        <app-kpi-card
          label="INVOICE DUE"
          iconClass="pi pi-file-edit"
          iconBgColor="#FFC107"
          [value]="kpi()?.invoice_due ?? '0.00'"
          [loading]="kpiLoading()"
        />
        <app-kpi-card
          label="TOTAL SELL RETURN"
          iconClass="pi pi-arrow-right-arrow-left"
          iconBgColor="#E74C3C"
          [value]="kpi()?.total_sell_return ?? '0.00'"
          [loading]="kpiLoading()"
          [subLines]="sellReturnSubLines()"
        />

        <!-- Row 2 -->
        <app-kpi-card
          label="TOTAL PURCHASE"
          iconClass="pi pi-money-bill"
          iconBgColor="#17A2B8"
          [value]="kpi()?.total_purchase ?? '0.00'"
          [loading]="kpiLoading()"
        />
        <app-kpi-card
          label="PURCHASE DUE"
          iconClass="pi pi-exclamation-circle"
          iconBgColor="#FFC107"
          [value]="kpi()?.purchase_due ?? '0.00'"
          [loading]="kpiLoading()"
        />
        <app-kpi-card
          label="TOTAL PURCHASE RETURN"
          iconClass="pi pi-replay"
          iconBgColor="#E74C3C"
          [value]="kpi()?.total_purchase_return ?? '0.00'"
          [loading]="kpiLoading()"
          [subLines]="purchaseReturnSubLines()"
        />
        <app-kpi-card
          label="EXPENSE"
          iconClass="pi pi-minus-circle"
          iconBgColor="#E74C3C"
          [value]="kpi()?.expense ?? '0.00'"
          [loading]="kpiLoading()"
        />
      </div>

      @if (kpiError()) {
        <div class="mb-4 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <i class="pi pi-exclamation-triangle text-danger"></i>
          <p class="text-sm text-danger">Failed to load KPI data.</p>
          <button
            class="ml-auto text-xs font-medium text-danger underline"
            (click)="loadKpi()"
          >Retry</button>
        </div>
      }
      <!-- ============================================================
           End KPI Banner
           ============================================================ -->

      <div class="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 class="text-2xl font-bold text-text">Dashboard</h2>
          <p class="mt-1 text-sm text-muted">Business overview at a glance</p>
        </div>

        <!-- Live FX Rate strip -->
        <div class="flex items-center gap-3 rounded-xl border border-gray-200 bg-white px-4 py-2.5 shadow-sm">
          <div class="flex h-7 w-7 items-center justify-center rounded-lg bg-green-50">
            <i class="pi pi-money-bill text-xs text-success"></i>
          </div>
          @if (liveRates()) {
            <div class="flex items-center gap-4">
              <div class="text-center">
                <p class="text-[10px] font-semibold uppercase tracking-wider text-muted">USD / NGN</p>
                <p class="text-base font-bold text-text">₦{{ liveRates()!.usd_ngn | number: '1.0-0' }}</p>
              </div>
              @if (liveRates()!.eur_ngn) {
                <div class="h-6 w-px bg-gray-200"></div>
                <div class="text-center">
                  <p class="text-[10px] font-semibold uppercase tracking-wider text-muted">EUR / NGN</p>
                  <p class="text-base font-bold text-text">₦{{ liveRates()!.eur_ngn! | number: '1.0-0' }}</p>
                </div>
              }
              <span class="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-semibold text-success">LIVE</span>
            </div>
          } @else {
            <p class="text-xs text-muted">Loading rates…</p>
          }
        </div>
      </div>

      @if (triageStatus()) {
        <div role="alert" class="mb-4 rounded-xl border-l-4 border-l-danger bg-red-50 p-4 shadow-sm">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
                <i class="pi pi-exclamation-triangle text-lg text-danger"></i>
              </div>
              <div>
                <h3 class="text-sm font-bold text-danger">Liquidity Squeeze Alert</h3>
                <p class="text-xs text-red-700">
                  Shortfall of {{ triageStatus()!.shortfall_amount | number: '1.0-0' }} NGN detected
                  within {{ triageStatus()!.horizon_days }} days
                </p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="rounded-full bg-red-100 px-3 py-1 text-xs font-semibold text-danger">
                {{ triageStatus()!.status | uppercase }}
              </span>
              <span class="text-xs text-red-600">
                Since {{ triageStatus()!.trigger_date }}
              </span>
            </div>
          </div>
        </div>
      }

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
                  {{ runwayMonths() }} months
                  <i class="text-sm" [class]="trendArrowClass()"></i>
                </p>
              </div>
              <div>
                <p class="text-xs text-muted">DSCR</p>
                <p class="text-xl font-bold" [class]="dscrColor()">
                  {{ data().liquidity.dscr | number: '1.2-2' }}
                  <i class="text-sm" [class]="trendArrowClass()"></i>
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
          } @else if (!loading()) {
            <div class="h-40 rounded-xl skeleton md:col-span-2"></div>
          }

          <!-- Logistics Efficiency -->
          @if (logistics()) {
            <div class="rounded-xl border bg-white p-5 shadow-sm"
              [class]="logistics()!.status === 'red' ? 'border-l-4 border-l-danger border-t-gray-200 border-r-gray-200 border-b-gray-200' : logistics()!.status === 'amber' ? 'border-l-4 border-l-warning border-t-gray-200 border-r-gray-200 border-b-gray-200' : 'border-gray-200'"
            >
              <div class="mb-3 flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
                    <i class="pi pi-percentage text-sm text-purple-600"></i>
                  </div>
                  <p class="text-sm font-semibold text-text">Logistics %</p>
                </div>
                <span [class]="logistics()!.status === 'red' ? 'rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700' : logistics()!.status === 'amber' ? 'rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700' : 'rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700'">
                  {{ logistics()!.status | uppercase }}
                </span>
              </div>
              <p class="text-3xl font-bold" [class]="logistics()!.status === 'red' ? 'text-danger' : logistics()!.status === 'amber' ? 'text-warning' : 'text-success'">
                {{ logistics()!.rolling_90d_avg_pct | number: '1.1-1' }}%
              </p>
              <p class="mt-1 text-xs text-muted">90-day rolling average</p>
              <div class="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-100">
                <div
                  class="h-2 rounded-full transition-all"
                  [class]="logistics()!.status === 'red' ? 'bg-danger' : logistics()!.status === 'amber' ? 'bg-warning' : 'bg-success'"
                  [style.width.%]="Math.min(logistics()!.rolling_90d_avg_pct / 25 * 100, 100)"
                ></div>
              </div>
              <p class="mt-1 text-xs text-muted">
                Target: &lt;{{ logistics()!.amber_threshold_pct }}%
              </p>
            </div>
          } @else if (!loading()) {
            <div class="h-32 rounded-xl skeleton"></div>
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
  private readonly ordersService = inject(OrdersService);
  private readonly fxService = inject(FxService);
  private readonly kpiService = inject(DashboardKpiService);
  private readonly locationsService = inject(LocationsService);
  private readonly authService = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly kpiTrigger$ = new Subject<{ locationId: string | null; dateFrom: string | null; dateTo: string | null }>();

  // KPI state
  kpi = signal<DashboardKpiSummary | null>(null);
  kpiLoading = signal(false);
  kpiError = signal(false);
  userName = signal('');
  locationOptions = signal<{ label: string; value: string | null }[]>([
    { label: 'All locations', value: null },
  ]);
  selectedLocationId: string | null = null;
  dateRange: Date[] = (() => { const t = new Date(); return [t, t]; })();

  sellReturnSubLines = computed<KpiSubLine[]>(() => {
    const k = this.kpi();
    return [
      { label: 'Total Sell Return', value: k?.total_sell_return ?? '0.00' },
      { label: 'Total Sell Return Paid', value: k?.total_sell_return_paid ?? '0.00' },
    ];
  });

  purchaseReturnSubLines = computed<KpiSubLine[]>(() => {
    const k = this.kpi();
    return [
      { label: 'Total Purchase Return', value: k?.total_purchase_return ?? '0.00' },
      { label: 'Total Purchase Return Paid', value: k?.total_purchase_return_paid ?? '0.00' },
    ];
  });

  loading = signal(true);
  liveRates = signal<{ usd_ngn: number; eur_ngn: number | null } | null>(null);
  triageStatus = signal<TriageStatusResponse | null>(null);
  globalExposure = signal<GlobalExposure | null>(null);
  exposureCurrency = signal<'NGN' | 'USD' | 'EUR'>('NGN');
  readonly currencies: ('NGN' | 'USD' | 'EUR')[] = ['NGN', 'USD', 'EUR'];
  logistics = signal<LogisticsEfficiency | null>(null);
  Math = Math;
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

  runwayMonths = computed(() => {
    const days = this.data().liquidity.cash_runway_days;
    return (days / 30).toFixed(1);
  });

  trendArrowClass(): string {
    const r = this.data().liquidity.risk_rating;
    if (r === 'LOW') return 'pi pi-arrow-up text-success';
    if (r === 'HIGH') return 'pi pi-arrow-down text-danger';
    return 'pi pi-minus text-warning';
  }

  loadKpi(): void {
    const dateFrom = this.dateRange?.[0] ? this.toLocalDateString(this.dateRange[0]) : null;
    const dateTo = this.dateRange?.[1] ? this.toLocalDateString(this.dateRange[1]) : null;
    this.kpiTrigger$.next({ locationId: this.selectedLocationId, dateFrom, dateTo });
  }

  private toLocalDateString(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  onLocationChange(): void {
    this.loadKpi();
  }

  onDateChange(): void {
    // Guard against mid-selection state where only the start date has been picked.
    // After clear, PrimeNG resets to [] so dateRange[1] is undefined — we reset to today.
    if (!this.dateRange[1]) {
      if (this.dateRange.length === 0) {
        const today = new Date();
        this.dateRange = [today, today];
      } else {
        return; // start date picked but end date not yet — wait
      }
    }
    this.loadKpi();
  }

  ngOnInit(): void {
    // Debounced pipeline for filter changes and manual retry — avoids
    // firing on every intermediate state while a user picks a date range.
    this.kpiTrigger$.pipe(
      debounceTime(300),
      switchMap(({ locationId, dateFrom, dateTo }) => {
        this.kpiLoading.set(true);
        this.kpiError.set(false);
        return this.kpiService.getSummary(locationId, dateFrom, dateTo).pipe(
          catchError(() => {
            this.kpiLoading.set(false);
            this.kpiError.set(true);
            return EMPTY;
          }),
        );
      }),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(data => {
      this.kpi.set(data);
      this.kpiLoading.set(false);
    });

    // Initial load bypasses the debounce so the first paint has no delay.
    // dateRange is initialised to [today, today] so the first fetch is already date-scoped.
    this.kpiLoading.set(true);
    const initFrom = this.toLocalDateString(this.dateRange[0]);
    const initTo = this.toLocalDateString(this.dateRange[1]);
    this.kpiService.getSummary(null, initFrom, initTo).pipe(
      takeUntilDestroyed(this.destroyRef),
      catchError(() => {
        this.kpiLoading.set(false);
        this.kpiError.set(true);
        return EMPTY;
      }),
    ).subscribe(data => {
      this.kpi.set(data);
      this.kpiLoading.set(false);
    });

    this.authService.checkSession().subscribe({
      next: (user) => {
        if (user) this.userName.set(user.full_name?.split(' ')?.[0] ?? '');
      },
    });

    this.locationsService.getAll(undefined, true).subscribe({
      next: (res) => {
        this.locationOptions.set([
          { label: 'All locations', value: null },
          ...res.items.map((l: Location) => ({ label: l.name, value: l.id })),
        ]);
      },
    });

    this.dashboardService.loadDashboard().subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
    this.cashflowService.getTriageStatus().subscribe({
      next: (t) => this.triageStatus.set(t),
    });
    this.cashflowService.getGlobalExposure().subscribe({
      next: (e) => this.globalExposure.set(e),
    });
    this.ordersService.getLogisticsEfficiency().subscribe({
      next: (l) => this.logistics.set(l),
    });
    this.fxService.getLiveRate().subscribe({
      next: (live) => {
        this.fxService.getLatestEurUsd().subscribe({
          next: (eur) => {
            const eurNgn = eur ? Math.round(eur.rate * live.usd_ngn) : null;
            this.liveRates.set({ usd_ngn: live.usd_ngn, eur_ngn: eurNgn });
          },
          error: () => this.liveRates.set({ usd_ngn: live.usd_ngn, eur_ngn: null }),
        });
      },
      error: () => this.liveRates.set(null),
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
