import { Component, ChangeDetectionStrategy, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import {
  InventoryService,
  InventoryItem,
  StockMovement,
} from '../../../core/services/inventory.service';

@Component({
  selector: 'app-inventory-page',
  standalone: true,
  imports: [FormsModule, DatePipe, Toast, Dialog, StatusBadgeComponent],
  template: `
    <p-toast />
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Inventory</h2>
        <p class="mt-1 text-sm text-muted">Monitor stock levels and movements</p>
      </div>

      <!-- Stock Levels -->
      <div class="mb-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-box text-sm text-secondary"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Current Stock Levels</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Current stock levels</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Product
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Stock
                </th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase text-muted">
                  Threshold
                </th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Status
                </th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase text-muted">
                  Depletion
                </th>
                <th class="px-4 py-3 text-center text-xs font-semibold uppercase text-muted">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (item of inventory(); track item.product_id) {
                <tr [class]="stockRowClass(item)">
                  <td class="px-4 py-3 font-medium text-text">{{ item.product_name }}</td>
                  <td class="px-4 py-3 text-right font-semibold">{{ item.current_stock }}</td>
                  <td class="px-4 py-3 text-right text-muted">
                    @if (editingThresholdId() === item.product_id) {
                      <input
                        type="number"
                        [value]="item.low_stock_threshold"
                        min="0"
                        class="w-20 rounded border border-primary px-2 py-1 text-right text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        (keydown.enter)="saveThreshold(item.product_id, $event)"
                        (blur)="saveThreshold(item.product_id, $event)"
                        #thresholdInput
                      />
                    } @else {
                      <span
                        class="cursor-pointer rounded px-1.5 py-0.5 transition-colors hover:bg-blue-50 hover:text-secondary"
                        (click)="startEditThreshold(item.product_id)"
                        title="Click to edit threshold"
                      >
                        {{ item.low_stock_threshold }}
                        <i class="pi pi-pencil ml-0.5 text-[9px] text-gray-300"></i>
                      </span>
                    }
                  </td>
                  <td class="px-4 py-3">
                    <app-status-badge [label]="stockLabel(item)" [status]="stockStatus(item)" />
                  </td>
                  <td class="px-4 py-3 text-muted">
                    @if (item.depletion_date) {
                      {{ item.depletion_date | date: 'mediumDate' }}
                      <span class="ml-1 text-xs text-gray-400"
                        title="Confidence interval: +/- 20% of estimated days">
                        (+/- {{ depletionConfidence(item) }}d)
                      </span>
                    } @else {
                      --
                    }
                  </td>
                  <td class="px-4 py-3 text-center">
                    <button
                      (click)="openAdjust(item)"
                      class="rounded-lg px-3 py-1.5 text-xs font-medium text-secondary transition-colors hover:bg-blue-50"
                    >
                      <i class="pi pi-pencil mr-1 text-[10px]"></i> Adjust
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6" class="px-4 py-10 text-center text-muted">
                    <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                    No inventory data
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Stock Movements -->
      <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
            <i class="pi pi-arrow-right-arrow-left text-sm text-warning"></i>
          </div>
          <h3 class="text-base font-semibold text-text">Recent Movements</h3>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Recent stock movements</caption>
            <thead>
              <tr class="bg-gray-50/80">
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Date
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Product
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Type
                </th>
                <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">
                  Qty
                </th>
                <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">
                  Notes
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (mov of movements(); track mov.id) {
                <tr class="transition-colors hover:bg-gray-50/50">
                  <td class="px-3 py-2.5 text-muted">{{ mov.created_at | date: 'short' }}</td>
                  <td class="px-3 py-2.5 font-medium">{{ mov.product_name }}</td>
                  <td class="px-3 py-2.5">
                    <app-status-badge
                      [label]="mov.movement_type"
                      [status]="movementStatus(mov.movement_type)"
                    />
                  </td>
                  <td
                    class="px-3 py-2.5 text-right font-semibold"
                    [class]="mov.quantity >= 0 ? 'text-success' : 'text-danger'"
                  >
                    {{ mov.quantity >= 0 ? '+' : '' }}{{ mov.quantity }}
                  </td>
                  <td class="px-3 py-2.5 text-muted">{{ mov.notes ?? '--' }}</td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="5" class="px-3 py-10 text-center text-muted">
                    <i class="pi pi-inbox mb-2 block text-2xl text-gray-300"></i>
                    No movements recorded
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Adjust Dialog -->
    <p-dialog
      header="Adjust Stock"
      [(visible)]="adjustVisible"
      [modal]="true"
      [style]="{ width: '400px' }"
    >
      @if (adjustItem()) {
        <div class="space-y-4">
          <div class="rounded-lg bg-gray-50 p-3">
            <p class="text-sm font-semibold text-text">{{ adjustItem()!.product_name }}</p>
            <p class="text-xs text-muted">Current stock: {{ adjustItem()!.current_stock }}</p>
          </div>
          <div>
            <label for="inv-adjust-type" class="mb-1.5 block text-xs font-medium text-muted">Type</label>
            <select
              id="inv-adjust-type"
              [(ngModel)]="adjustType"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="PURCHASE">Purchase</option>
              <option value="MANUAL_CORRECTION">Manual Correction</option>
              <option value="DAMAGE">Damage</option>
            </select>
          </div>
          <div>
            <label for="inv-adjust-qty" class="mb-1.5 block text-xs font-medium text-muted">Quantity</label>
            <input
              id="inv-adjust-qty"
              type="number"
              [(ngModel)]="adjustQty"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              min="1"
            />
          </div>
          <div>
            <label for="inv-adjust-notes" class="mb-1.5 block text-xs font-medium text-muted">Notes</label>
            <textarea
              id="inv-adjust-notes"
              [(ngModel)]="adjustNotes"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              rows="2"
              placeholder="Optional notes..."
            ></textarea>
          </div>
          <button
            (click)="submitAdjust()"
            class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md"
          >
            <i class="pi pi-check text-sm"></i> Save Adjustment
          </button>
        </div>
      }
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InventoryPageComponent implements OnInit {
  private readonly inventoryService = inject(InventoryService);
  private readonly messageService = inject(MessageService);

  inventory = signal<InventoryItem[]>([]);
  movements = signal<StockMovement[]>([]);
  editingThresholdId = signal<string | null>(null);
  adjustVisible = false;
  adjustItem = signal<InventoryItem | null>(null);
  adjustType = 'PURCHASE';
  adjustQty = 1;
  adjustNotes = '';

  ngOnInit(): void {
    this.loadData();
  }

  private loadData(): void {
    this.inventoryService.getCurrent().subscribe({ next: (d) => this.inventory.set(d) });
    this.inventoryService.getMovements().subscribe({ next: (d) => this.movements.set(d) });
  }

  stockStatus(item: InventoryItem): 'success' | 'warning' | 'danger' {
    if (item.current_stock <= item.low_stock_threshold) return 'danger';
    if (item.current_stock <= item.low_stock_threshold * 2) return 'warning';
    return 'success';
  }

  stockLabel(item: InventoryItem): string {
    const s = this.stockStatus(item);
    if (s === 'danger') return 'Critical';
    if (s === 'warning') return 'Low';
    return 'Healthy';
  }

  stockRowClass(item: InventoryItem): string {
    const s = this.stockStatus(item);
    if (s === 'danger') return 'bg-red-50/50 hover:bg-red-50';
    if (s === 'warning') return 'bg-amber-50/50 hover:bg-amber-50';
    return 'transition-colors hover:bg-gray-50/50';
  }

  depletionConfidence(item: InventoryItem): number {
    // Estimate days until stockout from depletion_date, then +/- 20%
    if (!item.depletion_date) return 0;
    const now = new Date();
    const depDate = new Date(item.depletion_date);
    const daysUntil = Math.max(0, Math.round((depDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)));
    return Math.max(1, Math.round(daysUntil * 0.2));
  }

  movementStatus(type: string): 'info' | 'success' | 'danger' | 'warning' {
    if (type === 'PURCHASE') return 'info';
    if (type === 'SALE') return 'success';
    if (type === 'DAMAGE') return 'danger';
    return 'warning';
  }

  startEditThreshold(productId: string): void {
    this.editingThresholdId.set(productId);
  }

  saveThreshold(productId: string, event: Event): void {
    const input = event.target as HTMLInputElement;
    const value = parseInt(input.value, 10);
    this.editingThresholdId.set(null);
    if (isNaN(value) || value < 0) return;
    this.inventoryService.updateThreshold(productId, value).subscribe({
      next: () => {
        this.messageService.add({
          severity: 'success',
          summary: 'Updated',
          detail: 'Threshold updated',
        });
        this.loadData();
      },
      error: () => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to update threshold',
        });
      },
    });
  }

  openAdjust(item: InventoryItem): void {
    this.adjustItem.set(item);
    this.adjustType = 'PURCHASE';
    this.adjustQty = 1;
    this.adjustNotes = '';
    this.adjustVisible = true;
  }

  submitAdjust(): void {
    const item = this.adjustItem();
    if (!item) return;
    this.inventoryService
      .adjust({
        product_id: item.product_id,
        adjustment_type: this.adjustType,
        quantity: this.adjustQty,
        notes: this.adjustNotes,
      })
      .subscribe({
        next: () => {
          this.adjustVisible = false;
          this.messageService.add({
            severity: 'success',
            summary: 'Adjusted',
            detail: 'Stock updated successfully',
          });
          this.loadData();
        },
        error: () => {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to adjust stock',
          });
        },
      });
  }
}
