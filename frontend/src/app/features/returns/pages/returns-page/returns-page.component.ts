import {
  Component,
  ChangeDetectionStrategy,
  signal,
} from '@angular/core';
import { SellReturnsTabComponent } from '../../components/sell-returns-tab/sell-returns-tab.component';
import { PurchaseReturnsTabComponent } from '../../components/purchase-returns-tab/purchase-returns-tab.component';

type ActiveTab = 'sell' | 'purchase';

@Component({
  selector: 'app-returns-page',
  standalone: true,
  imports: [SellReturnsTabComponent, PurchaseReturnsTabComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div>
      <!-- Header -->
      <div class="mb-6 flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-50 text-orange-600">
          <i class="pi pi-replay text-lg"></i>
        </div>
        <div>
          <h2 class="text-2xl font-bold text-text">Returns</h2>
          <p class="mt-0.5 text-sm text-muted">Manage sell and purchase returns</p>
        </div>
      </div>

      <!-- Tabs -->
      <div class="mb-5 flex gap-1 border-b border-gray-200">
        <button
          (click)="activeTab.set('sell')"
          [class]="activeTab() === 'sell'
            ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary'
            : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-arrow-circle-left mr-1.5 text-xs"></i> Sell Returns
        </button>
        <button
          (click)="activeTab.set('purchase')"
          [class]="activeTab() === 'purchase'
            ? 'border-b-2 border-primary px-4 py-2 text-sm font-semibold text-primary'
            : 'border-b-2 border-transparent px-4 py-2 text-sm text-muted hover:text-text'"
        >
          <i class="pi pi-arrow-circle-right mr-1.5 text-xs"></i> Purchase Returns
        </button>
      </div>

      <!-- Tab content -->
      @if (activeTab() === 'sell') {
        <app-sell-returns-tab />
      } @else {
        <app-purchase-returns-tab />
      }
    </div>
  `,
})
export class ReturnsPageComponent {
  activeTab = signal<ActiveTab>('sell');
}
