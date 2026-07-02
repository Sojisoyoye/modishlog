import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  output,
  input,
  effect,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Dialog } from 'primeng/dialog';
import { Toast } from 'primeng/toast';
import { ReturnsService } from '../../services/returns.service';
import { Sale, SellReturn } from '../../models/return.model';

@Component({
  selector: 'app-sell-return-form-modal',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe, Dialog, Toast],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <p-dialog
      header="Log Sell Return"
      [visible]="visible()"
      (visibleChange)="onVisibleChange($event)"
      [modal]="true"
      [style]="{ width: '520px' }"
      [breakpoints]="{ '640px': '95vw' }"
      [draggable]="false"
    >
      <form (ngSubmit)="submit()" #f="ngForm" class="flex flex-col gap-4 py-2">

        <!-- Sale search -->
        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700">
            Sale <span class="text-red-500">*</span>
          </label>
          <div class="relative">
            <input
              type="text"
              [(ngModel)]="saleSearch"
              name="sale_search"
              (ngModelChange)="filterSales($event)"
              placeholder="Search by date, customer or ID…"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
            @if (loadingSales()) {
              <i class="pi pi-spinner pi-spin absolute right-3 top-2.5 text-sm text-muted"></i>
            }
          </div>

          @if (filteredSales().length > 0 && !selectedSaleId()) {
            <ul class="mt-1 max-h-48 overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-md">
              @for (s of filteredSales(); track s.id) {
                <li>
                  <button
                    type="button"
                    (click)="selectSale(s)"
                    class="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-gray-50"
                  >
                    <span class="font-medium text-gray-800">
                      {{ s.sale_date | date: 'mediumDate' }}
                      @if (s.customer_name) { — {{ s.customer_name }} }
                    </span>
                    <span class="ml-4 shrink-0 font-mono text-xs text-muted">
                      ₦{{ +s.total_amount | number: '1.0-0' }}
                    </span>
                  </button>
                </li>
              }
            </ul>
          }

          @if (selectedSaleId()) {
            <div class="mt-1 flex items-center justify-between rounded-lg bg-primary/5 px-3 py-2 text-sm">
              <span class="text-primary font-medium">
                <i class="pi pi-check-circle mr-1"></i>
                {{ selectedSaleLabel() }}
              </span>
              <button type="button" (click)="clearSale()" class="text-muted hover:text-red-500 text-xs">
                Change
              </button>
            </div>
          }
        </div>

        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700">
            Return Date <span class="text-red-500">*</span>
          </label>
          <input
            type="date"
            name="return_date"
            [(ngModel)]="form.return_date"
            required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">
              Total Amount <span class="text-red-500">*</span>
            </label>
            <input
              type="number"
              name="total_amount"
              [(ngModel)]="form.total_amount"
              required
              min="0.000001"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">Amount Paid</label>
            <input
              type="number"
              name="amount_paid"
              [(ngModel)]="form.amount_paid"
              min="0"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700">Ref No</label>
          <input
            type="text"
            name="ref_no"
            [(ngModel)]="form.ref_no"
            placeholder="e.g. RET-001"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>

        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700">Notes</label>
          <textarea
            name="notes"
            [(ngModel)]="form.notes"
            rows="2"
            placeholder="Optional notes"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          ></textarea>
        </div>

        <div class="flex justify-end gap-2 pt-2">
          <button
            type="button"
            (click)="close()"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
          >
            Cancel
          </button>
          <button
            type="submit"
            [disabled]="saving() || !f.valid || !selectedSaleId()"
            class="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50 min-h-[40px]"
          >
            {{ saving() ? 'Saving…' : 'Save Return' }}
          </button>
        </div>
      </form>
    </p-dialog>
  `,
})
export class SellReturnFormModalComponent {
  private readonly returnsService = inject(ReturnsService);
  private readonly messageService = inject(MessageService);

  visible = input(false);
  saved = output<SellReturn>();
  closed = output<void>();

  saving = signal(false);
  loadingSales = signal(false);
  allSales = signal<Sale[]>([]);
  filteredSales = signal<Sale[]>([]);
  saleSearch = '';
  selectedSale = signal<Sale | null>(null);
  selectedSaleId = signal('');

  form = {
    return_date: new Date().toISOString().slice(0, 10),
    total_amount: '',
    amount_paid: '0',
    ref_no: '',
    notes: '',
  };

  constructor() {
    effect(() => {
      if (this.visible()) {
        this.loadSales();
      }
    });
  }

  selectedSaleLabel(): string {
    const s = this.selectedSale();
    if (!s) return '';
    const label = `${s.sale_date}${s.customer_name ? ' — ' + s.customer_name : ''}`;
    return label;
  }

  private loadSales(): void {
    this.loadingSales.set(true);
    this.returnsService.getRecentSales(50).subscribe({
      next: (res) => {
        this.allSales.set(res.items);
        this.filteredSales.set(res.items);
        this.loadingSales.set(false);
      },
      error: () => this.loadingSales.set(false),
    });
  }

  filterSales(query: string): void {
    const q = query.toLowerCase();
    this.filteredSales.set(
      this.allSales().filter(
        (s) =>
          s.id.toLowerCase().includes(q) ||
          s.sale_date.includes(q) ||
          (s.customer_name?.toLowerCase().includes(q) ?? false),
      ),
    );
  }

  selectSale(s: Sale): void {
    this.selectedSaleId.set(s.id);
    this.selectedSale.set(s);
    this.saleSearch = '';
    this.filteredSales.set([]);
  }

  clearSale(): void {
    this.selectedSaleId.set('');
    this.selectedSale.set(null);
    this.filteredSales.set(this.allSales());
    this.saleSearch = '';
  }

  onVisibleChange(v: boolean): void {
    if (!v) this.close();
  }

  close(): void {
    this.resetForm();
    this.closed.emit();
  }

  submit(): void {
    if (!this.selectedSaleId() || !this.form.return_date || !this.form.total_amount) return;
    this.saving.set(true);
    this.returnsService
      .createSellReturn(this.selectedSaleId(), {
        return_date: this.form.return_date,
        total_amount: this.form.total_amount,
        amount_paid: this.form.amount_paid || '0',
        ref_no: this.form.ref_no || null,
        notes: this.form.notes || null,
      })
      .subscribe({
        next: (result) => {
          this.saving.set(false);
          this.resetForm();
          this.saved.emit(result);
        },
        error: () => {
          this.saving.set(false);
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to save return',
          });
        },
      });
  }

  private resetForm(): void {
    this.form = {
      return_date: new Date().toISOString().slice(0, 10),
      total_amount: '',
      amount_paid: '0',
      ref_no: '',
      notes: '',
    };
    this.selectedSaleId.set('');
    this.selectedSale.set(null);
    this.saleSearch = '';
    this.filteredSales.set([]);
  }
}
