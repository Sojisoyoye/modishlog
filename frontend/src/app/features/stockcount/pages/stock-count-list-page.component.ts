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
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';

@Component({
  selector: 'app-stock-count-list-page',
  standalone: true,
  imports: [CommonModule, FormsModule, DialogModule, ToastModule, DatePipe, StatusBadgeComponent],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <div class="p-6">
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">Stock Counts</h1>
          <p class="mt-1 text-sm text-gray-500">Physical inventory count sessions and variance reports</p>
        </div>
        <button
          (click)="showCreate = true"
          class="flex min-h-[44px] items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90"
        >
          <i class="pi pi-plus text-sm"></i> New Stock Count
        </button>
      </div>

      <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
        <table class="min-w-full divide-y divide-gray-200 text-sm">
          <caption class="sr-only">Stock count sessions</caption>
          <thead>
            <tr class="bg-gray-50">
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Count Date</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Type</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Items</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Created</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Action</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            @for (sc of counts(); track sc.id) {
              <tr
                class="cursor-pointer transition-colors hover:bg-gray-50"
                (click)="open(sc.id)"
                (keydown.enter)="open(sc.id)"
                role="button"
                tabindex="0"
              >
                <td class="px-4 py-3 font-medium text-gray-900">{{ sc.count_date | date: 'dd MMM yyyy' }}</td>
                <td class="px-4 py-3 text-gray-500">{{ sc.count_type === 'PRODUCT' ? 'Product' : 'Lot' }}</td>
                <td class="px-4 py-3">
                  @if (sc.status === 'FINALIZED') {
                    <app-status-badge label="Completed" status="success" />
                  } @else if (sc.status === 'DRAFT') {
                    <app-status-badge label="Draft" status="neutral" />
                  } @else {
                    <app-status-badge label="In Progress" status="warning" />
                  }
                </td>
                <td class="px-4 py-3 text-right text-gray-500">{{ sc.item_count }}</td>
                <td class="px-4 py-3 text-gray-500">{{ sc.created_at | date: 'dd MMM yyyy' }}</td>
                <td class="px-4 py-3">
                  <button
                    (click)="open(sc.id); $event.stopPropagation()"
                    class="inline-flex min-h-[44px] items-center rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                  >
                    <i class="pi pi-eye mr-1.5 text-xs"></i> View
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="6" class="py-16 text-center">
                  <div class="flex flex-col items-center gap-3">
                    <div class="flex h-12 w-12 items-center justify-center rounded-full bg-gray-100">
                      <i class="pi pi-clipboard text-xl text-gray-400"></i>
                    </div>
                    <div>
                      <p class="text-sm font-medium text-gray-700">No stock counts yet</p>
                      <p class="mt-0.5 text-xs text-gray-500">Start a new count to track inventory variance</p>
                    </div>
                    <button
                      (click)="showCreate = true"
                      class="mt-1 flex min-h-[44px] items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90"
                    >
                      <i class="pi pi-plus text-sm"></i> New Stock Count
                    </button>
                  </div>
                </td>
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
