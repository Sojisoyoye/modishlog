import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, CurrencyPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { UIChart } from 'primeng/chart';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  PricingService,
  PortfolioMarginData,
  ProductMargin,
} from '../../../core/services/pricing.service';
import {
  RecommendationsService,
  Recommendation,
} from '../../../core/services/recommendations.service';

@Component({
  selector: 'app-pricing-page',
  standalone: true,
  imports: [DecimalPipe, CurrencyPipe, Toast, UIChart, StatusBadgeComponent],
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
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PricingPageComponent implements OnInit {
  private readonly pricingService = inject(PricingService);
  private readonly recsService = inject(RecommendationsService);
  private readonly messageService = inject(MessageService);

  marginData = signal<PortfolioMarginData>({
    blended_margin: 0,
    target_margin: 35,
    gap: -35,
    products: [],
  });
  pricingRecs = signal<Recommendation[]>([]);
  distributionChart = signal<unknown>(null);

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
      },
    });
    this.recsService.getAll({ category: 'PRICING' }).subscribe({
      next: (r) => this.pricingRecs.set(r.items.filter((i) => i.status === 'PENDING')),
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
}
