import { Component, ChangeDetectionStrategy } from '@angular/core';
import { RouterLink } from '@angular/router';

interface ReportCard {
  title: string;
  description: string;
  route: string;
  icon: string;
  color: string;
}

@Component({
  selector: 'app-reports-index',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Reports</h2>
        <p class="mt-1 text-sm text-muted">Business insights and financial summaries</p>
      </div>

      <div class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        @for (card of reportCards; track card.route) {
          <a
            [routerLink]="card.route"
            class="group flex flex-col rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-all hover:border-primary/30 hover:shadow-md"
          >
            <div class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl" [class]="card.color">
              <i [class]="'pi ' + card.icon + ' text-xl'"></i>
            </div>
            <h3 class="text-lg font-semibold text-text group-hover:text-primary">{{ card.title }}</h3>
            <p class="mt-1 text-sm text-muted">{{ card.description }}</p>
            <div class="mt-4 flex items-center gap-1 text-sm font-medium text-secondary">
              <span>View report</span>
              <i class="pi pi-arrow-right text-xs transition-transform group-hover:translate-x-1"></i>
            </div>
          </a>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportsIndexComponent {
  readonly reportCards: ReportCard[] = [
    {
      title: 'Profit & Loss',
      description: 'Revenue, costs, and net profit over a period',
      route: '/reports/profit-loss',
      icon: 'pi-chart-line',
      color: 'bg-green-50 text-green-600',
    },
    {
      title: 'Stock Report',
      description: 'Current inventory valuation and potential profit',
      route: '/reports/stock',
      icon: 'pi-box',
      color: 'bg-blue-50 text-blue-600',
    },
    {
      title: 'Purchase & Sale',
      description: 'Summary of purchases and sales over a period',
      route: '/reports/purchase-sale',
      icon: 'pi-arrows-h',
      color: 'bg-purple-50 text-purple-600',
    },
  ];
}
