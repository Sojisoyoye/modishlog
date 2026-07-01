import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  OnInit,
} from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { ReturnsService } from '../../services/returns.service';
import { PurchaseReturn } from '../../models/return.model';

@Component({
  selector: 'app-purchase-returns-tab',
  standalone: true,
  imports: [DecimalPipe, DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="mb-4">
      <p class="text-sm text-muted">{{ total() }} purchase return{{ total() !== 1 ? 's' : '' }}</p>
    </div>

    @if (loadError()) {
      <div class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        <i class="pi pi-exclamation-circle"></i>
        Failed to load purchase returns.
        <button (click)="load()" class="ml-auto underline hover:no-underline">Retry</button>
      </div>
    }

    <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
      <div class="overflow-x-auto">
        @if (loading()) {
          <div class="flex items-center justify-center py-16">
            <i class="pi pi-spinner pi-spin text-2xl text-muted"></i>
          </div>
        } @else {
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Purchase returns list</caption>
            <thead>
              <tr class="bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Ref No</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Order ID</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Return Date</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Total Amount</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Notes</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (r of returns(); track r.id) {
                <tr class="transition-colors hover:bg-gray-50">
                  <td class="px-4 py-3 font-mono text-xs text-gray-700">{{ r.ref_no ?? '—' }}</td>
                  <td class="px-4 py-3 font-mono text-xs text-gray-500">{{ r.original_order_id.slice(0, 8) }}…</td>
                  <td class="px-4 py-3 text-gray-700">{{ r.return_date | date: 'mediumDate' }}</td>
                  <td class="px-4 py-3 text-right font-medium">{{ +r.total_amount | number: '1.2-2' }}</td>
                  <td class="px-4 py-3 text-muted">{{ r.notes ?? '—' }}</td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="5" class="py-12 text-center text-sm text-muted">No purchase returns found.</td>
                </tr>
              }
            </tbody>
          </table>
        }
      </div>

      @if (total() > pageSize) {
        <div class="flex items-center justify-between border-t border-gray-100 px-4 py-3">
          <p class="text-sm text-muted">
            Showing {{ (page() - 1) * pageSize + 1 }}–{{ pageEnd() }} of {{ total() }}
          </p>
          <div class="flex gap-1">
            <button
              (click)="changePage(page() - 1)"
              [disabled]="page() === 1"
              class="rounded px-3 py-1.5 text-sm text-muted hover:bg-gray-100 disabled:opacity-40"
            >
              <i class="pi pi-chevron-left"></i>
            </button>
            <button
              (click)="changePage(page() + 1)"
              [disabled]="page() * pageSize >= total()"
              class="rounded px-3 py-1.5 text-sm text-muted hover:bg-gray-100 disabled:opacity-40"
            >
              <i class="pi pi-chevron-right"></i>
            </button>
          </div>
        </div>
      }
    </div>
  `,
})
export class PurchaseReturnsTabComponent implements OnInit {
  private readonly returnsService = inject(ReturnsService);

  returns = signal<PurchaseReturn[]>([]);
  loading = signal(false);
  loadError = signal(false);
  total = signal(0);
  page = signal(1);

  readonly pageSize = 25;

  pageEnd(): number {
    return Math.min(this.page() * this.pageSize, this.total());
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set(false);
    this.returnsService
      .getPurchaseReturns({ page: String(this.page()), page_size: String(this.pageSize) })
      .subscribe({
        next: (res) => {
          this.returns.set(res.items);
          this.total.set(res.total);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.loadError.set(true);
        },
      });
  }

  changePage(p: number): void {
    this.page.set(p);
    this.load();
  }
}
