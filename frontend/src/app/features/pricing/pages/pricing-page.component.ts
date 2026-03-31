import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { DecimalPipe, CurrencyPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { UIChart } from 'primeng/chart';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { PricingService, PortfolioMarginData, ProductMargin } from '../../../core/services/pricing.service';
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
      <h2 class="mb-6 text-xl font-bold text-text">Pricing & Margins</h2>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <!-- Blended Margin Card -->
        <div class="rounded-lg border border-gray-200 bg-surface p-6 text-center">
          <p class="text-sm text-muted">Blended Portfolio Margin</p>
          <p class="mt-2 text-4xl font-bold text-text">
            {{ marginData().blended_margin | number: '1.1-1' }}%
          </p>
          <p class="mt-1 text-sm" [class]="marginData().gap >= 0 ? 'text-success' : 'text-danger'">
            @if (marginData().gap >= 0) {
              +{{ marginData().gap | number: '1.1-1' }}% above {{ marginData().target_margin }}% target
            } @else {
              {{ marginData().gap | number: '1.1-1' }}% below {{ marginData().target_margin }}% target
            }
          </p>
        </div>

        <!-- Margin Distribution Chart -->
        <div class="rounded-lg border border-gray-200 bg-surface p-5 lg:col-span-2">
          <h3 class="mb-4 text-base font-semibold text-text">Margin Distribution</h3>
          @if (distributionChart()) {
            <p-chart type="bar" [data]="distributionChart()!" [options]="barOptions" height="200px" />
          }
        </div>
      </div>

      <!-- Per-Product Margins -->
      <div class="mt-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Per-Product Margins</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-muted">Product</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Cost</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Selling</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Margin</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Target</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Gap</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              @for (p of marginData().products; track p.product_id) {
                <tr [class]="p.gap >= 0 ? 'hover:bg-gray-50' : 'bg-red-50 hover:bg-red-100'">
                  <td class="px-4 py-3 font-medium">{{ p.product_name }}</td>
                  <td class="px-4 py-3 text-right text-muted">
                    {{ p.cost_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right">
                    {{ p.selling_price | currency: 'NGN' : 'symbol' : '1.0-0' }}
                  </td>
                  <td class="px-4 py-3 text-right font-medium">
                    {{ p.current_margin | number: '1.1-1' }}%
                  </td>
                  <td class="px-4 py-3 text-right text-muted">
                    {{ p.target_margin | number: '1.1-1' }}%
                  </td>
                  <td class="px-4 py-3 text-right font-medium" [class]="p.gap >= 0 ? 'text-success' : 'text-danger'">
                    {{ p.gap >= 0 ? '+' : '' }}{{ p.gap | number: '1.1-1' }}%
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6" class="px-4 py-8 text-center text-muted">No pricing data available</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Pricing Recommendations -->
      <div class="mt-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Pricing Recommendations</h3>
        <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
          @for (rec of pricingRecs(); track rec.id) {
            <div class="rounded-lg border border-gray-200 p-4">
              <div class="mb-2 flex items-center justify-between">
                <app-status-badge [label]="rec.priority" [status]="rec.priority === 'HIGH' ? 'danger' : 'warning'" />
                <span class="text-xs text-muted">{{ rec.category }}</span>
              </div>
              <h4 class="text-sm font-medium text-text">{{ rec.title }}</h4>
              <p class="mt-1 text-xs text-muted">{{ rec.description }}</p>
              <div class="mt-3 flex gap-2">
                <button
                  (click)="applyRec(rec.id)"
                  class="rounded bg-success px-3 py-1 text-xs font-medium text-white hover:bg-success/90"
                >
                  Apply
                </button>
                <button
                  (click)="dismissRec(rec.id)"
                  class="rounded border border-gray-300 px-3 py-1 text-xs text-muted hover:bg-gray-50"
                >
                  Dismiss
                </button>
              </div>
            </div>
          } @empty {
            <p class="col-span-2 text-muted">No pricing recommendations</p>
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
    scales: { y: { beginAtZero: true, title: { display: true, text: 'Products' } } },
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
