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
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <div class="mb-4 flex items-center gap-2">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50">
              <i class="pi pi-percentage text-lg text-emerald-700"></i>
            </div>
          </div>
          <p class="text-sm font-medium text-muted">Blended Portfolio Margin</p>
          <p class="mt-2 text-4xl font-bold text-gray-900">
            {{ marginData().blended_margin | number: '1.1-1' }}%
          </p>
          <p
            class="mt-2 text-sm font-medium"
            [class]="marginData().gap >= 0 ? 'text-emerald-600' : 'text-red-600'"
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
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
              <i class="pi pi-chart-bar text-sm text-purple-700"></i>
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
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-list text-sm text-blue-700"></i>
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
                    class="px-4 py-3 text-right"
                    [class]="p.gap >= 0 ? 'text-emerald-600 font-semibold' : 'text-red-600 font-semibold'"
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
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
            <i class="pi pi-sparkles text-sm text-amber-700"></i>
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
                  class="flex min-h-[44px] items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-all hover:bg-emerald-700"
                >
                  <i class="pi pi-check text-[10px]"></i> Mark Reviewed
                </button>
                <button
                  (click)="dismissRec(rec.id)"
                  class="min-h-[44px] rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-gray-100 hover:text-text"
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
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-orange-50">
            <i class="pi pi-arrows-h text-sm text-orange-700"></i>
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
                  class="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800"
                >
                  {{ pair.high.product_name }} ({{ pair.high.margin_pct | number: '1.0-0' }}%)
                </span>
                <span class="text-xs font-medium text-muted">subsidises</span>
                <span
                  class="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-800"
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
                  <span class="text-sm font-semibold text-emerald-600">
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
                  <span class="text-sm font-semibold text-red-600">
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

      <!-- Demand Elasticity Configuration (Task 31) -->
      <div class="mt-6 rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-50">
            <i class="pi pi-sliders-h text-sm text-sky-600"></i>
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
              class="w-52 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
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
              class="w-40 rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
            />
          </div>
          <button
            (click)="updateElasticity()"
            [disabled]="!elasticityProductId || !elasticityCoeff"
            class="flex min-h-[44px] items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50"
          >
            <i class="pi pi-save text-sm"></i> Save
          </button>
          <button
            (click)="loadElasticity()"
            [disabled]="!elasticityProductId"
            class="flex min-h-[44px] items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-gray-100 hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
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
}
