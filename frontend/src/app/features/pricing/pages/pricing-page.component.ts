import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe, CurrencyPipe } from '@angular/common';
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
  imports: [FormsModule, DecimalPipe, CurrencyPipe, Toast, UIChart, StatusBadgeComponent],
  template: `
    <p-toast />
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Pricing & Margins</h2>
        <p class="mt-1 text-sm text-muted">Analyze margins and optimize pricing</p>
      </div>

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

      <!-- Per-Product Margins -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-list text-sm text-secondary"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Per-Product Margins</h3>
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
              @for (p of marginData().products; track p.product_id) {
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
                    No pricing data available
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Pricing Recommendations -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
            <i class="pi pi-sparkles text-sm text-warning"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Pricing Recommendations</h3>
        </div>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          @for (rec of pricingRecs(); track rec.id) {
            <div class="rounded-xl border border-gray-200 p-4 transition-shadow hover:shadow-md">
              <div class="mb-2 flex items-center justify-between">
                <app-status-badge
                  [label]="rec.priority"
                  [status]="rec.priority === 'HIGH' ? 'danger' : 'warning'"
                />
                <span class="text-xs text-muted">{{ rec.category }}</span>
              </div>
              <h4 class="text-sm font-semibold text-text">{{ rec.title }}</h4>
              <p class="mt-1 text-xs text-muted leading-relaxed">{{ rec.description }}</p>
              <div class="mt-3 flex gap-2">
                <button
                  (click)="applyRec(rec.id)"
                  class="flex items-center gap-1 rounded-lg bg-success px-3 py-1.5 text-xs font-semibold text-white transition-all hover:bg-success/90"
                >
                  <i class="pi pi-check text-[10px]"></i> Apply
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
            <p class="col-span-2 py-4 text-center text-muted">No pricing recommendations</p>
          }
        </div>
      </div>

      <!-- Cross-Subsidisation Display (Task 32) -->
      <div class="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50">
            <i class="pi pi-arrows-h text-sm text-orange-600"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Cross-Subsidisation</h3>
        </div>
        @if (subsidyPairs().length > 0) {
          <div class="space-y-3">
            @for (pair of subsidyPairs(); track pair.high.product_name + pair.low.product_name) {
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
            }
          </div>
          <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <h4 class="mb-2 text-xs font-semibold uppercase text-muted">
                Above Target ({{ marginData().target_margin }}%)
              </h4>
              @for (item of aboveTarget(); track item.product_name) {
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-sm text-text">{{ item.product_name }}</span>
                  <span class="text-sm font-semibold text-success">
                    {{ item.margin_pct | number: '1.1-1' }}%
                  </span>
                </div>
              } @empty {
                <p class="text-sm text-muted">None</p>
              }
            </div>
            <div>
              <h4 class="mb-2 text-xs font-semibold uppercase text-muted">
                Below Target ({{ marginData().target_margin }}%)
              </h4>
              @for (item of belowTarget(); track item.product_name) {
                <div class="flex items-center justify-between py-1.5">
                  <span class="text-sm text-text">{{ item.product_name }}</span>
                  <span class="text-sm font-semibold text-danger">
                    {{ item.margin_pct | number: '1.1-1' }}%
                  </span>
                </div>
              } @empty {
                <p class="text-sm text-muted">None</p>
              }
            </div>
          </div>
        } @else {
          <p class="py-4 text-center text-sm text-muted">
            <i class="pi pi-info-circle mr-1"></i> Not enough product data to show
            cross-subsidisation
          </p>
        }
      </div>

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
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PricingPageComponent implements OnInit {
  private readonly pricingService = inject(PricingService);
  private readonly recsService = inject(RecommendationsService);
  private readonly productsService = inject(ProductsService);
  private readonly messageService = inject(MessageService);

  marginData = signal<PortfolioMarginData>({
    blended_margin: 0,
    target_margin: 35,
    gap: -35,
    products: [],
  });
  pricingRecs = signal<Recommendation[]>([]);
  distributionChart = signal<unknown>(null);

  // Task 32: Cross-subsidisation
  aboveTarget = signal<CrossSubsidyItem[]>([]);
  belowTarget = signal<CrossSubsidyItem[]>([]);
  subsidyPairs = signal<SubsidyPair[]>([]);

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
    this.recsService.getAll({ category: 'PRICING' }).subscribe({
      next: (r) => this.pricingRecs.set(r.items.filter((i) => i.status === 'PENDING')),
    });
    this.productsService.getAll().subscribe({
      next: (p) => this.products.set(p),
    });
    this.pricingService.getMixStatus().subscribe({
      next: (r) => this.mixStatus.set(r.categories),
    });
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
        next: () =>
          this.messageService.add({ severity: 'success', summary: 'Saved', detail: name }),
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
}
