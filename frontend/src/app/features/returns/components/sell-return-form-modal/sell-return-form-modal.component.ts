import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  output,
  input,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { Dialog } from 'primeng/dialog';
import { Toast } from 'primeng/toast';
import { ReturnsService } from '../../services/returns.service';
import { SellReturn } from '../../models/return.model';

@Component({
  selector: 'app-sell-return-form-modal',
  standalone: true,
  imports: [FormsModule, Dialog, Toast],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <p-dialog
      header="Log Sell Return"
      [visible]="visible()"
      (visibleChange)="onVisibleChange($event)"
      [modal]="true"
      [style]="{ width: '480px' }"
      [draggable]="false"
    >
      <form (ngSubmit)="submit()" #f="ngForm" class="flex flex-col gap-4 py-2">
        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700">Sale ID <span class="text-red-500">*</span></label>
          <input
            type="text"
            name="sale_id"
            [(ngModel)]="form.sale_id"
            required
            placeholder="Paste sale UUID"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-gray-700">Return Date <span class="text-red-500">*</span></label>
          <input
            type="date"
            name="return_date"
            [(ngModel)]="form.return_date"
            required
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">Total Amount <span class="text-red-500">*</span></label>
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
            [disabled]="saving() || !f.valid"
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

  form = {
    sale_id: '',
    return_date: new Date().toISOString().slice(0, 10),
    total_amount: '',
    amount_paid: '0',
    ref_no: '',
    notes: '',
  };

  onVisibleChange(v: boolean): void {
    if (!v) this.close();
  }

  close(): void {
    this.resetForm();
    this.closed.emit();
  }

  submit(): void {
    if (!this.form.sale_id || !this.form.return_date || !this.form.total_amount) return;
    this.saving.set(true);
    this.returnsService
      .createSellReturn(this.form.sale_id, {
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
          this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to save return' });
        },
      });
  }

  private resetForm(): void {
    this.form = {
      sale_id: '',
      return_date: new Date().toISOString().slice(0, 10),
      total_amount: '',
      amount_paid: '0',
      ref_no: '',
      notes: '',
    };
  }
}
