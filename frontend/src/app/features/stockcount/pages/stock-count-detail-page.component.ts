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

@Component({
  selector: 'app-stock-count-detail-page',
  standalone: true,
  imports: [CommonModule, FormsModule, DialogModule, ToastModule, DatePipe, DecimalPipe],
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
                class="text-muted hover:text-text"
              >
                <i class="pi pi-arrow-left text-sm"></i>
              </button>
              <h1 class="text-2xl font-bold text-text">
                Stock Count — {{ sc.count_date | date: 'dd MMM yyyy' }}
              </h1>
              <span
                class="rounded-full px-2.5 py-0.5 text-xs font-semibold"
                [class]="sc.status === 'FINALIZED' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'"
              >{{ sc.status }}</span>
            </div>
            <p class="mt-1 ml-7 text-sm text-muted">
              {{ sc.count_type === 'PRODUCT' ? 'Product-level' : 'Lot-level' }} count
              @if (sc.notes) { · {{ sc.notes }} }
            </p>
          </div>
          @if (sc.status === 'DRAFT') {
            <button
              (click)="confirmFinalizeVisible = true"
              class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90"
            >
              <i class="pi pi-check text-sm"></i> Finalise
            </button>
          }
        </div>

        <!-- Items table -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Stock count items</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Product</th>
                @if (sc.count_type === 'LOT') {
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Lot (Order line)</th>
                }
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">System Qty</th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Counted Qty</th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Variance</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (item of sc.items; track item.id) {
                <tr>
                  <td class="px-3 py-3 font-medium text-text">{{ item.product_id }}</td>
                  @if (sc.count_type === 'LOT') {
                    <td class="px-3 py-3 text-muted text-xs">{{ item.order_line_item_id ?? '—' }}</td>
                  }
                  <td class="px-3 py-3 text-right text-muted">
                    @if (item.system_quantity_at_count !== null) {
                      {{ item.system_quantity_at_count | number: '1.0-2' }}
                    } @else {
                      <span class="text-muted">—</span>
                    }
                  </td>
                  <td class="px-3 py-3 text-right">
                    @if (sc.status === 'DRAFT') {
                      <input
                        type="number"
                        [value]="item.counted_quantity ?? ''"
                        min="0"
                        step="1"
                        (change)="updateItem(sc.id, item.id, $event)"
                        class="w-24 rounded border border-gray-300 px-2 py-1 text-right text-sm focus:border-primary focus:ring-1 focus:ring-primary"
                      />
                    } @else {
                      {{ item.counted_quantity !== null ? (item.counted_quantity | number: '1.0-2') : '—' }}
                    }
                  </td>
                  <td class="px-3 py-3 text-right">
                    @if (item.variance !== null) {
                      <span
                        class="rounded-full px-2 py-0.5 text-xs font-semibold"
                        [class]="item.variance > 0
                          ? 'bg-green-100 text-green-700'
                          : item.variance < 0
                          ? 'bg-red-100 text-red-700'
                          : 'bg-gray-100 text-gray-600'"
                      >
                        {{ item.variance > 0 ? '+' : '' }}{{ item.variance | number: '1.0-2' }}
                      </span>
                    } @else {
                      <span class="text-muted">—</span>
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td [attr.colspan]="sc.count_type === 'LOT' ? 5 : 4" class="py-10 text-center text-muted">
                    No items
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p class="text-muted">Loading...</p>
      }
    </div>

    <!-- Finalise confirmation dialog -->
    <p-dialog
      header="Finalise Stock Count"
      [(visible)]="confirmFinalizeVisible"
      [modal]="true"
      [style]="{ width: '400px' }"
    >
      <p class="text-sm text-muted">
        This will snapshot the current system stock quantities into each item and lock the count.
        You will not be able to edit counted quantities after finalisation.
      </p>
      <ng-template pTemplate="footer">
        <button
          (click)="confirmFinalizeVisible = false"
          class="mr-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted hover:bg-gray-50"
        >Cancel</button>
        <button
          (click)="finalize()"
          [disabled]="finalizing()"
          class="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
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
  confirmFinalizeVisible = false;

  private get id(): string {
    return this.route.snapshot.paramMap.get('id')!;
  }

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.service.get(this.id).subscribe({ next: (sc) => this.stockCount.set(sc) });
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
        this.confirmFinalizeVisible = false;
        this.stockCount.set(sc);
        this.messageService.add({ severity: 'success', summary: 'Finalised', detail: 'Stock count is now locked' });
      },
      error: () => {
        this.finalizing.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to finalise' });
      },
    });
  }
}
