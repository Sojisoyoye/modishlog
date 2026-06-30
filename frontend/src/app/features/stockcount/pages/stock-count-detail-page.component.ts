import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { CommonModule, DatePipe, DecimalPipe } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { StockCountService } from '../services/stock-count.service';
import { StockCount, StockCountItem } from '../models/stock-count.model';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';

@Component({
  selector: 'app-stock-count-detail-page',
  standalone: true,
  imports: [CommonModule, FormsModule, DialogModule, ToastModule, DatePipe, DecimalPipe, StatusBadgeComponent],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <div class="p-6">
      @if (stockCount(); as sc) {
        <!-- Header -->
        <div class="mb-6 flex items-start justify-between">
          <div>
            <div class="flex items-center gap-3">
              <button
                (click)="router.navigate(['/stock-counts'])"
                class="inline-flex min-h-[44px] items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm transition-colors hover:bg-gray-50"
              >
                <i class="pi pi-arrow-left text-sm"></i>
                <span>Back</span>
              </button>
              <div>
                <div class="flex items-center gap-2">
                  <h1 class="text-2xl font-bold text-gray-900">
                    Stock Count — {{ sc.count_date | date: 'dd MMM yyyy' }}
                  </h1>
                  @if (sc.status === 'FINALIZED') {
                    <app-status-badge label="Completed" status="success" />
                  } @else {
                    <app-status-badge label="Draft" status="neutral" />
                  }
                </div>
                <p class="mt-1 text-sm text-gray-500">
                  {{ sc.count_type === 'PRODUCT' ? 'Product-level' : 'Lot-level' }} count
                  @if (sc.notes) { · {{ sc.notes }} }
                </p>
              </div>
            </div>
          </div>
          @if (sc.status === 'DRAFT') {
            <button
              (click)="confirmFinalizeVisible.set(true)"
              class="flex min-h-[44px] items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary/90"
            >
              <i class="pi pi-check text-sm"></i> Finalise Count
            </button>
          }
        </div>

        <!-- Items section card -->
        <div class="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <div class="mb-4 flex items-center gap-3">
            <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
              <i class="pi pi-list text-base"></i>
            </div>
            <h2 class="text-base font-semibold text-gray-900">Count Items</h2>
          </div>
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Stock count items</caption>
            <thead>
              <tr class="bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Product</th>
                @if (sc.count_type === 'LOT') {
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Lot (Order line)</th>
                }
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">System Qty</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Counted Qty</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Variance</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (item of sc.items; track item.id) {
                <tr class="hover:bg-gray-50">
                  <td class="px-4 py-3 font-medium text-gray-900">{{ item.product_name }}</td>
                  @if (sc.count_type === 'LOT') {
                    <td class="px-4 py-3 text-xs text-gray-500">{{ item.order_line_item_id ?? '—' }}</td>
                  }
                  <td class="px-4 py-3 text-right text-gray-500">
                    @if (item.system_quantity_at_count !== null) {
                      {{ item.system_quantity_at_count | number: '1.0-2' }}
                    } @else {
                      <span class="text-gray-400">—</span>
                    }
                  </td>
                  <td class="px-4 py-3 text-right">
                    @if (sc.status === 'DRAFT') {
                      <input
                        type="number"
                        [value]="item.counted_quantity ?? ''"
                        min="0"
                        step="1"
                        (change)="updateItem(sc.id, item.id, $event)"
                        class="w-24 rounded-lg border border-gray-300 px-2 py-1.5 text-right text-sm min-h-[44px] focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
                      />
                    } @else {
                      <span class="text-gray-700">{{ item.counted_quantity !== null ? (item.counted_quantity | number: '1.0-2') : '—' }}</span>
                    }
                  </td>
                  <td class="px-4 py-3 text-right">
                    @if (item.variance !== null) {
                      @if (item.variance > 0) {
                        <span class="font-semibold text-emerald-600">
                          +{{ item.variance | number: '1.0-2' }}
                        </span>
                      } @else if (item.variance < 0) {
                        <span class="font-semibold text-red-600">
                          {{ item.variance | number: '1.0-2' }}
                        </span>
                      } @else {
                        <span class="text-gray-500">
                          {{ item.variance | number: '1.0-2' }}
                        </span>
                      }
                    } @else {
                      <span class="text-gray-400">—</span>
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td [attr.colspan]="sc.count_type === 'LOT' ? 5 : 4" class="py-10 text-center text-gray-400">
                    No items
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else if (loadError()) {
        <p class="mt-8 text-center text-sm text-red-600">Failed to load. Please refresh.</p>
      } @else {
        <p class="text-gray-400">Loading...</p>
      }
    </div>

    <!-- Finalise confirmation dialog -->
    <p-dialog
      header="Finalise Stock Count"
      [visible]="confirmFinalizeVisible()"
      (visibleChange)="confirmFinalizeVisible.set($event)"
      [modal]="true"
      [style]="{ width: '400px' }"
    >
      <p class="text-sm text-gray-500">
        This will snapshot the current system stock quantities into each item and lock the count.
        You will not be able to edit counted quantities after finalisation.
      </p>
      <ng-template #footer>
        <button
          (click)="confirmFinalizeVisible.set(false)"
          class="mr-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-500 hover:bg-gray-50"
        >Cancel</button>
        <button
          (click)="finalize()"
          [disabled]="finalizing()"
          class="flex min-h-[44px] items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
        >
          @if (finalizing()) { Finalising... } @else { Confirm }
        </button>
      </ng-template>
    </p-dialog>
  `,
})
export class StockCountDetailPageComponent implements OnInit {
  private readonly service = inject(StockCountService);
  readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly messageService = inject(MessageService);

  stockCount = signal<StockCount | null>(null);
  finalizing = signal(false);
  loadError = signal(false);
  confirmFinalizeVisible = signal(false);

  private get id(): string {
    return this.route.snapshot.paramMap.get('id')!;
  }

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.service.get(this.id).subscribe({
      next: (sc) => this.stockCount.set(sc),
      error: () => this.loadError.set(true),
    });
  }

  updateItem(stockCountId: string, itemId: string, event: Event): void {
    const value = parseFloat((event.target as HTMLInputElement).value);
    if (isNaN(value) || value < 0) return;
    this.service.updateItem(stockCountId, itemId, value).subscribe({
      next: (updated) => {
        this.stockCount.update((sc) => {
          if (!sc) return sc;
          return {
            ...sc,
            items: sc.items.map((i) => (i.id === itemId ? { ...i, ...updated } : i)),
          };
        });
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to update item' });
      },
    });
  }

  finalize(): void {
    this.finalizing.set(true);
    this.service.finalize(this.id).subscribe({
      next: (sc) => {
        this.finalizing.set(false);
        this.confirmFinalizeVisible.set(false);
        this.stockCount.set(sc);
        this.messageService.add({ severity: 'success', summary: 'Finalised', detail: 'Stock count is now locked' });
      },
      error: () => {
        this.finalizing.set(false);
        this.confirmFinalizeVisible.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to finalise' });
      },
    });
  }
}
