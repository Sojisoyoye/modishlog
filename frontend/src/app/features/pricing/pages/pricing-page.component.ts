import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe, CurrencyPipe, DatePipe, UpperCasePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { UIChart } from 'primeng/chart';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  PricingService,
  PortfolioMarginData,
  ProductMargin,
  ElasticityRead,
  SensitivityCalcResponse,
  MixCategoryStatus,
  SellingPriceSuggestionResponse,
  ScenarioRead,
  DemandForecastDay,
  PricingOptimizerRec,
} from '../../../core/services/pricing.service';
import {
  RecommendationsService,
  Recommendation,
} from '../../../core/services/recommendations.service';
import { ProductsService, Product } from '../../../core/services/products.service';

interface CrossSubsidyItem {
  product_name: string;
  margin_pct: number;
  is_above: boolean;
}

interface SubsidyPair {
  high: CrossSubsidyItem;
  low: CrossSubsidyItem;
}

interface ElasticityEntry {
  product_id: string;
  product_name: string;
  elasticity_coefficient: number;
}

@Component({
  selector: 'app-pricing-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, CurrencyPipe, DatePipe, UpperCasePipe, Toast, UIChart, StatusBadgeComponent],
  template: `
    <p-toast />
    <div>
      <div class="mb-4">
        <h2 class="text-2xl font-bold text-text">Pricing & Margins</h2>
        <p class="mt-1 text-sm text-muted">Analyze margins and optimize pricing</p>
      </div>

      <!-- Tab bar -->
      <div class="flex gap-1 overflow-x-auto border-b border-gray-200">
        @for (tab of [
          {key: 'overview',         label: 'Overview',            icon: 'pi-home'},
          {key: 'margins',          label: 'Product Margins',     icon: 'pi-list'},
          {key: 'recommendations',  label: 'Recommendations',     icon: 'pi-sparkles'},
          {key: 'analysis',         label: 'Cross-Subsidisation', icon: 'pi-arrows-h'},
          {key: 'tools',            label: 'Tools',               icon: 'pi-calculator'},
          {key: 'demand',           label: 'Demand & Mix',        icon: 'pi-chart-line'}
        ]; track tab.key) {
          <button
            type="button"
            (click)="activeTab.set($any(tab.key))"
            [class]="activeTab() === tab.key
              ? 'whitespace-nowrap border-b-2 border-primary px-4 py-2.5 text-sm font-semibold text-primary'
              : 'whitespace-nowrap border-b-2 border-transparent px-4 py-2.5 text-sm text-muted hover:text-text'"
          >
            <i class="pi mr-1.5 text-xs" [class]="tab.icon"></i>{{ tab.label }}
          </button>
        }
      </div>

      @if (activeTab() === 'overview') {
      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Blended Margin Card -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-4 flex items-center gap-2">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <i class="pi pi-percentage text-lg text-primary"></i>
            </div>
          </div>
          <p class="text-sm font-medium text-muted">Blended Portfolio Margin</p>
          <p class="mt-2 text-4xl font-bold text-text">
            {{ marginData().blended_margin | number: '1.1-1' }}%
          </p>
          <p
            class="mt-2 text-sm font-medium"
            [class]="marginData().gap >= 0 ? 'text-success' : 'text-danger'"
          >
            @if (marginData().gap >= 0) {
              <i class="pi pi-arrow-up text-xs"></i>
              +{{ marginData().gap | number: '1.1-1' }}% above {{ marginData().target_margin }}%
              target
            } @else {
              <i class="pi pi-arrow-down text-xs"></i>
              {{ marginData().gap | number: '1.1-1' }}% below {{ marginData().target_margin }}%
              target
            }
          </p>
        </div>

        <!-- Margin Distribution Chart -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
              <i class="pi pi-chart-bar text-sm text-purple-600"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Margin Distribution</h3>
          </div>
          @if (distributionChart()) {
            <p-chart
              type="bar"
              [data]="distributionChart()!"
              [options]="barOptions"
              height="200px"
            />
          }
        </div>
      </div>

      } <!-- /overview -->

      @if (activeTab() === 'margins') {
      <!-- Per-Product Margins -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-4 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-list text-sm text-secondary"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Per-Product Margins</h3>
        </div>

        <!-- Toolbar: page-size + search -->
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2 text-sm text-muted">
            Show
            <select
              [ngModel]="marginPageSize()"
              (ngModelChange)="onMarginPageSizeChange(+$event)"
              class="rounded-lg border border-gray-300 py-1 pl-3 pr-7 text-sm focus:border-primary focus:outline-none"
            >
              <option [value]="10">10</option>
              <option [value]="20">20</option>
              <option [value]="50">50</option>
            </select>
            entries
          </div>

          <div class="relative ml-auto">
            <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted"></i>
            <input
              type="text"
              placeholder="Search product..."
              [ngModel]="marginSearch()"
              (ngModelChange)="onMarginSearch($event)"
              class="w-48 rounded-lg border border-gray-300 py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none"
            />
          </div>
        </div>

        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Per-product margin analysis</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Product
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Cost
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Selling
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Margin
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Target
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">Gap</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (p of marginPagedProducts(); track p.product_id) {
                <tr
                  [class]="
                    p.gap >= 0
                      ? 'transition-colors hover:bg-gray-50/50'
                      : 'bg-red-50/50 hover:bg-red-50'
                  "
                >
                  <td class="px-4 py-3 font-medium text-text">{{ p.product_name }}</td>
                  <td class="px-4 py-3 text-right text-muted">
                    {{ p.cost_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    {{ p.selling_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right font-semibold">
                    {{ p.current_margin | number: '1.1-1' }}%
                  </td>
                  <td class="px-4 py-3 text-right text-muted">
                    {{ p.target_margin | number: '1.1-1' }}%
                  </td>
                  <td
                    class="px-4 py-3 text-right font-bold"
                    [class]="p.gap >= 0 ? 'text-success' : 'text-danger'"
                  >
                    {{ p.gap >= 0 ? '+' : '' }}{{ p.gap | number: '1.1-1' }}%
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6" class="px-4 py-10 text-center text-muted">
                    <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                    @if (marginSearch()) {
                      No products match "{{ marginSearch() }}"
                    } @else {
                      No pricing data available
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <!-- Pagination bar -->
        @if (marginTotal() > 0) {
          <div class="mt-4 flex items-center justify-between text-sm text-muted">
            <span
              >Showing {{ marginShowingFrom() }}–{{ marginShowingTo() }} of {{ marginTotal() }}
              products</span
            >
            <div class="flex items-center gap-1">
              <button
                type="button"
                (click)="marginGoToPage(marginPage() - 1)"
                [disabled]="marginPage() === 1"
                class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
              >
                <i class="pi pi-chevron-left text-xs"></i>
              </button>
              @for (n of marginPageNumbers(); track n) {
                <button
                  type="button"
                  (click)="marginGoToPage(n)"
                  [class]="
                    n === marginPage()
                      ? 'rounded bg-primary px-2.5 py-1 text-xs font-semibold text-white'
                      : 'rounded px-2.5 py-1 text-xs hover:bg-gray-100'
                  "
                >
                  {{ n }}
                </button>
              }
              <button
                type="button"
                (click)="marginGoToPage(marginPage() + 1)"
                [disabled]="marginPage() === marginTotalPages()"
                class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
              >
                <i class="pi pi-chevron-right text-xs"></i>
              </button>
            </div>
          </div>
        }
      </div>

      } <!-- /margins -->

      @if (activeTab() === 'recommendations') {
      <!-- Pricing Recommendations -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
            <i class="pi pi-sparkles text-sm text-warning"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Pricing Recommendations</h3>
          <button
            type="button"
            (click)="refreshPricingRecs()"
            [disabled]="recsGenerating()"
            class="ml-auto flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:opacity-50"
          >
            <i class="pi text-xs" [class]="recsGenerating() ? 'pi-spinner pi-spin' : 'pi-refresh'"></i>
            {{ recsGenerating() ? 'Generating…' : 'Refresh' }}
          </button>
        </div>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          @for (rec of pricingRecs(); track rec.id) {
            <div class="rounded-xl border border-gray-200 p-4 transition-shadow hover:shadow-md">
              <!-- Header: priority badge + product count chip -->
              <div class="mb-2 flex items-center justify-between">
                <app-status-badge
                  [label]="rec.priority | uppercase"
                  [status]="rec.priority === 'high' ? 'danger' : rec.priority === 'medium' ? 'warning' : 'info'"
                />
                @if ($any(rec.action_payload)?.['count']) {
                  <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold text-muted">
                    {{ $any(rec.action_payload)['count'] }} product{{ $any(rec.action_payload)['count'] !== 1 ? 's' : '' }}
                  </span>
                }
              </div>

              <!-- Category title + avg gap -->
              <h4 class="text-sm font-semibold text-text">
                {{ $any(rec.action_payload)?.['category_name'] ?? rec.title }}
              </h4>
              <p class="mt-0.5 text-xs text-muted">
                Avg margin gap:
                <span class="font-semibold text-danger">{{ $any(rec.action_payload)?.['avg_gap'] }}%</span>
              </p>

              <!-- Top 3 products preview -->
              @if ($any(rec.action_payload)?.['products']?.length) {
                <div class="mt-2 space-y-1 border-t border-gray-100 pt-2">
                  @for (p of $any(rec.action_payload)['products'].slice(0, 3); track p.product_id) {
                    <div class="flex items-center justify-between text-xs">
                      <span class="truncate text-text" style="max-width:55%">{{ p.product_name }}</span>
                      <span class="text-muted">
                        {{ p.current_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                        <i class="pi pi-arrow-right mx-0.5 text-[9px]"></i>
                        <span class="font-semibold text-success">{{ p.suggested_price | currency: 'NGN' : 'symbol' : '1.0-0' }}</span>
                      </span>
                    </div>
                  }
                  @if ($any(rec.action_payload)['products'].length > 3) {
                    <p class="text-xs text-muted">
                      and {{ $any(rec.action_payload)['products'].length - 3 }} more…
                    </p>
                  }
                </div>
              }

              <!-- Actions -->
              <div class="mt-3 flex gap-2">
                <button
                  (click)="applyRec(rec.id)"
                  class="flex items-center gap-1 rounded-lg bg-success px-3 py-1.5 text-xs font-semibold text-white transition-all hover:bg-success/90"
                >
                  <i class="pi pi-check text-[10px]"></i> Mark Reviewed
                </button>
                <button
                  (click)="dismissRec(rec.id)"
                  class="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
                >
                  Dismiss
                </button>
              </div>
            </div>
          } @empty {
            <div class="col-span-2 py-8 text-center">
              <i class="pi pi-sparkles mb-2 block text-2xl text-gray-300"></i>
              <p class="text-sm text-muted">No recommendations yet.</p>
              <p class="mt-1 text-xs text-muted">
                Click <span class="font-medium">Refresh</span> to generate AI pricing suggestions for below-target products.
              </p>
            </div>
          }
        </div>
      </div>

      } <!-- /recommendations part 1 -->

      @if (activeTab() === 'analysis') {
      <!-- Cross-Subsidisation Display (Task 32) -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-4 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50">
            <i class="pi pi-arrows-h text-sm text-orange-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Cross-Subsidisation</h3>
        </div>

        <!-- Insight block -->
        @if (subsidyInsight(); as insight) {
          <div
            class="mb-4 rounded-lg border px-4 py-3"
            [class]="
              insight.level === 'high'
                ? 'border-red-200 bg-red-50'
                : insight.level === 'medium'
                  ? 'border-amber-200 bg-amber-50'
                  : 'border-green-200 bg-green-50'
            "
          >
            <div class="mb-2 flex items-center gap-2">
              <i
                class="pi text-sm"
                [class]="
                  insight.level === 'high'
                    ? 'pi-exclamation-triangle text-red-600'
                    : insight.level === 'medium'
                      ? 'pi-exclamation-circle text-amber-600'
                      : 'pi-check-circle text-green-600'
                "
              ></i>
              <span
                class="text-xs font-semibold uppercase"
                [class]="
                  insight.level === 'high'
                    ? 'text-red-700'
                    : insight.level === 'medium'
                      ? 'text-amber-700'
                      : 'text-green-700'
                "
              >
                {{
                  insight.level === 'high'
                    ? 'High Concentration Risk'
                    : insight.level === 'medium'
                      ? 'Moderate Risk — Action Recommended'
                      : 'Portfolio Well-Balanced'
                }}
              </span>
              <div class="ml-auto flex items-center gap-2">
                <span class="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700"
                  >{{ insight.aboveCount }} above target</span
                >
                <span class="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700"
                  >{{ insight.belowCount }} below target</span
                >
              </div>
            </div>
            <p class="mb-1 text-xs text-gray-700">{{ insight.impact }}</p>
            <p class="text-xs font-medium text-gray-800">
              <i class="pi pi-arrow-right mr-1 text-xs"></i>{{ insight.action }}
            </p>
          </div>
        }

        <!-- Toolbar: page-size + search -->
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-2 text-sm text-muted">
            Show
            <select
              [ngModel]="subsidyPageSize()"
              (ngModelChange)="onSubsidyPageSizeChange(+$event)"
              class="rounded-lg border border-gray-300 py-1 pl-3 pr-7 text-sm focus:border-primary focus:outline-none"
            >
              <option [value]="10">10</option>
              <option [value]="20">20</option>
              <option [value]="50">50</option>
            </select>
            entries
          </div>

          <div class="relative ml-auto">
            <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-xs text-muted"></i>
            <input
              type="text"
              placeholder="Search product..."
              [ngModel]="subsidySearch()"
              (ngModelChange)="onSubsidySearch($event)"
              class="w-48 rounded-lg border border-gray-300 py-1.5 pl-8 pr-3 text-sm focus:border-primary focus:outline-none"
            />
          </div>
        </div>

        @if (subsidyPairs().length > 0) {
          <div class="space-y-3">
            @for (pair of subsidyPagedPairs(); track pair.high.product_name + pair.low.product_name) {
              <div
                class="flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50/50 px-4 py-3"
              >
                <span
                  class="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-semibold text-green-700"
                >
                  {{ pair.high.product_name }} ({{ pair.high.margin_pct | number: '1.0-0' }}%)
                </span>
                <span class="text-xs font-medium text-muted">subsidises</span>
                <span
                  class="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700"
                >
                  {{ pair.low.product_name }} ({{ pair.low.margin_pct | number: '1.0-0' }}%)
                </span>
              </div>
            } @empty {
              <div class="py-10 text-center text-muted">
                <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                @if (subsidySearch()) {
                  No pairs match "{{ subsidySearch() }}"
                } @else {
                  No cross-subsidisation pairs found
                }
              </div>
            }
          </div>

          <!-- Pagination bar -->
          @if (subsidyTotal() > 0) {
            <div class="mt-4 flex items-center justify-between text-sm text-muted">
              <span
                >Showing {{ subsidyShowingFrom() }}–{{ subsidyShowingTo() }} of
                {{ subsidyTotal() }} pairs</span
              >
              <div class="flex items-center gap-1">
                <button
                  type="button"
                  (click)="subsidyGoToPage(subsidyPage() - 1)"
                  [disabled]="subsidyPage() === 1"
                  class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
                >
                  <i class="pi pi-chevron-left text-xs"></i>
                </button>
                @for (n of subsidyPageNumbers(); track n) {
                  <button
                    type="button"
                    (click)="subsidyGoToPage(n)"
                    [class]="
                      n === subsidyPage()
                        ? 'rounded bg-primary px-2.5 py-1 text-xs font-semibold text-white'
                        : 'rounded px-2.5 py-1 text-xs hover:bg-gray-100'
                    "
                  >
                    {{ n }}
                  </button>
                }
                <button
                  type="button"
                  (click)="subsidyGoToPage(subsidyPage() + 1)"
                  [disabled]="subsidyPage() === subsidyTotalPages()"
                  class="rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
                >
                  <i class="pi pi-chevron-right text-xs"></i>
                </button>
              </div>
            </div>
          }

        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> Not enough product data to show
            cross-subsidisation
          </p>
        }
      </div>

      <!-- Above / Below Target Breakdown Table -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-4 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50">
            <i class="pi pi-table text-sm text-orange-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Margin Target Breakdown</h3>
          <span class="ml-1 text-xs text-muted">(top 10 each side)</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full table-fixed divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Above and below target margin breakdown</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="w-2/5 px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Above Target ({{ marginData().target_margin }}%)
                </th>
                <th class="w-1/10 px-4 py-3 text-right text-xs font-semibold uppercase text-success">
                  Margin
                </th>
                <th class="w-2/5 border-l border-gray-200 px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Below Target ({{ marginData().target_margin }}%)
                </th>
                <th class="w-1/10 px-4 py-3 text-right text-xs font-semibold uppercase text-danger">
                  Margin
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (row of subsidyTableRows(); track row.idx) {
                <tr class="transition-colors hover:bg-gray-50/50">
                  <td class="truncate px-4 py-2.5 text-text">{{ row.above?.product_name ?? '' }}</td>
                  <td class="px-4 py-2.5 text-right font-semibold text-success">
                    {{ row.above ? (row.above.margin_pct | number: '1.1-1') + '%' : '' }}
                  </td>
                  <td class="truncate border-l border-gray-200 px-4 py-2.5 text-text">
                    {{ row.below?.product_name ?? '' }}
                  </td>
                  <td class="px-4 py-2.5 text-right font-semibold text-danger">
                    {{ row.below ? (row.below.margin_pct | number: '1.1-1') + '%' : '' }}
                  </td>
                </tr>
              }
            </tbody>
            @if (subsidyAboveMoreCount() > 0 || subsidyBelowMoreCount() > 0) {
              <tfoot>
                <tr class="bg-gray-50/50 text-xs text-muted">
                  <td colspan="2" class="px-4 py-2">
                    @if (subsidyAboveMoreCount() > 0) { and {{ subsidyAboveMoreCount() }} more }
                  </td>
                  <td colspan="2" class="border-l border-gray-200 px-4 py-2">
                    @if (subsidyBelowMoreCount() > 0) { and {{ subsidyBelowMoreCount() }} more }
                  </td>
                </tr>
              </tfoot>
            }
          </table>
        </div>
      </div>

      } <!-- /analysis part 1 -->

      @if (activeTab() === 'tools') {
      <!-- Price-FX Sensitivity Calculator -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-50">
            <i class="pi pi-calculator text-sm text-teal-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Price-FX Sensitivity Calculator</h3>
        </div>

        <div class="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label for="sens-selling-price" class="mb-1.5 block text-xs font-medium text-muted"
              >Selling Price (NGN)</label
            >
            <input
              id="sens-selling-price"
              type="number"
              [(ngModel)]="sensSellingPrice"
              placeholder="e.g. 5000"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="sens-fx-rate" class="mb-1.5 block text-xs font-medium text-muted"
              >FX Rate (USD→NGN)</label
            >
            <input
              id="sens-fx-rate"
              type="number"
              [(ngModel)]="sensFxRate"
              placeholder="e.g. 1550"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="sens-quantity" class="mb-1.5 block text-xs font-medium text-muted"
              >Quantity</label
            >
            <input
              id="sens-quantity"
              type="number"
              [(ngModel)]="sensQuantity"
              placeholder="e.g. 100"
              min="1"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="sens-unit-cost" class="mb-1.5 block text-xs font-medium text-muted"
              >Unit Cost USD <span class="font-normal">(optional)</span></label
            >
            <input
              id="sens-unit-cost"
              type="number"
              [(ngModel)]="sensUnitCostUsd"
              placeholder="Manual cost"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <div class="flex flex-wrap gap-3">
          <button
            (click)="calculateSensitivity()"
            [disabled]="!sensSellingPrice || !sensFxRate || !sensQuantity"
            class="flex items-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i class="pi pi-play text-sm"></i> Calculate
          </button>
          @if (sensResult()) {
            <button
              (click)="saveSensScenario()"
              class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
            >
              <i class="pi pi-save text-sm"></i> Save Scenario
            </button>
          }
        </div>

        @if (sensResult()) {
          <div class="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div class="rounded-lg bg-gray-50 p-4">
              <p class="text-xs font-medium text-muted">Landed Cost</p>
              <p class="mt-1 text-lg font-bold text-text">
                {{ sensResult()!.landed_cost_ngn | currency: 'NGN' : 'symbol' : '1.0-0' }}
              </p>
            </div>
            <div class="rounded-lg p-4" [class]="sensResult()!.margin_pct >= 35 ? 'bg-green-50' : 'bg-red-50'">
              <p class="text-xs font-medium text-muted">Margin</p>
              <p
                class="mt-1 text-lg font-bold"
                [class]="sensResult()!.margin_pct >= 35 ? 'text-success' : 'text-danger'"
              >
                {{ sensResult()!.margin_pct | number: '1.1-1' }}%
              </p>
            </div>
            <div class="rounded-lg bg-gray-50 p-4">
              <p class="text-xs font-medium text-muted">Total Revenue</p>
              <p class="mt-1 text-lg font-bold text-text">
                {{ sensResult()!.total_revenue | currency: 'NGN' : 'symbol' : '1.0-0' }}
              </p>
            </div>
            <div class="rounded-lg bg-gray-50 p-4">
              <p class="text-xs font-medium text-muted">Gross Profit</p>
              <p class="mt-1 text-lg font-bold text-text">
                {{ sensResult()!.gross_profit | currency: 'NGN' : 'symbol' : '1.0-0' }}
              </p>
            </div>
          </div>
        }
      </div>

      <!-- Selling Price Suggestion -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-50">
            <i class="pi pi-tag text-sm text-violet-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Selling Price Suggestion</h3>
        </div>
        <p class="mb-4 text-xs text-muted">
          Compute the FX-adjusted minimum selling price needed to achieve a target margin.
        </p>

        <div class="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label for="sugg-cost" class="mb-1.5 block text-xs font-medium text-muted"
              >Unit Cost</label
            >
            <input
              id="sugg-cost"
              type="number"
              [(ngModel)]="suggUnitCost"
              placeholder="e.g. 10.00"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="sugg-currency" class="mb-1.5 block text-xs font-medium text-muted"
              >Currency</label
            >
            <select
              id="sugg-currency"
              [(ngModel)]="suggCurrency"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="USD">USD</option>
              <option value="NGN">NGN</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
            </select>
          </div>
          <div>
            <label for="sugg-fx" class="mb-1.5 block text-xs font-medium text-muted"
              >FX Rate Override <span class="font-normal">(optional)</span></label
            >
            <input
              id="sugg-fx"
              type="number"
              [(ngModel)]="suggFxRate"
              placeholder="e.g. 1550"
              min="0"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="sugg-margin" class="mb-1.5 block text-xs font-medium text-muted"
              >Min Margin %</label
            >
            <input
              id="sugg-margin"
              type="number"
              [(ngModel)]="suggMinMargin"
              placeholder="35"
              min="1"
              max="99"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <button
          (click)="getSellingSuggestion()"
          [disabled]="!suggUnitCost"
          class="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <i class="pi pi-lightbulb text-sm"></i> Get Suggestion
        </button>

        @if (suggResult()) {
          <div class="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div class="rounded-lg bg-gray-50 p-4">
              <p class="text-xs font-medium text-muted">Unit Cost (NGN)</p>
              <p class="mt-1 text-lg font-bold text-text">
                {{ suggResult()!.unit_cost_ngn | currency: 'NGN' : 'symbol' : '1.0-0' }}
              </p>
              <p class="mt-0.5 text-xs text-muted">
                FX {{ suggResult()!.fx_rate | number: '1.0-0' }}
              </p>
            </div>
            <div class="rounded-lg bg-violet-50 p-4">
              <p class="text-xs font-medium text-muted">Min Selling Price</p>
              <p class="mt-1 text-xl font-bold text-violet-700">
                {{ suggResult()!.min_selling_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
              </p>
            </div>
            <div class="rounded-lg bg-gray-50 p-4">
              <p class="text-xs font-medium text-muted">Target Margin</p>
              <p class="mt-1 text-lg font-bold text-text">
                {{ suggResult()!.min_margin_pct | number: '1.1-1' }}%
              </p>
            </div>
          </div>
        }
      </div>

      } <!-- /tools part 1 -->

      @if (activeTab() === 'demand') {
      <!-- Product Mix Status -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-50">
            <i class="pi pi-chart-pie text-sm text-sky-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Product Mix Status</h3>
          <span class="ml-1 text-xs text-muted">(last 90 days vs target)</span>
        </div>
        @if (mixStatus().length > 0) {
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Product mix actual vs target</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                    Category
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    Actual
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    Target
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    Variance
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (cat of mixStatus(); track cat.category_id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-4 py-3 font-medium text-text">{{ cat.category_name }}</td>
                    <td class="px-4 py-3 text-right">{{ cat.actual_pct | number: '1.1-1' }}%</td>
                    <td class="px-4 py-3 text-right text-muted">
                      {{ cat.target_pct | number: '1.1-1' }}%
                    </td>
                    <td
                      class="px-4 py-3 text-right font-semibold"
                      [class]="
                        cat.variance_pct >= -5 && cat.variance_pct <= 5
                          ? 'text-success'
                          : 'text-danger'
                      "
                    >
                      {{ cat.variance_pct >= 0 ? '+' : ''
                      }}{{ cat.variance_pct | number: '1.1-1' }}%
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> No mix targets configured yet. Set product mix
            targets to track actual vs target revenue distribution.
          </p>
        }
      </div>

      } <!-- /demand part 1 -->

      @if (activeTab() === 'recommendations') {
      <!-- Optimizer Pricing Recommendations -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-50">
              <i class="pi pi-bolt text-sm text-rose-600"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Optimizer Recommendations</h3>
          </div>
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-2">
              <label for="opt-target-margin" class="text-xs font-medium text-muted"
                >Target %</label
              >
              <input
                id="opt-target-margin"
                type="number"
                [(ngModel)]="optimizerTargetMargin"
                min="1"
                max="99"
                class="w-20 rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
            <button
              (click)="generateOptimizerRecs()"
              [disabled]="optimizerLoading()"
              class="flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white transition-all hover:bg-rose-700 disabled:opacity-50"
            >
              <i class="pi pi-sync text-xs" [class.pi-spin]="optimizerLoading()"></i>
              {{ optimizerLoading() ? 'Generating…' : 'Generate' }}
            </button>
          </div>
        </div>

        @if (optimizerRecs().length > 0) {
          <div class="space-y-3">
            @for (rec of optimizerRecs(); track rec.id) {
              <div class="rounded-lg border border-gray-100 bg-gray-50/50 p-4">
                <div class="flex items-start justify-between gap-4">
                  <div class="min-w-0 flex-1">
                    <p class="text-xs font-medium text-muted">Product ID: {{ rec.product_id }}</p>
                    <p class="mt-1 text-sm text-text">
                      <span class="font-semibold">₦{{ rec.current_price | number: '1.0-0' }}</span>
                      <i class="pi pi-arrow-right mx-2 text-xs text-muted"></i>
                      <span class="font-bold text-primary"
                        >₦{{ rec.recommended_price | number: '1.0-0' }}</span
                      >
                      <span class="ml-2 text-xs text-muted"
                        >({{ rec.expected_margin_change_pct >= 0 ? '+' : ''
                        }}{{ rec.expected_margin_change_pct | number: '1.1-1' }}% margin)</span
                      >
                    </p>
                    <p class="mt-1 text-xs text-muted leading-relaxed">{{ rec.reasoning }}</p>
                  </div>
                  <div class="flex shrink-0 gap-2">
                    <button
                      (click)="applyOptimizerRec(rec.id)"
                      class="rounded-lg bg-success px-3 py-1.5 text-xs font-semibold text-white hover:bg-success/90"
                    >
                      Apply
                    </button>
                    <button
                      (click)="dismissOptimizerRec(rec.id)"
                      class="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted hover:bg-gray-50"
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            }
          </div>
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> No pending optimizer recommendations. Click
            Generate to run the margin optimizer.
          </p>
        }
      </div>

      } <!-- /recommendations part 2 -->

      @if (activeTab() === 'demand') {
      <!-- Demand Forecast -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
            <i class="pi pi-chart-line text-sm text-emerald-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Demand Forecast</h3>
        </div>

        <div class="mb-5 flex flex-wrap items-end gap-3">
          <div>
            <label for="forecast-product" class="mb-1.5 block text-xs font-medium text-muted"
              >Product</label
            >
            <select
              id="forecast-product"
              [(ngModel)]="forecastProductId"
              class="w-56 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="">Select product…</option>
              @for (p of products(); track p.id) {
                <option [value]="p.id">{{ p.name }}</option>
              }
            </select>
          </div>
          <div>
            <label for="forecast-horizon" class="mb-1.5 block text-xs font-medium text-muted"
              >Horizon (days)</label
            >
            <select
              id="forecast-horizon"
              [(ngModel)]="forecastHorizon"
              class="w-28 rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option [value]="30">30 days</option>
              <option [value]="60">60 days</option>
              <option [value]="90">90 days</option>
            </select>
          </div>
          <button
            (click)="runDemandForecast()"
            [disabled]="!forecastProductId || forecastLoading()"
            class="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i
              class="pi text-sm"
              [class]="forecastLoading() ? 'pi-spin pi-spinner' : 'pi-play'"
            ></i>
            {{ forecastLoading() ? 'Forecasting…' : 'Run Forecast' }}
          </button>
        </div>

        @if (forecastData()) {
          <div class="mb-4 rounded-lg bg-emerald-50 p-4">
            <p class="text-xs font-medium text-muted">Total Projected Demand ({{ forecastHorizon }} days)</p>
            <p class="mt-1 text-2xl font-bold text-emerald-700">
              {{ forecastTotalDemand() | number: '1.0-0' }} units
            </p>
          </div>
          @if (forecastChartData()) {
            <p-chart
              type="line"
              [data]="forecastChartData()!"
              [options]="forecastChartOptions"
              height="220px"
            />
          }
        } @else if (!forecastLoading()) {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> Select a product and click Run Forecast.
            Requires at least 10 days of sales history over the past 180 days.
          </p>
        }
      </div>

      } <!-- /demand part 2 -->

      @if (activeTab() === 'tools') {
      <!-- Saved Scenarios -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
              <i class="pi pi-bookmark text-sm text-amber-600"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Saved Scenarios</h3>
          </div>
          <button
            (click)="loadScenarios()"
            class="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
          >
            <i class="pi pi-refresh text-xs"></i> Refresh
          </button>
        </div>

        @if (scenarios().length > 0) {
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Saved pricing scenarios</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                    Name
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    Selling Price
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    FX Rate
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    Qty
                  </th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                    Margin
                  </th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                    Saved
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (s of scenarios(); track s.id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-4 py-3 font-medium text-text">{{ s.name }}</td>
                    <td class="px-4 py-3 text-right">
                      {{ s.selling_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                    </td>
                    <td class="px-4 py-3 text-right text-muted">
                      {{ s.fx_rate | number: '1.0-0' }}
                    </td>
                    <td class="px-4 py-3 text-right text-muted">{{ s.quantity }}</td>
                    <td class="px-4 py-3 text-right font-semibold">
                      @if (s.results && s.results['margin_pct']) {
                        {{ $any(s.results['margin_pct']) | number: '1.1-1' }}%
                      } @else {
                        —
                      }
                    </td>
                    <td class="px-4 py-3 text-xs text-muted">
                      {{ s.created_at | date: 'dd MMM yyyy HH:mm' }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-inbox mr-1 text-gray-300"></i> No saved scenarios yet. Use the
            Sensitivity Calculator above and click Save Scenario.
          </p>
        }
      </div>

      } <!-- /tools part 2 -->

      @if (activeTab() === 'demand') {
      <!-- Demand Elasticity Configuration (Task 31) -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
            <i class="pi pi-sliders-h text-sm text-indigo-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Demand Elasticity</h3>
        </div>

        <!-- Elasticity Config Form -->
        <div class="mb-5 flex flex-wrap items-end gap-3">
          <div>
            <label for="pricing-elasticity-product" class="mb-1.5 block text-xs font-medium text-muted">Product</label>
            <select
              id="pricing-elasticity-product"
              [(ngModel)]="elasticityProductId"
              class="w-52 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="">Select product...</option>
              @for (p of products(); track p.id) {
                <option [value]="p.id">{{ p.name }}</option>
              }
            </select>
          </div>
          <div>
            <label for="pricing-elasticity-coeff" class="mb-1.5 block text-xs font-medium text-muted"
              >Elasticity Coefficient</label
            >
            <input
              id="pricing-elasticity-coeff"
              type="number"
              [(ngModel)]="elasticityCoeff"
              placeholder="e.g. -1.5"
              step="0.1"
              max="0"
              class="w-40 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            (click)="updateElasticity()"
            [disabled]="!elasticityProductId || !elasticityCoeff"
            class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i class="pi pi-save text-sm"></i> Save
          </button>
          <button
            (click)="loadElasticity()"
            [disabled]="!elasticityProductId"
            class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i class="pi pi-refresh text-sm"></i> Load
          </button>
        </div>

        <!-- Elasticity List -->
        @if (elasticityEntries().length > 0) {
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Demand elasticity coefficients</caption>
              <thead>
                <tr class="bg-gray-50/80">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                    Product
                  </th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                    Coefficient
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (e of elasticityEntries(); track e.product_id) {
                  <tr class="transition-colors hover:bg-gray-50/50">
                    <td class="px-3 py-2.5 font-medium text-text">{{ e.product_name }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold">
                      {{ e.elasticity_coefficient | number: '1.2-2' }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> No elasticity data loaded yet. Select a product
            and click Load.
          </p>
        }
      </div>
      } <!-- /demand part 3 -->

    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PricingPageComponent implements OnInit {
  private readonly pricingService = inject(PricingService);
  private readonly recsService = inject(RecommendationsService);
  private readonly productsService = inject(ProductsService);
  private readonly messageService = inject(MessageService);

  activeTab = signal<'overview' | 'margins' | 'recommendations' | 'analysis' | 'tools' | 'demand'>('overview');

  marginData = signal<PortfolioMarginData>({
    blended_margin: 0,
    target_margin: 35,
    gap: -35,
    products: [],
  });

  // Per-product margins: search + pagination (client-side)
  marginSearch = signal('');
  marginPage = signal(1);
  marginPageSize = signal(20);

  private marginFilteredProducts = computed(() => {
    const q = this.marginSearch().toLowerCase().trim();
    const all = this.marginData().products;
    return q ? all.filter((p) => p.product_name.toLowerCase().includes(q)) : all;
  });

  marginTotal = computed(() => this.marginFilteredProducts().length);
  marginTotalPages = computed(() => Math.max(1, Math.ceil(this.marginTotal() / this.marginPageSize())));
  marginShowingFrom = computed(() => this.marginTotal() === 0 ? 0 : (this.marginPage() - 1) * this.marginPageSize() + 1);
  marginShowingTo = computed(() => Math.min(this.marginPage() * this.marginPageSize(), this.marginTotal()));
  marginPagedProducts = computed(() => {
    const start = (this.marginPage() - 1) * this.marginPageSize();
    return this.marginFilteredProducts().slice(start, start + this.marginPageSize());
  });
  marginPageNumbers = computed(() => {
    const total = this.marginTotalPages();
    const current = this.marginPage();
    const start = Math.max(1, current - 2);
    const end = Math.min(total, start + 4);
    const pages: number[] = [];
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  });

  pricingRecs = signal<Recommendation[]>([]);
  recsGenerating = signal(false);
  distributionChart = signal<unknown>(null);

  // Task 32: Cross-subsidisation
  aboveTarget = signal<CrossSubsidyItem[]>([]);
  belowTarget = signal<CrossSubsidyItem[]>([]);
  subsidyPairs = signal<SubsidyPair[]>([]);

  subsidySearch = signal('');
  subsidyPage = signal(1);
  subsidyPageSize = signal(20);

  private subsidyFilteredPairs = computed(() => {
    const q = this.subsidySearch().toLowerCase().trim();
    const all = this.subsidyPairs();
    return q
      ? all.filter(
          (pair) =>
            pair.high.product_name.toLowerCase().includes(q) ||
            pair.low.product_name.toLowerCase().includes(q),
        )
      : all;
  });

  subsidyTotal = computed(() => this.subsidyFilteredPairs().length);
  subsidyTotalPages = computed(() => Math.max(1, Math.ceil(this.subsidyTotal() / this.subsidyPageSize())));
  subsidyShowingFrom = computed(() =>
    this.subsidyTotal() === 0 ? 0 : (this.subsidyPage() - 1) * this.subsidyPageSize() + 1,
  );
  subsidyShowingTo = computed(() =>
    Math.min(this.subsidyPage() * this.subsidyPageSize(), this.subsidyTotal()),
  );
  subsidyPagedPairs = computed(() => {
    const start = (this.subsidyPage() - 1) * this.subsidyPageSize();
    return this.subsidyFilteredPairs().slice(start, start + this.subsidyPageSize());
  });
  subsidyPageNumbers = computed(() => {
    const total = this.subsidyTotalPages();
    const current = this.subsidyPage();
    const start = Math.max(1, current - 2);
    const end = Math.min(total, start + 4);
    const pages: number[] = [];
    for (let i = start; i <= end; i++) pages.push(i);
    return pages;
  });

  private subsidyAllAbove = computed(() => {
    const q = this.subsidySearch().toLowerCase().trim();
    return q
      ? this.aboveTarget().filter((i) => i.product_name.toLowerCase().includes(q))
      : this.aboveTarget();
  });

  private subsidyAllBelow = computed(() => {
    const q = this.subsidySearch().toLowerCase().trim();
    return q
      ? this.belowTarget().filter((i) => i.product_name.toLowerCase().includes(q))
      : this.belowTarget();
  });

  subsidyFilteredAbove = computed(() => this.subsidyAllAbove().slice(0, 10));
  subsidyAboveMoreCount = computed(() => Math.max(0, this.subsidyAllAbove().length - 10));

  subsidyFilteredBelow = computed(() => this.subsidyAllBelow().slice(0, 10));
  subsidyBelowMoreCount = computed(() => Math.max(0, this.subsidyAllBelow().length - 10));

  subsidyTableRows = computed(() => {
    const above = this.subsidyFilteredAbove();
    const below = this.subsidyFilteredBelow();
    const len = Math.max(above.length, below.length);
    return Array.from({ length: len }, (_, idx) => ({
      idx,
      above: above[idx] ?? null,
      below: below[idx] ?? null,
    }));
  });

  subsidyInsight = computed(() => {
    const above = this.aboveTarget();
    const below = this.belowTarget();
    const total = above.length + below.length;
    if (total === 0) return null;
    const ratio = above.length / total;
    const topProduct = above[0]?.product_name ?? '';
    const worstProduct = below[0]?.product_name ?? '';
    const worstMargin = below[0] != null ? below[0].margin_pct.toFixed(1) : null;
    const target = this.marginData().target_margin;
    let level: 'high' | 'medium' | 'low';
    let impact: string;
    let action: string;
    if (ratio < 0.2) {
      level = 'high';
      impact = `Only ${above.length} of your ${total} products are above the ${target}% target. If sales of these top performers slow down, your overall portfolio margin will turn negative.`;
      action = topProduct
        ? `Protect "${topProduct}" and your other top performers — do not discount them. Use the Pricing Recommendations above to close the gap on below-target products${worstProduct ? `, starting with "${worstProduct}" (${worstMargin}% margin)` : ''}.`
        : `Do not discount your top-margin products. Address below-target pricing urgently using the Pricing Recommendations above.`;
    } else if (ratio < 0.5) {
      level = 'medium';
      impact = `${above.length} products are subsidising ${below.length} others. Your margin is healthy overall, but you are depending on a minority of products to carry the portfolio.`;
      action = worstProduct
        ? `Avoid discounting your high-margin products — they are doing the heavy lifting. Your biggest drag is "${worstProduct}" at ${worstMargin}% margin; see Pricing Recommendations above for a suggested price to close that gap.`
        : `Avoid discounting your top-margin products. Use Pricing Recommendations above to address the ${below.length} below-target products.`;
    } else {
      level = 'low';
      impact = `${above.length} of your ${total} products are above the ${target}% target — margin is well-spread across your portfolio, reducing reliance on any single product.`;
      action = below.length > 0
        ? `Portfolio risk is low. Keep an eye on cost price increases for the ${below.length} below-target products${worstProduct ? ` — "${worstProduct}" (${worstMargin}%) is the closest to becoming a drag` : ''}.`
        : `All active products are meeting the margin target. Watch for cost price changes that could shift this.`;
    }
    return { level, impact, action, aboveCount: above.length, belowCount: below.length, topProduct, worstProduct };
  });

  // Task 31: Demand elasticity
  products = signal<Product[]>([]);
  elasticityEntries = signal<ElasticityEntry[]>([]);
  elasticityProductId = '';
  elasticityCoeff = 0;

  // Sensitivity calculator
  sensSellingPrice = 0;
  sensFxRate = 0;
  sensQuantity = 1;
  sensUnitCostUsd = 0;
  sensResult = signal<SensitivityCalcResponse | null>(null);

  // Selling price suggestion
  suggUnitCost = 0;
  suggCurrency = 'USD';
  suggFxRate = 0;
  suggMinMargin = 35;
  suggResult = signal<SellingPriceSuggestionResponse | null>(null);

  // Product mix status
  mixStatus = signal<MixCategoryStatus[]>([]);

  // Optimizer recommendations
  optimizerRecs = signal<PricingOptimizerRec[]>([]);
  optimizerTargetMargin = 35;
  optimizerLoading = signal(false);

  // Demand forecast
  forecastProductId = '';
  forecastHorizon = 90;
  forecastData = signal<DemandForecastDay[] | null>(null);
  forecastTotalDemand = signal(0);
  forecastChartData = signal<unknown>(null);
  forecastLoading = signal(false);

  readonly forecastChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { maxTicksLimit: 8 } },
      y: { beginAtZero: true, title: { display: true, text: 'Units' } },
    },
  };

  // Saved scenarios
  scenarios = signal<ScenarioRead[]>([]);

  readonly barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, title: { display: true, text: 'Products' } },
      x: { grid: { display: false } },
    },
  };

  ngOnInit(): void {
    this.pricingService.getPortfolioMargin().subscribe({
      next: (d) => {
        this.marginData.set(d);
        this.buildDistribution(d.products);
        this.buildCrossSubsidy(d);
      },
    });
    this.recsGenerating.set(true);
    this.recsService.generate().subscribe({
      next: () => {
        this.recsService.getAll({ category: 'PRICING' }).subscribe({
          next: (r) => {
            this.pricingRecs.set(r.items.filter((i) => i.status === 'pending'));
            this.recsGenerating.set(false);
          },
        });
      },
      error: () => this.recsGenerating.set(false),
    });
    this.productsService.getAll().subscribe({
      next: (p) => this.products.set(p),
    });
    this.pricingService.getMixStatus().subscribe({
      next: (r) => this.mixStatus.set(r.categories),
    });
    this.pricingService.getOptimizerRecs().subscribe({
      next: (r) => this.optimizerRecs.set(r),
    });
    this.loadScenarios();
  }

  private buildDistribution(products: ProductMargin[]): void {
    const buckets = ['0-10%', '10-20%', '20-30%', '30-40%', '40%+'];
    const counts = [0, 0, 0, 0, 0];
    for (const p of products) {
      const m = p.current_margin;
      if (m < 10) counts[0]++;
      else if (m < 20) counts[1]++;
      else if (m < 30) counts[2]++;
      else if (m < 40) counts[3]++;
      else counts[4]++;
    }
    this.distributionChart.set({
      labels: buckets,
      datasets: [
        {
          label: 'Products',
          data: counts,
          backgroundColor: ['#C0392B', '#D97706', '#2E75B6', '#1A7A4A', '#1F4E79'],
          borderRadius: 6,
        },
      ],
    });
  }

  refreshPricingRecs(): void {
    this.recsGenerating.set(true);
    this.recsService.generate().subscribe({
      next: () => {
        this.recsService.getAll({ category: 'PRICING' }).subscribe({
          next: (r) => {
            this.pricingRecs.set(r.items.filter((i) => i.status === 'pending'));
            this.recsGenerating.set(false);
            this.messageService.add({
              severity: 'success',
              summary: 'Refreshed',
              detail: `${this.pricingRecs().length} pricing recommendation(s) ready`,
            });
          },
        });
      },
      error: () => {
        this.recsGenerating.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Could not generate recommendations' });
      },
    });
  }

  applyRec(id: string): void {
    this.recsService.apply(id).subscribe({
      next: () => {
        this.pricingRecs.update((recs) => recs.filter((r) => r.id !== id));
        this.messageService.add({
          severity: 'success',
          summary: 'Applied',
          detail: 'Recommendation applied',
        });
      },
    });
  }

  dismissRec(id: string): void {
    this.recsService.dismiss(id, 'Dismissed from pricing page').subscribe({
      next: () => {
        this.pricingRecs.update((recs) => recs.filter((r) => r.id !== id));
        this.messageService.add({
          severity: 'info',
          summary: 'Dismissed',
          detail: 'Recommendation dismissed',
        });
      },
    });
  }

  // Task 32: Cross-subsidisation computation
  private buildCrossSubsidy(data: PortfolioMarginData): void {
    const target = data.target_margin;
    const above: CrossSubsidyItem[] = [];
    const below: CrossSubsidyItem[] = [];

    for (const p of data.products) {
      const item: CrossSubsidyItem = {
        product_name: p.product_name,
        margin_pct: p.current_margin,
        is_above: p.current_margin >= target,
      };
      if (item.is_above) {
        above.push(item);
      } else {
        below.push(item);
      }
    }

    above.sort((a, b) => b.margin_pct - a.margin_pct);
    below.sort((a, b) => a.margin_pct - b.margin_pct);

    this.aboveTarget.set(above);
    this.belowTarget.set(below);

    // Build pairs: each high-margin product "subsidises" each low-margin product
    const pairs: SubsidyPair[] = [];
    for (const high of above) {
      for (const low of below) {
        pairs.push({ high, low });
      }
    }
    this.subsidyPairs.set(pairs);
  }

  // Task 31: Demand elasticity
  loadElasticity(): void {
    if (!this.elasticityProductId) return;
    const product = this.products().find((p) => p.id === this.elasticityProductId);
    this.pricingService.getElasticity(this.elasticityProductId).subscribe({
      next: (e) => {
        const entry: ElasticityEntry = {
          product_id: e.product_id,
          product_name: product?.name ?? 'Unknown',
          elasticity_coefficient: Number(e.elasticity_coefficient),
        };
        this.elasticityEntries.update((list) => {
          const filtered = list.filter((x) => x.product_id !== e.product_id);
          return [...filtered, entry];
        });
        this.elasticityCoeff = Number(e.elasticity_coefficient);
      },
      error: () => {
        this.messageService.add({
          severity: 'warn',
          summary: 'Not Found',
          detail: 'No elasticity data for this product',
        });
      },
    });
  }

  updateElasticity(): void {
    if (!this.elasticityProductId || !this.elasticityCoeff) return;
    const product = this.products().find((p) => p.id === this.elasticityProductId);
    this.pricingService
      .updateElasticity(this.elasticityProductId, {
        elasticity_coefficient: this.elasticityCoeff,
      })
      .subscribe({
        next: (e) => {
          const entry: ElasticityEntry = {
            product_id: e.product_id,
            product_name: product?.name ?? 'Unknown',
            elasticity_coefficient: Number(e.elasticity_coefficient),
          };
          this.elasticityEntries.update((list) => {
            const filtered = list.filter((x) => x.product_id !== e.product_id);
            return [...filtered, entry];
          });
          this.messageService.add({
            severity: 'success',
            summary: 'Saved',
            detail: `Elasticity updated for ${product?.name ?? 'product'}`,
          });
        },
        error: () => {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to update elasticity',
          });
        },
      });
  }

  calculateSensitivity(): void {
    if (!this.sensSellingPrice || !this.sensFxRate || !this.sensQuantity) return;
    const body: Record<string, unknown> = {
      selling_price_override: this.sensSellingPrice,
      fx_rate_override: this.sensFxRate,
      quantity: this.sensQuantity,
    };
    if (this.sensUnitCostUsd) body['unit_cost_usd'] = this.sensUnitCostUsd;
    this.pricingService.sensitivityCalc(body as any).subscribe({
      next: (r) => this.sensResult.set(r),
      error: () =>
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Sensitivity calculation failed. Provide a unit cost or select a product.',
        }),
    });
  }

  saveSensScenario(): void {
    const r = this.sensResult();
    if (!r) return;
    const name = `Scenario ${new Date().toLocaleString()}`;
    this.pricingService
      .saveScenario({
        name,
        selling_price: this.sensSellingPrice,
        fx_rate: this.sensFxRate,
        quantity: this.sensQuantity,
        results: r as unknown as Record<string, unknown>,
      })
      .subscribe({
        next: () => {
          this.messageService.add({ severity: 'success', summary: 'Saved', detail: name });
          this.loadScenarios();
        },
        error: () =>
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Save failed' }),
      });
  }

  getSellingSuggestion(): void {
    if (!this.suggUnitCost) return;
    const body: Record<string, unknown> = {
      unit_cost_override: this.suggUnitCost,
      currency: this.suggCurrency,
      min_margin_pct: this.suggMinMargin,
    };
    if (this.suggFxRate) body['fx_rate_override'] = this.suggFxRate;
    this.pricingService.getSellingPriceSuggestion(body as any).subscribe({
      next: (r) => this.suggResult.set(r),
      error: () =>
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Could not compute selling price suggestion.',
        }),
    });
  }

  generateOptimizerRecs(): void {
    this.optimizerLoading.set(true);
    this.pricingService.generateOptimizerRecs(this.optimizerTargetMargin).subscribe({
      next: (recs) => {
        this.optimizerRecs.set(recs);
        this.optimizerLoading.set(false);
        this.messageService.add({
          severity: recs.length ? 'success' : 'info',
          summary: recs.length ? `${recs.length} recommendation(s) generated` : 'No gaps found',
          detail: recs.length
            ? 'Review and apply to update product prices.'
            : 'All products are at or above the target margin.',
        });
      },
      error: () => {
        this.optimizerLoading.set(false);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Optimizer failed — ensure products have sufficient sales data.',
        });
      },
    });
  }

  applyOptimizerRec(id: string): void {
    this.pricingService.applyOptimizerRec(id).subscribe({
      next: () => {
        this.optimizerRecs.update((r) => r.filter((x) => x.id !== id));
        this.messageService.add({ severity: 'success', summary: 'Applied', detail: 'Price updated.' });
        this.pricingService.getPortfolioMargin().subscribe({ next: (d) => { this.marginData.set(d); this.buildDistribution(d.products); this.buildCrossSubsidy(d); } });
      },
      error: () => this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to apply recommendation.' }),
    });
  }

  dismissOptimizerRec(id: string): void {
    this.pricingService.dismissOptimizerRec(id).subscribe({
      next: () => {
        this.optimizerRecs.update((r) => r.filter((x) => x.id !== id));
        this.messageService.add({ severity: 'info', summary: 'Dismissed', detail: 'Recommendation removed.' });
      },
      error: () => this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to dismiss.' }),
    });
  }

  runDemandForecast(): void {
    if (!this.forecastProductId) return;
    this.forecastLoading.set(true);
    this.forecastData.set(null);
    this.forecastChartData.set(null);
    this.pricingService.getDemandForecast(this.forecastProductId, this.forecastHorizon).subscribe({
      next: (r) => {
        this.forecastData.set(r.forecasts);
        this.forecastTotalDemand.set(r.total_projected_demand);
        this.forecastLoading.set(false);
        // Build chart — sample every ~7th point to avoid crowding
        const step = Math.max(1, Math.floor(r.forecasts.length / 30));
        const sampled = r.forecasts.filter((_, i) => i % step === 0);
        this.forecastChartData.set({
          labels: sampled.map((d) => d.date),
          datasets: [
            {
              label: 'Demand',
              data: sampled.map((d) => d.demand),
              borderColor: '#059669',
              backgroundColor: 'rgba(5,150,105,0.08)',
              fill: true,
              tension: 0.3,
              pointRadius: 2,
            },
            {
              label: 'Lower',
              data: sampled.map((d) => d.demand_lower),
              borderColor: 'rgba(5,150,105,0.3)',
              borderDash: [4, 4],
              fill: false,
              pointRadius: 0,
            },
            {
              label: 'Upper',
              data: sampled.map((d) => d.demand_upper),
              borderColor: 'rgba(5,150,105,0.3)',
              borderDash: [4, 4],
              fill: false,
              pointRadius: 0,
            },
          ],
        });
      },
      error: (err) => {
        this.forecastLoading.set(false);
        const detail = err?.error?.detail ?? 'Not enough sales history (need ≥10 days in last 180 days).';
        this.messageService.add({ severity: 'warn', summary: 'Forecast unavailable', detail });
      },
    });
  }

  loadScenarios(): void {
    this.pricingService.getScenarios().subscribe({
      next: (s) => this.scenarios.set(s),
    });
  }

  onMarginSearch(value: string): void {
    this.marginSearch.set(value);
    this.marginPage.set(1);
  }

  onMarginPageSizeChange(size: number): void {
    this.marginPageSize.set(size);
    this.marginPage.set(1);
  }

  marginGoToPage(page: number): void {
    const p = Math.max(1, Math.min(page, this.marginTotalPages()));
    this.marginPage.set(p);
  }

  onSubsidySearch(value: string): void {
    this.subsidySearch.set(value);
    this.subsidyPage.set(1);
  }

  onSubsidyPageSizeChange(size: number): void {
    this.subsidyPageSize.set(size);
    this.subsidyPage.set(1);
  }

  subsidyGoToPage(page: number): void {
    const p = Math.max(1, Math.min(page, this.subsidyTotalPages()));
    this.subsidyPage.set(p);
  }
}

