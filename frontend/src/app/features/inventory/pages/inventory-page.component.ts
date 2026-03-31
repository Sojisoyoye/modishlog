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
      <h2 class="mb-6 text-xl font-bold text-text">Inventory</h2>

      <!-- Stock Levels -->
      <div class="mb-6 rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Current Stock Levels</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-muted">Product</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Stock</th>
                <th class="px-4 py-3 text-right text-xs font-medium uppercase text-muted">Threshold</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-muted">Status</th>
                <th class="px-4 py-3 text-left text-xs font-medium uppercase text-muted">Depletion</th>
                <th class="px-4 py-3 text-center text-xs font-medium uppercase text-muted">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              @for (item of inventory(); track item.product_id) {
                <tr [class]="stockRowClass(item)">
                  <td class="px-4 py-3 font-medium">{{ item.product_name }}</td>
                  <td class="px-4 py-3 text-right">{{ item.current_stock }}</td>
                  <td class="px-4 py-3 text-right">{{ item.low_stock_threshold }}</td>
                  <td class="px-4 py-3">
                    <app-status-badge [label]="stockLabel(item)" [status]="stockStatus(item)" />
                  </td>
                  <td class="px-4 py-3 text-muted">
                    @if (item.depletion_date) {
                      {{ item.depletion_date | date: 'mediumDate' }}
                    } @else {
                      --
                    }
                  </td>
                  <td class="px-4 py-3 text-center">
                    <button
                      (click)="openAdjust(item)"
                      class="rounded px-2 py-1 text-xs text-secondary hover:bg-blue-50"
                    >
                      Adjust
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="6" class="px-4 py-8 text-center text-muted">No inventory data</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>

      <!-- Stock Movements -->
      <div class="rounded-lg border border-gray-200 bg-surface p-5">
        <h3 class="mb-4 text-base font-semibold text-text">Recent Movements</h3>
        <div class="overflow-x-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Date</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Product</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Type</th>
                <th class="px-3 py-2 text-right text-xs font-medium uppercase text-muted">Qty</th>
                <th class="px-3 py-2 text-left text-xs font-medium uppercase text-muted">Notes</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200">
              @for (mov of movements(); track mov.id) {
                <tr class="hover:bg-gray-50">
                  <td class="px-3 py-2 text-muted">{{ mov.created_at | date: 'short' }}</td>
                  <td class="px-3 py-2">{{ mov.product_name }}</td>
                  <td class="px-3 py-2">
                    <app-status-badge [label]="mov.movement_type" [status]="movementStatus(mov.movement_type)" />
                  </td>
                  <td class="px-3 py-2 text-right font-medium" [class]="mov.quantity >= 0 ? 'text-success' : 'text-danger'">
                    {{ mov.quantity >= 0 ? '+' : '' }}{{ mov.quantity }}
                  </td>
                  <td class="px-3 py-2 text-muted">{{ mov.notes ?? '--' }}</td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="5" class="px-3 py-6 text-center text-muted">No movements recorded</td>
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
          <p class="text-sm font-medium text-text">{{ adjustItem()!.product_name }}</p>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Type</label>
            <select
              [(ngModel)]="adjustType"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="PURCHASE">Purchase</option>
              <option value="MANUAL_CORRECTION">Manual Correction</option>
              <option value="DAMAGE">Damage</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Quantity</label>
            <input
              type="number"
              [(ngModel)]="adjustQty"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              min="1"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Notes</label>
            <textarea
              [(ngModel)]="adjustNotes"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              rows="2"
            ></textarea>
          </div>
          <button
            (click)="submitAdjust()"
            class="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
          >
            Save Adjustment
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
    if (s === 'danger') return 'bg-red-50 hover:bg-red-100';
    if (s === 'warning') return 'bg-amber-50 hover:bg-amber-100';
    return 'hover:bg-gray-50';
  }

  movementStatus(type: string): 'info' | 'success' | 'danger' | 'warning' {
    if (type === 'PURCHASE') return 'info';
    if (type === 'SALE') return 'success';
    if (type === 'DAMAGE') return 'danger';
    return 'warning';
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
