import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  inject,
  signal,
} from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';
import { Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { StockCountService } from '../services/stock-count.service';
import { StockCountListItem } from '../models/stock-count.model';

@Component({
  selector: 'app-stock-count-list-page',
  standalone: true,
  imports: [CommonModule, FormsModule, DialogModule, ToastModule, DatePipe],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <div class="p-6">
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-text">Stock Counts</h1>
          <p class="mt-1 text-sm text-muted">Physical inventory count sessions and variance reports</p>
        </div>
        <button
          (click)="showCreate = true"
          class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90"
        >
          <i class="pi pi-plus text-sm"></i> New Stock Count
        </button>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <table class="min-w-full divide-y divide-gray-200 text-sm">
          <caption class="sr-only">Stock count sessions</caption>
          <thead>
            <tr class="bg-gray-50/80">
              <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Count Date</th>
              <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Type</th>
              <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Status</th>
              <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase text-muted">Items</th>
              <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase text-muted">Created</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            @for (sc of counts(); track sc.id) {
              <tr
                role="button"
                tabindex="0"
                (click)="open(sc.id)"
                (keydown.enter)="open(sc.id)"
                class="cursor-pointer transition-colors hover:bg-gray-50"
              >
                <td class="px-3 py-3 font-medium text-text">{{ sc.count_date | date: 'dd MMM yyyy' }}</td>
                <td class="px-3 py-3 text-muted">{{ sc.count_type === 'PRODUCT' ? 'Product' : 'Lot' }}</td>
                <td class="px-3 py-3">
                  <span
                    class="rounded-full px-2 py-0.5 text-xs font-semibold"
                    [class]="sc.status === 'FINALIZED'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-yellow-100 text-yellow-700'"
                  >{{ sc.status }}</span>
                </td>
                <td class="px-3 py-3 text-right text-muted">{{ sc.item_count }}</td>
                <td class="px-3 py-3 text-muted">{{ sc.created_at | date: 'dd MMM yyyy' }}</td>
              </tr>
            } @empty {
              <tr>
                <td colspan="5" class="py-10 text-center text-muted">No stock counts yet</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>

    <!-- Creation dialog -->
    <p-dialog
      header="New Stock Count"
      [(visible)]="showCreate"
      [modal]="true"
      [style]="{ width: '420px' }"
      [closable]="true"
    >
      <div class="space-y-4 py-2">
        <div>
          <label class="mb-1.5 block text-sm font-medium text-text" for="count-date">Count date</label>
          <input
            id="count-date"
            type="date"
            [(ngModel)]="form.count_date"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <p class="mb-1.5 text-sm font-medium text-text">Count type</p>
          <div class="flex gap-4">
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <input type="radio" name="count_type" value="PRODUCT" [(ngModel)]="form.count_type" />
              Product level
            </label>
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <input type="radio" name="count_type" value="LOT" [(ngModel)]="form.count_type" />
              Lot level
            </label>
          </div>
        </div>
        <div>
          <label class="mb-1.5 block text-sm font-medium text-text" for="count-notes">Notes (optional)</label>
          <textarea
            id="count-notes"
            [(ngModel)]="form.notes"
            rows="2"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          ></textarea>
        </div>
      </div>
      <ng-template #footer>
        <button
          (click)="showCreate = false"
          class="mr-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-muted hover:bg-gray-50"
        >Cancel</button>
        <button
          (click)="create()"
          [disabled]="creating()"
          class="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
        >
          @if (creating()) { Creating... } @else { Create }
        </button>
      </ng-template>
    </p-dialog>
  `,
})
export class StockCountListPageComponent implements OnInit {
  private readonly service = inject(StockCountService);
  private readonly router = inject(Router);
  private readonly messageService = inject(MessageService);

  counts = signal<StockCountListItem[]>([]);
  creating = signal(false);
  showCreate = false;

  form = {
    count_date: new Date().toISOString().split('T')[0],
    count_type: 'PRODUCT' as 'PRODUCT' | 'LOT',
    notes: '',
  };

  ngOnInit(): void {
    this.load();
  }

  private load(): void {
    this.service.list().subscribe({ next: (c) => this.counts.set(c) });
  }

  open(id: string): void {
    this.router.navigate(['/stock-counts', id]);
  }

  create(): void {
    if (!this.form.count_date) return;
    this.creating.set(true);
    this.service
      .create({
        count_date: this.form.count_date,
        count_type: this.form.count_type,
        notes: this.form.notes || null,
      })
      .subscribe({
        next: (sc) => {
          this.creating.set(false);
          this.showCreate = false;
          this.router.navigate(['/stock-counts', sc.id]);
        },
        error: () => {
          this.creating.set(false);
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to create stock count' });
        },
      });
  }
}
