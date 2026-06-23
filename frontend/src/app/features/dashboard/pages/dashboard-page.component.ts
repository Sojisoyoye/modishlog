import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  computed,
  OnInit,
  DestroyRef,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, EMPTY } from 'rxjs';
import { switchMap, catchError, debounceTime } from 'rxjs/operators';
import { DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { Select } from 'primeng/select';
import { DatePicker } from 'primeng/datepicker';
import { FormsModule } from '@angular/forms';
import { KpiCardComponent, KpiSubLine } from '../../../shared/components/kpi-card/kpi-card.component';
import { DashboardService, DashboardData } from '../../../core/services/dashboard.service';
import { FxService, FxExposureEntry } from '../../../core/services/fx.service';
import { CashflowService, GlobalExposure } from '../../../core/services/cashflow.service';
import { OrdersService, LogisticsEfficiency } from '../../../core/services/orders.service';
import { DashboardKpiService } from '../services/dashboard-kpi.service';
import { DashboardKpiSummary } from '../models/dashboard-kpi.model';
import { LocationsService, Location } from '../../../core/services/locations.service';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [
    DecimalPipe, RouterLink,
    KpiCardComponent, Select, DatePicker, FormsModule,
  ],
  template: `
    <div class="space-y-5">

      <!-- ============================================================
           Welcome Banner + Filters
           ============================================================ -->
      <div class="rounded-2xl bg-gradient-to-br from-slate-800 via-slate-700 to-blue-700 p-5 text-white shadow-lg sm:p-6">
        <div class="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="text-sm font-medium text-blue-200">Good day,</p>
            <h1 class="text-2xl font-bold tracking-tight">{{ userName() }}</h1>
          </div>
          @if (liveRate() !== null) {
            <div class="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-sm backdrop-blur-sm">
              <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-green-400"></span>
              <span class="font-semibold">$1 = ₦{{ liveRate()! | number: '1.0-0' }}</span>
            </div>
          }
        </div>
        <div class="flex flex-wrap items-center gap-3">
          <p-select
            [options]="locationOptions()"
            [(ngModel)]="selectedLocationId"
            optionLabel="label"
            optionValue="value"
            placeholder="All locations"
            [showClear]="true"
            styleClass="w-48"
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

      <!-- ============================================================
           KPI Cards — 8 business metrics
           ============================================================ -->
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <app-kpi-card label="Total Sales"        iconClass="pi pi-chart-bar"    iconBgColor="#0EA5E9" [value]="kpi()?.total_sales       ?? '0.00'" [loading]="kpiLoading()" tooltipText="All completed sales in the selected period" />
        <app-kpi-card label="Net Profit"         iconClass="pi pi-trending-up"  iconBgColor="#22C55E" [value]="kpi()?.net               ?? '0.00'" [loading]="kpiLoading()" tooltipText="Sales Revenue − Cost of Goods Sold − Expenses" />
        <app-kpi-card label="Unpaid Sales"       iconClass="pi pi-clock"        iconBgColor="#F59E0B" [value]="kpi()?.invoice_due       ?? '0.00'" [loading]="kpiLoading()" tooltipText="Sales where payment hasn't been received yet" />
        <app-kpi-card label="Customer Returns"   iconClass="pi pi-undo"         iconBgColor="#EF4444" [value]="kpi()?.total_sell_return ?? '0.00'" [loading]="kpiLoading()" tooltipText="Value of goods returned by customers"          [subLines]="sellReturnSubLines()" />
        <app-kpi-card label="Total Purchased"    iconClass="pi pi-shopping-bag" iconBgColor="#0EA5E9" [value]="kpi()?.total_purchase    ?? '0.00'" [loading]="kpiLoading()" tooltipText="Total value of all purchase orders placed" />
        <app-kpi-card label="Amount Owed"        iconClass="pi pi-credit-card"  iconBgColor="#F59E0B" [value]="kpi()?.purchase_due      ?? '0.00'" [loading]="kpiLoading()" tooltipText="Outstanding balance you owe to suppliers" />
        <app-kpi-card label="Supplier Refunds"   iconClass="pi pi-replay"       iconBgColor="#EF4444" [value]="kpi()?.total_purchase_return ?? '0.00'" [loading]="kpiLoading()" tooltipText="Value of goods returned to suppliers"   [subLines]="purchaseReturnSubLines()" />
        <app-kpi-card label="Monthly Expenses"   iconClass="pi pi-minus-circle" iconBgColor="#8B5CF6" [value]="kpi()?.expense           ?? '0.00'" [loading]="kpiLoading()" tooltipText="Operating costs (rent, salaries, utilities, etc.)" />
      </div>

      @if (kpiError()) {
        <div class="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <i class="pi pi-exclamation-triangle text-red-500"></i>
          <p class="text-sm text-red-600">Could not load your business figures.</p>
          <button class="ml-auto text-xs font-semibold text-red-600 underline" (click)="loadKpi()">Retry</button>
        </div>
      }

      <!-- ============================================================
           Row 1: Cash Health | Order Activity | Profit Margin
           ============================================================ -->
      @if (loading()) {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
          @for (i of [1,2,3]; track i) { <div class="h-44 rounded-xl skeleton"></div> }
        </div>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          @for (i of [1,2]; track i) { <div class="h-48 rounded-xl skeleton"></div> }
        </div>
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
          @for (i of [1,2,3]; track i) { <div class="h-40 rounded-xl skeleton"></div> }
        </div>
      } @else {

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">

          <!-- Cash Health -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center gap-3">
              <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-blue-50">
                <i class="pi pi-wallet text-lg text-blue-600"></i>
              </div>
              <div>
                <p class="font-semibold text-slate-800">Cash Health</p>
                <p class="text-xs text-slate-400">How long your money lasts</p>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-sm text-slate-500">Cash Runway</span>
                <span class="text-sm font-bold text-slate-800">
                  @if (data().liquidity.runway_months > 0) {
                    {{ data().liquidity.runway_months | number: '1.1-1' }} mo
                  } @else { Profitable ✓ }
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm text-slate-500">Profit Score (DSCR)</span>
                <span class="text-sm font-bold" [class]="dscrColor()">
                  @if (data().liquidity.dscr >= 99) { Excellent }
                  @else if (data().liquidity.dscr > 0) { {{ data().liquidity.dscr | number: '1.1-1' }} }
                  @else { — }
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm text-slate-500">Status</span>
                <span class="rounded-full px-3 py-1 text-xs font-semibold" [class]="riskBadgeClass()">
                  {{ riskLabel() }}
                </span>
              </div>
            </div>
          </div>

          <!-- Order Activity -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center gap-3">
              <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-amber-50">
                <i class="pi pi-box text-lg text-amber-600"></i>
              </div>
              <div>
                <p class="font-semibold text-slate-800">Order Activity</p>
                <p class="text-xs text-slate-400">Purchases &amp; shipments</p>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <span class="text-sm text-slate-500">In Progress</span>
                <span class="text-sm font-bold text-slate-800">{{ data().ordersSummary.active_orders }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm text-slate-500">All Time</span>
                <span class="text-sm font-bold text-slate-800">{{ data().ordersSummary.total_orders }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-sm text-slate-500">Delivered</span>
                <span class="text-sm font-bold text-slate-800">{{ data().ordersSummary.by_status['DELIVERED'] || 0 }}</span>
              </div>
            </div>
            <a routerLink="/orders" class="mt-4 flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-700">
              View orders <i class="pi pi-arrow-right text-[10px]"></i>
            </a>
          </div>

          <!-- Profit Margin -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center gap-3">
              <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-purple-50">
                <i class="pi pi-percentage text-lg text-purple-600"></i>
              </div>
              <div>
                <p class="font-semibold text-slate-800">Profit Margin</p>
                <p class="text-xs text-slate-400">Average across all products</p>
              </div>
            </div>
            <div class="flex items-baseline gap-2">
              <p class="text-3xl font-bold tracking-tight" [class]="marginColor()">
                {{ data().profitMargin.blended_margin | number: '1.1-1' }}%
              </p>
              <span class="text-sm font-medium" [class]="marginGapColor()">
                @if (data().profitMargin.margin_gap >= 0) {
                  +{{ data().profitMargin.margin_gap | number: '1.1-1' }}% vs target
                } @else {
                  {{ data().profitMargin.margin_gap | number: '1.1-1' }}% vs target
                }
              </span>
            </div>
            <div class="mt-3 h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div class="h-2 rounded-full transition-all" [class]="marginColor() === 'text-green-600' ? 'bg-green-500' : 'bg-amber-500'" [style.width.%]="marginBarWidth()"></div>
            </div>
            <p class="mt-1.5 text-xs text-slate-400">Target: {{ data().profitMargin.target_margin }}%</p>
          </div>
        </div>

        <!-- ============================================================
             Row 2: FX Exposure | Global Exposure
             ============================================================ -->
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">

          <!-- FX Exposure Widget -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-sky-50">
                  <i class="pi pi-arrow-right-arrow-left text-lg text-sky-600"></i>
                </div>
                <div>
                  <p class="font-semibold text-slate-800">FX Exposure</p>
                  <p class="text-xs text-slate-400">Locked vs floating currency risk on open orders</p>
                </div>
              </div>
              <a routerLink="/fx" class="text-xs font-semibold text-blue-600 hover:text-blue-700">
                Manage <i class="pi pi-arrow-right text-[10px]"></i>
              </a>
            </div>

            @if (fxExposure().length === 0) {
              <div class="rounded-xl bg-slate-50 p-5 text-center">
                <i class="pi pi-info-circle mb-2 text-2xl text-slate-400"></i>
                <p class="font-medium text-slate-600">No FX exposure tracked yet</p>
                <p class="mt-1 text-xs text-slate-400">
                  FX exposure is recorded when purchase orders are created with a USD/EUR component.<br>
                  30% is locked at deposit rate; 70% floats until delivery.
                </p>
                <a routerLink="/orders" class="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline">
                  Create a purchase order <i class="pi pi-arrow-right text-[10px]"></i>
                </a>
              </div>
            } @else {
              <div class="space-y-3">
                @for (entry of fxExposure(); track entry.pair) {
                  <div class="rounded-xl border border-gray-100 p-4">
                    <div class="mb-3 flex items-center justify-between">
                      <span class="rounded-full bg-sky-100 px-3 py-0.5 text-xs font-bold text-sky-700">{{ entry.pair }}</span>
                      <span class="text-xs" [class]="entry.unrealized_pnl >= 0 ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold'">
                        {{ entry.unrealized_pnl >= 0 ? '+' : '' }}{{ entry.unrealized_pnl | number: '1.0-0' }} P&amp;L
                      </span>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                      <div>
                        <p class="text-xs text-slate-400">Locked ({{ (entry.locked_pct * 100) | number: '1.0-0' }}%)</p>
                        <p class="font-bold text-slate-800">{{ entry.locked_amount | number: '1.0-0' }}</p>
                        <p class="text-[10px] text-slate-400">at {{ entry.weighted_locked_rate | number: '1.2-2' }}</p>
                      </div>
                      <div>
                        <p class="text-xs text-slate-400">Floating ({{ (entry.floating_pct * 100) | number: '1.0-0' }}%)</p>
                        <p class="font-bold text-slate-800">{{ entry.floating_amount | number: '1.0-0' }}</p>
                        <p class="text-[10px] text-slate-400">market {{ entry.current_market_rate | number: '1.2-2' }}</p>
                      </div>
                    </div>
                    <!-- Locked vs floating bar -->
                    <div class="mt-3 flex h-2 w-full overflow-hidden rounded-full">
                      <div class="bg-blue-500" [style.width.%]="entry.locked_pct * 100"></div>
                      <div class="bg-amber-400" [style.width.%]="entry.floating_pct * 100"></div>
                    </div>
                    <div class="mt-1 flex justify-between text-[10px] text-slate-400">
                      <span class="flex items-center gap-1"><span class="inline-block h-1.5 w-1.5 rounded-full bg-blue-500"></span> Locked</span>
                      <span class="flex items-center gap-1"><span class="inline-block h-1.5 w-1.5 rounded-full bg-amber-400"></span> Floating</span>
                    </div>
                  </div>
                }
              </div>
            }
          </div>

          <!-- Global Exposure Widget -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center gap-3">
              <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-indigo-50">
                <i class="pi pi-globe text-lg text-indigo-600"></i>
              </div>
              <div>
                <p class="font-semibold text-slate-800">Global Exposure</p>
                <p class="text-xs text-slate-400">Total financial obligations across all currencies</p>
              </div>
            </div>

            @let ge = globalExposure();
            @if (ge) {
              <!-- Total headline -->
              <div class="mb-4 rounded-xl bg-indigo-50 p-4">
                <p class="text-xs font-semibold uppercase tracking-wider text-indigo-400">Total Exposure (NGN)</p>
                <p class="mt-1 text-2xl font-bold text-indigo-700">₦{{ ge.total_global_exposure_ngn | number: '1.0-0' }}</p>
                <div class="mt-2 flex items-center gap-2">
                  <span class="text-xs text-indigo-500">Debt/Trade Ratio:</span>
                  <span class="text-xs font-bold" [class]="ge.debt_to_trade_ratio > 1.5 ? 'text-red-600' : ge.debt_to_trade_ratio > 0.8 ? 'text-amber-600' : 'text-green-600'">
                    {{ ge.debt_to_trade_ratio | number: '1.2-2' }}
                    @if (ge.debt_to_trade_ratio <= 0.8) { (Healthy) }
                    @else if (ge.debt_to_trade_ratio <= 1.5) { (Moderate) }
                    @else { (High) }
                  </span>
                </div>
              </div>

              <!-- Breakdown -->
              <div class="space-y-3">
                <div class="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                  <div class="flex items-center gap-2">
                    <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-green-50 text-xs font-bold text-green-700">$</span>
                    <div>
                      <p class="text-sm font-medium text-slate-700">USD Order Obligations</p>
                      <p class="text-xs text-slate-400">Balance owed on open purchase orders</p>
                    </div>
                  </div>
                  <span class="text-sm font-bold text-slate-800">\${{ ge.open_order_usd_obligations | number: '1.0-0' }}</span>
                </div>

                <div class="flex items-center justify-between rounded-lg border border-gray-100 p-3">
                  <div class="flex items-center gap-2">
                    <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-xs font-bold text-blue-700">€</span>
                    <div>
                      <p class="text-sm font-medium text-slate-700">EUR Loan Balance</p>
                      <p class="text-xs text-slate-400">Outstanding loan obligations in EUR</p>
                    </div>
                  </div>
                  <span class="text-sm font-bold text-slate-800">€{{ ge.eur_loan_balance_eur | number: '1.0-0' }}</span>
                </div>
              </div>

              <!-- FX Rates used -->
              <div class="mt-4 flex flex-wrap gap-3 border-t border-gray-100 pt-3">
                <span class="text-xs text-slate-400">$1 = ₦{{ ge.ngn_usd_rate | number: '1.0-0' }}</span>
                @if (ge.eur_usd_rate_available) {
                  <span class="text-xs text-slate-400">€1 = \${{ ge.eur_usd_rate | number: '1.3-3' }}</span>
                  <span class="text-xs text-slate-400">€1 = ₦{{ ge.eur_ngn_derived_rate | number: '1.0-0' }}</span>
                } @else {
                  <span class="text-xs text-amber-500">EUR/USD rate unavailable</span>
                }
              </div>
            } @else {
              <div class="h-32 rounded-xl skeleton"></div>
            }
          </div>
        </div>

        <!-- ============================================================
             Row 3: Logistics Efficiency | Low Stock | AI Suggestions
             ============================================================ -->
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">

          <!-- Logistics Efficiency -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl" [class]="logisticsIconBg()">
                  <i class="pi pi-truck text-lg" [class]="logisticsIconColor()"></i>
                </div>
                <div>
                  <p class="font-semibold text-slate-800">Shipping Costs</p>
                  <p class="text-xs text-slate-400">Logistics as % of order value</p>
                </div>
              </div>
              <a routerLink="/orders" class="text-xs font-semibold text-blue-600 hover:text-blue-700">
                Orders <i class="pi pi-arrow-right text-[10px]"></i>
              </a>
            </div>

            @let lg = logistics();
            @if (lg) {
              <p class="text-4xl font-bold" [class]="logisticsValueColor()">
                {{ lg.rolling_90d_avg_pct | number: '1.1-1' }}%
              </p>
              <p class="mt-1 text-xs text-slate-400">90-day rolling average</p>

              <!-- Status badge -->
              <div class="mt-3 flex items-center gap-2">
                <span class="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold" [class]="logisticsBadgeClass()">
                  <i class="pi" [class]="lg.status === 'healthy' ? 'pi-check-circle' : 'pi-exclamation-triangle'"></i>
                  {{ lg.status === 'healthy' ? 'Within target' : lg.status === 'amber' ? 'Watch closely' : 'Above limit' }}
                </span>
              </div>

              <!-- Threshold guide -->
              <div class="mt-4 space-y-1.5">
                <div class="flex items-center justify-between text-xs">
                  <span class="flex items-center gap-1 text-green-600"><span class="h-1.5 w-1.5 rounded-full bg-green-500"></span> Target</span>
                  <span class="font-medium text-slate-600">&lt; {{ lg.amber_threshold_pct }}%</span>
                </div>
                <div class="flex items-center justify-between text-xs">
                  <span class="flex items-center gap-1 text-amber-600"><span class="h-1.5 w-1.5 rounded-full bg-amber-400"></span> Caution</span>
                  <span class="font-medium text-slate-600">{{ lg.amber_threshold_pct }}–{{ lg.red_threshold_pct }}%</span>
                </div>
                <div class="flex items-center justify-between text-xs">
                  <span class="flex items-center gap-1 text-red-600"><span class="h-1.5 w-1.5 rounded-full bg-red-500"></span> High</span>
                  <span class="font-medium text-slate-600">&gt; {{ lg.red_threshold_pct }}%</span>
                </div>
              </div>
            } @else {
              <div class="space-y-2">
                <div class="h-10 w-24 rounded skeleton"></div>
                <div class="h-4 w-32 rounded skeleton"></div>
              </div>
            }
          </div>

          <!-- Low Stock Alerts -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-red-50">
                  <i class="pi pi-exclamation-triangle text-lg text-red-500"></i>
                </div>
                <div>
                  <p class="font-semibold text-slate-800">Stock Levels</p>
                  <p class="text-xs text-slate-400">Products running low</p>
                </div>
              </div>
              <a routerLink="/inventory" class="text-xs font-semibold text-blue-600 hover:text-blue-700">
                Inventory <i class="pi pi-arrow-right text-[10px]"></i>
              </a>
            </div>
            @if (data().lowStockCount === 0) {
              <div class="flex items-center gap-3 rounded-xl bg-green-50 p-4">
                <i class="pi pi-check-circle text-xl text-green-600"></i>
                <div>
                  <p class="font-medium text-green-700">All stock levels healthy</p>
                  <p class="text-xs text-green-600">No products need restocking</p>
                </div>
              </div>
            } @else {
              <div class="flex items-center gap-4 rounded-xl bg-red-50 p-4">
                <div class="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl bg-red-100">
                  <span class="text-2xl font-bold text-red-600">{{ data().lowStockCount }}</span>
                </div>
                <div>
                  <p class="font-semibold text-red-700">{{ data().lowStockCount }} product{{ data().lowStockCount !== 1 ? 's' : '' }} low</p>
                  <p class="text-xs text-red-500">Check inventory and restock soon</p>
                </div>
              </div>
            }
          </div>

          <!-- AI Smart Suggestions -->
          <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-indigo-50">
                  <i class="pi pi-sparkles text-lg text-indigo-600"></i>
                </div>
                <div>
                  <p class="font-semibold text-slate-800">Smart Suggestions</p>
                  <p class="text-xs text-slate-400">AI-powered business tips</p>
                </div>
              </div>
              <a routerLink="/recommendations" class="text-xs font-semibold text-blue-600 hover:text-blue-700">
                View all <i class="pi pi-arrow-right text-[10px]"></i>
              </a>
            </div>
            @if (data().recommendations.length === 0) {
              <div class="flex items-center gap-3 rounded-xl bg-slate-50 p-4">
                <i class="pi pi-check-circle text-xl text-slate-400"></i>
                <p class="text-sm text-slate-500">No new suggestions right now.</p>
              </div>
            } @else {
              <div class="space-y-2">
                @for (rec of data().recommendations; track rec.id) {
                  <div class="flex items-start gap-3 rounded-xl border border-gray-100 p-3 transition-colors hover:bg-slate-50">
                    <span class="mt-0.5 flex-shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide" [class]="priorityClass(rec.priority)">
                      {{ rec.priority }}
                    </span>
                    <div class="min-w-0">
                      <p class="truncate text-sm font-medium text-slate-800">{{ rec.title }}</p>
                      <p class="truncate text-xs text-slate-400">{{ rec.category }}</p>
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
  private readonly fxService = inject(FxService);
  private readonly cashflowService = inject(CashflowService);
  private readonly ordersService = inject(OrdersService);
  private readonly kpiService = inject(DashboardKpiService);
  private readonly locationsService = inject(LocationsService);
  private readonly authService = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly kpiTrigger$ = new Subject<{
    locationId: string | null;
    dateFrom: string | null;
    dateTo: string | null;
  }>();

  // KPI banner
  kpi = signal<DashboardKpiSummary | null>(null);
  kpiLoading = signal(false);
  kpiError = signal(false);

  // Filters
  userName = signal('');
  locationOptions = signal<{ label: string; value: string | null }[]>([{ label: 'All locations', value: null }]);
  selectedLocationId: string | null = null;
  dateRange: Date[] = (() => { const t = new Date(); return [t, t]; })();

  // FX live rate (header chip)
  liveRate = signal<number | null>(null);

  // Dashboard data (loaded in parallel)
  loading = signal(true);
  data = signal<DashboardData>({
    liquidity: { runway_months: 0, dscr: 0, risk_rating: 'UNKNOWN' },
    ordersSummary: { total_orders: 0, total_value: '0', by_status: {}, active_orders: 0 },
    profitMargin: { blended_margin: 0, target_margin: 35, margin_gap: -35 },
    lowStockCount: 0,
    recommendations: [],
  });

  // Three restored widgets (loaded independently so one failure doesn't block others)
  fxExposure = signal<FxExposureEntry[]>([]);
  globalExposure = signal<GlobalExposure | null>(null);
  logistics = signal<LogisticsEfficiency | null>(null);

  // ---- Computed sub-lines -----------------------------------------------

  sellReturnSubLines = computed<KpiSubLine[]>(() => {
    const k = this.kpi();
    return [
      { label: 'Total returned', value: k?.total_sell_return ?? '0.00' },
      { label: 'Amount paid back', value: k?.total_sell_return_paid ?? '0.00' },
    ];
  });

  purchaseReturnSubLines = computed<KpiSubLine[]>(() => {
    const k = this.kpi();
    return [
      { label: 'Total returned', value: k?.total_purchase_return ?? '0.00' },
      { label: 'Amount refunded', value: k?.total_purchase_return_paid ?? '0.00' },
    ];
  });

  // ---- Cash Health helpers -----------------------------------------------

  dscrColor(): string {
    const d = this.data().liquidity.dscr;
    return d >= 1.5 ? 'text-green-600' : d >= 1.0 ? 'text-amber-600' : 'text-red-600';
  }

  riskBadgeClass(): string {
    const r = this.data().liquidity.risk_rating;
    return r === 'LOW' ? 'bg-green-50 text-green-700' : r === 'MEDIUM' ? 'bg-amber-50 text-amber-700' : r === 'HIGH' ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-500';
  }

  riskLabel(): string {
    const r = this.data().liquidity.risk_rating;
    return r === 'LOW' ? 'Healthy' : r === 'MEDIUM' ? 'Caution' : r === 'HIGH' ? 'At Risk' : 'Unknown';
  }

  // ---- Profit Margin helpers ---------------------------------------------

  marginColor(): string {
    const { blended_margin, target_margin } = this.data().profitMargin;
    return blended_margin >= target_margin ? 'text-green-600' : blended_margin >= target_margin * 0.8 ? 'text-amber-600' : 'text-red-600';
  }

  marginGapColor(): string {
    return this.data().profitMargin.margin_gap >= 0 ? 'text-green-500' : 'text-red-500';
  }

  marginBarWidth(): number {
    const { blended_margin, target_margin } = this.data().profitMargin;
    return Math.min((blended_margin / (target_margin || 35)) * 100, 100);
  }

  // ---- Logistics helpers -------------------------------------------------

  logisticsIconBg(): string {
    const s = this.logistics()?.status;
    return s === 'red' ? 'bg-red-50' : s === 'amber' ? 'bg-amber-50' : 'bg-green-50';
  }

  logisticsIconColor(): string {
    const s = this.logistics()?.status;
    return s === 'red' ? 'text-red-600' : s === 'amber' ? 'text-amber-600' : 'text-green-600';
  }

  logisticsValueColor(): string {
    const s = this.logistics()?.status;
    return s === 'red' ? 'text-red-600' : s === 'amber' ? 'text-amber-600' : 'text-green-600';
  }

  logisticsBadgeClass(): string {
    const s = this.logistics()?.status;
    return s === 'red' ? 'bg-red-100 text-red-700' : s === 'amber' ? 'bg-amber-100 text-amber-700' : 'bg-green-100 text-green-700';
  }

  // ---- AI Suggestions helpers --------------------------------------------

  priorityClass(priority: string): string {
    return priority === 'HIGH' ? 'bg-red-100 text-red-700' : priority === 'MEDIUM' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700';
  }

  // ---- KPI filter logic --------------------------------------------------

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

  onLocationChange(): void { this.loadKpi(); }

  onDateChange(): void {
    if (!this.dateRange[1]) {
      if (this.dateRange.length === 0) {
        const today = new Date();
        this.dateRange = [today, today];
      } else {
        return;
      }
    }
    this.loadKpi();
  }

  // ---- Lifecycle ---------------------------------------------------------

  ngOnInit(): void {
    // Debounced KPI pipeline (filter changes)
    this.kpiTrigger$
      .pipe(
        debounceTime(300),
        switchMap(({ locationId, dateFrom, dateTo }) => {
          this.kpiLoading.set(true);
          this.kpiError.set(false);
          return this.kpiService.getSummary(locationId, dateFrom, dateTo).pipe(
            catchError(() => { this.kpiLoading.set(false); this.kpiError.set(true); return EMPTY; }),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((d) => { this.kpi.set(d); this.kpiLoading.set(false); });

    // Initial KPI load (bypass debounce for first paint)
    this.kpiLoading.set(true);
    this.kpiService.getSummary(null, this.toLocalDateString(this.dateRange[0]), this.toLocalDateString(this.dateRange[1]))
      .pipe(takeUntilDestroyed(this.destroyRef), catchError(() => { this.kpiLoading.set(false); this.kpiError.set(true); return EMPTY; }))
      .subscribe((d) => { this.kpi.set(d); this.kpiLoading.set(false); });

    // User display name
    this.authService.checkSession().subscribe({
      next: (u) => { if (u) this.userName.set(u.full_name?.split(' ')?.[0] ?? ''); },
    });

    // Location filter options
    this.locationsService.getAll(undefined, true).subscribe({
      next: (res) => {
        this.locationOptions.set([
          { label: 'All locations', value: null },
          ...res.items.map((l: Location) => ({ label: l.name, value: l.id })),
        ]);
      },
    });

    // Core dashboard data (cash health, orders, margin, low stock, AI)
    this.dashboardService.loadDashboard().subscribe({
      next: (d) => { this.data.set(d); this.loading.set(false); },
      error: () => this.loading.set(false),
    });

    // Live FX rate (header chip)
    this.fxService.getLiveRate().subscribe({
      next: (r) => this.liveRate.set(r.usd_ngn),
      error: () => {},
    });

    // FX Exposure — locked vs floating per currency pair
    this.fxService.getExposureSummary().subscribe({
      next: (d) => this.fxExposure.set(d),
      error: () => {},
    });

    // Global Exposure — multi-currency debt overview
    this.cashflowService.getGlobalExposure().subscribe({
      next: (d) => this.globalExposure.set(d),
      error: () => {},
    });

    // Logistics Efficiency — shipping cost % of order value (90-day rolling)
    this.ordersService.getLogisticsEfficiency().subscribe({
      next: (d) => this.logistics.set(d),
      error: () => {},
    });
  }
}

