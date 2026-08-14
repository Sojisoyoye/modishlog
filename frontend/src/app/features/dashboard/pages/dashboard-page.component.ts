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
    <div class="flex flex-col gap-5">

      <!-- ============================================================
           Global filters — affect all data on this page
           ============================================================ -->
      <div class="flex flex-col gap-2 rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm sm:flex-row sm:flex-wrap sm:items-center sm:gap-3" data-testid="dashboard-filter-bar">
        <span class="text-xs font-medium text-muted">Filter period:</span>
        <p-select
          [options]="locationOptions()"
          [(ngModel)]="selectedLocationId"
          optionLabel="label"
          optionValue="value"
          placeholder="All locations"
          [showClear]="true"
          styleClass="w-full sm:w-48"
          (onChange)="onLocationChange()"
          ariaLabel="Select location"
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
          styleClass="w-full sm:w-auto"
          ariaLabel="Select date range"
          inputId="dashboard-date-range"
        >
          <ng-template pTemplate="inputicon" let-clickCallBack="clickCallBack">
            <i class="pi pi-calendar cursor-pointer" (click)="clickCallBack($event)"></i>
          </ng-template>
        </p-datepicker>
        @if (liveRate() !== null) {
          <div class="ml-auto flex items-center gap-1.5 text-sm text-muted">
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500"></span>
            <span>$1 = ₦{{ liveRate()! | number: '1.0-0' }}</span>
          </div>
        }
      </div>

      <!-- ============================================================
           Hero row — Today's Revenue | Net Profit | Sales Today | Unpaid Sales
           ============================================================ -->
      <div aria-live="polite" aria-atomic="true">
      <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">

        <!-- Today's Revenue — emerald hero card -->
        <div class="flex flex-col justify-between rounded-2xl bg-emerald-600 p-6 text-white shadow-sm" data-testid="hero-revenue-card">
          <div>
            <p class="text-sm font-medium text-emerald-100">{{ isToday() ? "Today's Revenue" : 'Period Revenue' }}</p>
            @if (kpiLoading()) {
              <div class="mt-2 h-10 w-32 animate-pulse rounded bg-emerald-500"></div>
            } @else {
              <p class="mt-2 text-4xl font-bold tracking-tight">
                ₦{{ kpi()?.total_sales ?? '0.00' | number: '1.0-0' }}
              </p>
            }
          </div>
          @if (isToday()) {
            <p class="mt-4 flex items-center gap-1.5 text-sm font-medium" [class]="revenueChangeClass()">
              <i [class]="revenueChangeIcon()"></i>
              {{ revenueChangePct() }}% vs yesterday
            </p>
          } @else {
            <p class="mt-4 text-sm text-emerald-200">Filtered period total</p>
          }
        </div>

        <!-- Net Profit -->
        <div class="flex flex-col justify-between rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
          <div>
            <p class="text-sm font-medium text-muted">Net Profit</p>
            @if (kpiLoading()) {
              <div class="mt-2 h-10 w-24 animate-pulse rounded bg-gray-100"></div>
            } @else {
              <p class="mt-2 text-4xl font-bold tracking-tight text-gray-900">
                ₦{{ kpi()?.net ?? '0.00' | number: '1.0-0' }}
              </p>
            }
          </div>
          <p class="mt-4 text-sm text-muted">after all costs</p>
        </div>

        <!-- Sales Today -->
        <div class="flex flex-col justify-between rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
          <div>
            <p class="text-sm font-medium text-muted">{{ isToday() ? 'Sales Today' : 'Period Sales' }}</p>
            @if (kpiLoading()) {
              <div class="mt-2 h-10 w-16 animate-pulse rounded bg-gray-100"></div>
            } @else {
              <p class="mt-2 text-4xl font-bold tracking-tight text-gray-900">
                {{ kpi()?.transaction_count ?? 0 }}
              </p>
            }
          </div>
          <p class="mt-4 text-sm text-muted">transactions</p>
        </div>

        <!-- Unpaid Sales -->
        <div class="flex flex-col justify-between rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
          <div>
            <p class="text-sm font-medium text-muted">Unpaid Sales</p>
            @if (kpiLoading()) {
              <div class="mt-2 h-10 w-24 animate-pulse rounded bg-gray-100"></div>
            } @else {
              <p class="mt-2 text-4xl font-bold tracking-tight text-amber-600">
                ₦{{ kpi()?.invoice_due ?? '0.00' | number: '1.0-0' }}
              </p>
            }
          </div>
          <p class="mt-4 text-sm text-muted">awaiting payment</p>
        </div>
      </div>

      <!-- ============================================================
           Recent Sales table
           ============================================================ -->
      <div class="mt-4 rounded-2xl border border-gray-100 bg-white shadow-sm">
        <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 class="text-base font-semibold text-gray-900">Recent Sales</h2>
          <a routerLink="/sales" class="text-xs font-semibold text-emerald-600 hover:text-emerald-700">
            View all <i class="pi pi-arrow-right text-[10px]"></i>
          </a>
        </div>
        @if (kpiLoading()) {
          <div class="px-6 py-4 text-center text-sm text-muted">Loading…</div>
        } @else if (!(kpi()?.recent_sales?.length)) {
          <div class="px-6 py-4 text-center text-sm text-muted">No sales recorded today yet.</div>
        } @else {
          <table class="hidden sm:table w-full text-sm">
            <thead>
              <tr class="border-b border-gray-100">
                <th class="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Product</th>
                <th class="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Qty</th>
                <th class="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Revenue</th>
                <th class="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Margin</th>
              </tr>
            </thead>
            <tbody>
              @for (sale of kpi()!.recent_sales; track $index) {
                <tr class="border-b border-gray-50 last:border-0">
                  <td class="px-6 py-3 font-medium text-gray-900">{{ sale.product_name }}</td>
                  <td class="px-6 py-3 text-right text-muted">{{ sale.quantity }}</td>
                  <td class="px-6 py-3 text-right text-gray-900">₦{{ sale.revenue | number: '1.0-0' }}</td>
                  <td class="px-6 py-3 text-right font-semibold" [class]="marginClass(sale.margin_pct)">
                    {{ sale.margin_pct !== null ? sale.margin_pct + '%' : '—' }}
                  </td>
                </tr>
              }
            </tbody>
          </table>

          <!-- Mobile stacked list (hidden sm+) -->
          <div class="block sm:hidden divide-y divide-gray-100">
            @for (sale of kpi()!.recent_sales; track $index) {
              <div class="flex items-center justify-between px-4 py-3 min-h-[44px]">
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-medium text-gray-900 truncate">{{ sale.product_name }}</p>
                  <p class="text-xs text-muted">Qty: {{ sale.quantity }}</p>
                </div>
                <div class="ml-4 text-right flex-shrink-0">
                  <p class="text-sm font-semibold text-gray-900">₦{{ sale.revenue | number: '1.0-0' }}</p>
                  <p class="text-xs font-semibold" [class]="marginClass(sale.margin_pct)">
                    {{ sale.margin_pct !== null ? sale.margin_pct + '%' : '—' }}
                  </p>
                </div>
              </div>
            }
          </div>
        }
      </div>
      </div><!-- /aria-live: hero KPI row + recent sales -->

      <!-- ============================================================
           KPI Cards — 5 business metrics: Money Out + Returns
           ============================================================ -->
      <div aria-live="polite" aria-atomic="true">
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">

        <!-- Money Out -->
        <button type="button" class="col-span-1 sm:col-span-2 lg:col-span-3 flex w-full items-center gap-2 border-b border-gray-100 pb-2 pt-1 text-left" [attr.aria-expanded]="moneyOutOpen()" (click)="moneyOutOpen.set(!moneyOutOpen())">
          <i class="pi text-gray-500 text-sm" [class]="moneyOutOpen() ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
          <span class="text-xs font-semibold uppercase tracking-widest text-gray-500">Money Out</span>
        </button>
        @if (moneyOutOpen()) {
          <app-kpi-card label="Total Purchased"    iconClass="pi pi-shopping-bag" colorScheme="blue"   [value]="kpi()?.total_purchase        ?? '0.00'" [loading]="kpiLoading()" tooltipText="Total value of all purchase orders placed" />
          <app-kpi-card label="Amount Owed"        iconClass="pi pi-credit-card"  colorScheme="amber"  [value]="kpi()?.purchase_due          ?? '0.00'" [loading]="kpiLoading()" tooltipText="Outstanding balance you owe to suppliers" />
          <app-kpi-card label="Monthly Expenses"   iconClass="pi pi-minus-circle" colorScheme="purple" [value]="kpi()?.expense               ?? '0.00'" [loading]="kpiLoading()" tooltipText="Operating costs (rent, salaries, utilities, etc.)" />
        }

        <!-- Returns -->
        <button type="button" class="col-span-1 sm:col-span-2 lg:col-span-3 flex w-full items-center gap-2 border-b border-gray-100 pb-2 pt-1 text-left" [attr.aria-expanded]="returnsOpen()" (click)="returnsOpen.set(!returnsOpen())">
          <i class="pi text-gray-500 text-sm" [class]="returnsOpen() ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
          <span class="text-xs font-semibold uppercase tracking-widest text-gray-500">Returns</span>
        </button>
        @if (returnsOpen()) {
          <app-kpi-card label="Customer Returns"   iconClass="pi pi-undo"         colorScheme="red"    [value]="kpi()?.total_sell_return     ?? '0.00'" [loading]="kpiLoading()" tooltipText="Value of goods returned by customers"             [subLines]="sellReturnSubLines()" />
          <app-kpi-card label="Supplier Refunds"   iconClass="pi pi-replay"       colorScheme="red"    [value]="kpi()?.total_purchase_return ?? '0.00'" [loading]="kpiLoading()" tooltipText="Value of goods returned to suppliers"             [subLines]="purchaseReturnSubLines()" />
        }
      </div>

      @if (kpiError()) {
        <div class="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <i class="pi pi-exclamation-triangle text-red-500"></i>
          <p class="text-sm text-red-600">Could not load your business figures.</p>
          <button class="ml-auto text-xs font-semibold text-red-600 underline" (click)="loadKpi()">Retry</button>
        </div>
      }
      </div><!-- /aria-live KPI cards -->

      <!-- ============================================================
           Accordions: Stock & Purchase | Pulse Metrics | AI Suggestions
           ============================================================ -->
      @if (loading()) {
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">
          @for (i of [1,2,3]; track i) { <div class="h-44 rounded-xl skeleton"></div> }
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          @for (i of [1,2]; track i) { <div class="h-44 rounded-xl skeleton"></div> }
        </div>
        <div class="h-64 rounded-xl skeleton"></div>
        <div class="h-40 rounded-xl skeleton"></div>
      } @else {

        <!-- ── Stock & Purchase Metrics ─────────────────────────────────── -->
        <div class="space-y-3">
          <button type="button" class="flex w-full items-center gap-2 border-b border-gray-100 pb-2 pt-1 text-left" [attr.aria-expanded]="stockPurchaseOpen()" (click)="stockPurchaseOpen.set(!stockPurchaseOpen())">
            <i class="pi text-gray-500 text-sm" [class]="stockPurchaseOpen() ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
            <span class="text-xs font-semibold uppercase tracking-widest text-gray-500">Stock & Purchase Metrics</span>
          </button>
          @if (stockPurchaseOpen()) {
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-3">

              <!-- Stock Levels -->
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
                @let lsc = data().lowStockCount;
                @if (lsc === 0) {
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
                      <span class="text-2xl font-bold text-red-600">{{ lsc }}</span>
                    </div>
                    <div>
                      <p class="font-semibold text-red-700">{{ lsc }} product{{ lsc !== 1 ? 's' : '' }} low</p>
                      <p class="text-xs text-red-500">Check inventory and restock soon</p>
                    </div>
                  </div>
                }
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

              <!-- Shipping Costs -->
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
                  <div class="mt-3 flex items-center gap-2">
                    <span class="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold" [class]="logisticsBadgeClass()">
                      <i class="pi" [class]="lg.status === 'healthy' ? 'pi-check-circle' : 'pi-exclamation-triangle'"></i>
                      {{ lg.status === 'healthy' ? 'Within target' : lg.status === 'amber' ? 'Watch closely' : 'Above limit' }}
                    </span>
                  </div>
                  <p class="mt-3 text-xs text-slate-400">Target: below {{ lg.amber_threshold_pct }}% of order value</p>
                } @else {
                  <div class="space-y-2">
                    <div class="h-10 w-24 rounded skeleton"></div>
                    <div class="h-4 w-32 rounded skeleton"></div>
                  </div>
                }
              </div>

            </div>
          }
        </div>

        <!-- ── Pulse Metrics ──────────────────────────────────────────────── -->
        <div class="space-y-3">
          <button type="button" class="flex w-full items-center gap-2 border-b border-gray-100 pb-2 pt-1 text-left" [attr.aria-expanded]="pulseOpen()" (click)="pulseOpen.set(!pulseOpen())">
            <i class="pi text-gray-500 text-sm" [class]="pulseOpen() ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
            <span class="text-xs font-semibold uppercase tracking-widest text-gray-500">Pulse Metrics</span>
          </button>
          @if (pulseOpen()) {
            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">

              <!-- Margin vs Target -->
              <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <div class="mb-4 flex items-center gap-3">
                  <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-purple-50">
                    <i class="pi pi-percentage text-lg text-purple-600"></i>
                  </div>
                  <div>
                    <p class="font-semibold text-slate-800">Margin vs Target</p>
                    <p class="text-xs text-slate-400">How your margin compares to your goal</p>
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
                  <div class="h-2 rounded-full transition-all" [class]="marginColor() === 'text-green-600' ? 'bg-emerald-500' : marginColor() === 'text-red-600' ? 'bg-red-500' : 'bg-amber-500'" [style.width.%]="marginBarWidth()"></div>
                </div>
                <p class="mt-1.5 text-xs text-slate-400">Target: {{ data().profitMargin.target_margin }}%</p>
              </div>

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
                      @if (data().liquidity.runway_is_finite) {
                        {{ data().liquidity.runway_months | number: '1.1-1' }} mo
                      } @else { Profitable ✓ }
                    </span>
                  </div>
                  <div class="flex items-center justify-between">
                    <span class="text-sm text-slate-500">Profit Score (DSCR)</span>
                    <span class="text-sm font-bold" [class]="dscrColor()">
                      @if (!data().liquidity.dscr_is_finite) { Excellent }
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

            </div>

            <!-- Currency & Import Risks (full width) -->
            <div class="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <div class="mb-4 flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <div class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-sky-50">
                    <i class="pi pi-arrow-right-arrow-left text-lg text-sky-600"></i>
                  </div>
                  <div>
                    <p class="font-semibold text-slate-800">Currency & Import Risks</p>
                    <p class="text-xs text-slate-400">Your foreign currency exposure and obligations</p>
                  </div>
                </div>
                <a routerLink="/fx" class="text-xs font-semibold text-blue-600 hover:text-blue-700">
                  Manage <i class="pi pi-arrow-right text-[10px]"></i>
                </a>
              </div>

              <!-- Section 1: Open Order Exposure -->
              <p class="mb-2 text-[10px] font-semibold uppercase tracking-widest text-gray-400">Open Order Exposure</p>
              @if (fxExposure().length === 0) {
                <div class="rounded-xl bg-slate-50 p-4 text-center">
                  <i class="pi pi-info-circle mb-2 text-xl text-slate-400"></i>
                  <p class="text-sm font-medium text-slate-600">No FX exposure tracked yet</p>
                  <p class="mt-1 text-xs text-slate-400">Recorded when purchase orders include a USD/EUR component.</p>
                  <a routerLink="/orders" class="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:underline">
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

              <hr class="my-4 border-gray-100">

              <!-- Section 2: Total Obligations -->
              <p class="mb-3 text-[10px] font-semibold uppercase tracking-widest text-gray-400">Total Obligations</p>
              @let ge = globalExposure();
              @if (ge) {
                <div class="mb-4 rounded-xl bg-indigo-50 p-4">
                  <p class="text-xs font-semibold uppercase tracking-wider text-indigo-400">Total Amount Owed (₦)</p>
                  <p class="mt-1 text-2xl font-bold text-indigo-700">₦{{ ge.total_global_exposure_ngn | number: '1.0-0' }}</p>
                  <div class="mt-2 flex items-center gap-2">
                    <span class="text-xs text-indigo-500">Risk Level:</span>
                    <span class="text-xs font-bold" [class]="ge.debt_to_trade_ratio > 1.5 ? 'text-red-600' : ge.debt_to_trade_ratio > 0.8 ? 'text-amber-600' : 'text-green-600'">
                      {{ ge.debt_to_trade_ratio | number: '1.2-2' }}
                      @if (ge.debt_to_trade_ratio <= 0.8) { (Healthy) }
                      @else if (ge.debt_to_trade_ratio <= 1.5) { (Moderate) }
                      @else { (High) }
                    </span>
                  </div>
                </div>
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
          }
        </div>

        <!-- ── AI Smart Suggestions ───────────────────────────────────────── -->
        <div class="space-y-3">
          <button type="button" class="flex w-full items-center gap-2 border-b border-gray-100 pb-2 pt-1 text-left" [attr.aria-expanded]="aiOpen()" (click)="aiOpen.set(!aiOpen())">
            <i class="pi text-gray-500 text-sm" [class]="aiOpen() ? 'pi-chevron-down' : 'pi-chevron-right'"></i>
            <span class="text-xs font-semibold uppercase tracking-widest text-gray-500">AI Smart Suggestions</span>
          </button>
          @if (aiOpen()) {
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
          }
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
    liquidity: {
      runway_months: 0,
      runway_is_finite: true,
      dscr: 0,
      dscr_is_finite: true,
      risk_rating: 'UNKNOWN',
    },
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

  isToday = signal(true);
  moneyOutOpen = signal(false);
  returnsOpen = signal(false);
  stockPurchaseOpen = signal(false);
  pulseOpen = signal(false);
  aiOpen = signal(false);

  private checkIsToday(dates: Date[]): boolean {
    if (dates.length < 2 || !dates[0] || !dates[1]) return true;
    const t = new Date();
    const sameDay = (a: Date, b: Date) =>
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate();
    return sameDay(dates[0], t) && sameDay(dates[1], t);
  }

  revenueChangePct = computed(() => {
    const today = parseFloat(this.kpi()?.total_sales ?? '0');
    const yesterday = parseFloat(this.kpi()?.yesterday_sales ?? '0');
    if (yesterday === 0) return 0;
    return Math.abs(Math.round(((today - yesterday) / yesterday) * 100));
  });

  revenueChangeClass = computed(() => {
    const today = parseFloat(this.kpi()?.total_sales ?? '0');
    const yesterday = parseFloat(this.kpi()?.yesterday_sales ?? '0');
    return today >= yesterday ? 'text-emerald-200' : 'text-red-200';
  });

  revenueChangeIcon = computed(() => {
    const today = parseFloat(this.kpi()?.total_sales ?? '0');
    const yesterday = parseFloat(this.kpi()?.yesterday_sales ?? '0');
    return today >= yesterday ? 'pi pi-arrow-up text-xs' : 'pi pi-arrow-down text-xs';
  });

  marginClass(pct: string | null): string {
    if (pct === null) return 'text-muted';
    const n = parseFloat(pct);
    return n >= 30 ? 'text-emerald-600' : n >= 15 ? 'text-amber-600' : 'text-red-500';
  }

  // ---- Cash Health helpers -----------------------------------------------

  dscrColor(): string {
    const l = this.data().liquidity;
    if (!l.dscr_is_finite) return 'text-green-600';
    return l.dscr >= 1.5 ? 'text-green-600' : l.dscr >= 1.0 ? 'text-amber-600' : 'text-red-600';
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
    if (!this.dateRange?.[1]) {
      if (!this.dateRange?.length) {
        const today = new Date();
        this.dateRange = [today, today];
      } else {
        return; // user clicked first date only — wait for second
      }
    }
    this.isToday.set(this.checkIsToday(this.dateRange));
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

