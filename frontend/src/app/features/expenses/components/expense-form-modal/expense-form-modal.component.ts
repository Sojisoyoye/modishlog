import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  input,
  output,
  effect,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { Dialog } from 'primeng/dialog';
import { Toast } from 'primeng/toast';
import { ExpensesService } from '../../services/expenses.service';
import { ExpenseCategory, ExpenseRead } from '../../models/expense.model';

@Component({
  selector: 'app-expense-form-modal',
  standalone: true,
  imports: [FormsModule, Dialog, Toast],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <p-dialog
      [header]="editId() ? 'Edit Expense' : 'Add Expense'"
      [visible]="visible()"
      (visibleChange)="onVisibleChange($event)"
      [modal]="true"
      [style]="{ width: '520px' }"
      [breakpoints]="{ '640px': '95vw' }"
      [draggable]="false"
    >
      <form (ngSubmit)="submit()" #f="ngForm" class="flex flex-col gap-4 py-2">

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label for="expense-amount-ngn" class="mb-1 block text-sm font-medium text-gray-700">
              Amount (NGN) <span class="text-red-500">*</span>
            </label>
            <input
              id="expense-amount-ngn"
              type="number"
              name="amount_ngn"
              [(ngModel)]="form.amount_ngn"
              required
              min="0"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="expense-amount-usd" class="mb-1 block text-sm font-medium text-gray-700">
              Amount (USD) <span class="text-red-500">*</span>
            </label>
            <input
              id="expense-amount-usd"
              type="number"
              name="amount_usd"
              [(ngModel)]="form.amount_usd"
              required
              min="0"
              step="0.000001"
              placeholder="0.000000"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label for="expense-date" class="mb-1 block text-sm font-medium text-gray-700">
              Expense Date <span class="text-red-500">*</span>
            </label>
            <input
              id="expense-date"
              type="date"
              name="expense_date"
              [(ngModel)]="form.expense_date"
              required
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
          <div>
            <label for="expense-fx-rate" class="mb-1 block text-sm font-medium text-gray-700">FX Rate</label>
            <input
              id="expense-fx-rate"
              type="number"
              name="fx_rate"
              [(ngModel)]="form.fx_rate"
              min="0"
              step="0.01"
              placeholder="e.g. 1550"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label for="expense-category" class="mb-1 block text-sm font-medium text-gray-700">Category</label>
            <select
              id="expense-category"
              name="category_id"
              [(ngModel)]="form.category_id"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            >
              <option value="">— None —</option>
              @for (cat of categories(); track cat.id) {
                <option [value]="cat.id">{{ cat.name }}</option>
              }
            </select>
          </div>
          <div>
            <label for="expense-payment-method" class="mb-1 block text-sm font-medium text-gray-700">Payment Method</label>
            <input
              id="expense-payment-method"
              type="text"
              name="payment_method"
              [(ngModel)]="form.payment_method"
              placeholder="e.g. bank_transfer"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </div>
        </div>

        <div>
          <label for="expense-ref-no" class="mb-1 block text-sm font-medium text-gray-700">Ref No</label>
          <input
            id="expense-ref-no"
            type="text"
            name="ref_no"
            [(ngModel)]="form.ref_no"
            placeholder="e.g. EXP-001"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          />
        </div>

        <div>
          <label for="expense-note" class="mb-1 block text-sm font-medium text-gray-700">Note</label>
          <textarea
            id="expense-note"
            name="note"
            [(ngModel)]="form.note"
            rows="2"
            placeholder="Optional note"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
          ></textarea>
        </div>

        <div class="flex flex-col gap-3 pt-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            (click)="close()"
            class="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px] sm:w-auto"
          >
            Cancel
          </button>
          <button
            type="submit"
            [disabled]="saving() || !f.valid"
            class="w-full rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50 min-h-[40px] sm:w-auto"
          >
            {{ saving() ? 'Saving…' : 'Save Expense' }}
          </button>
        </div>
      </form>
    </p-dialog>
  `,
})
export class ExpenseFormModalComponent {
  private readonly expensesService = inject(ExpensesService);
  private readonly messageService = inject(MessageService);

  visible = input(false);
  editId = input<string | null>(null);
  editData = input<ExpenseRead | null>(null);
  categories = input<ExpenseCategory[]>([]);

  saved = output<ExpenseRead>();
  closed = output<void>();

  saving = signal(false);

  form = this._blankForm();

  constructor() {
    effect(() => {
      const data = this.editData();
      if (data) {
        this.form = {
          amount_ngn: data.amount_ngn,
          amount_usd: data.amount_usd,
          fx_rate: data.fx_rate ?? '',
          expense_date: data.expense_date,
          category_id: data.category_id ?? '',
          payment_method: data.payment_method ?? '',
          ref_no: data.ref_no ?? '',
          note: data.note ?? '',
        };
      } else if (this.visible()) {
        this.form = this._blankForm();
      }
    });
  }

  private _blankForm() {
    return {
      amount_ngn: '',
      amount_usd: '',
      fx_rate: '',
      expense_date: new Date().toISOString().slice(0, 10),
      category_id: '',
      payment_method: '',
      ref_no: '',
      note: '',
    };
  }

  onVisibleChange(v: boolean): void {
    if (!v) this.close();
  }

  close(): void {
    this.form = this._blankForm();
    this.closed.emit();
  }

  submit(): void {
    if (!this.form.amount_ngn || !this.form.amount_usd || !this.form.expense_date) return;
    this.saving.set(true);

    const payload = {
      amount_ngn: String(this.form.amount_ngn),
      amount_usd: String(this.form.amount_usd),
      fx_rate: this.form.fx_rate ? String(this.form.fx_rate) : null,
      expense_date: this.form.expense_date,
      category_id: this.form.category_id || null,
      payment_method: this.form.payment_method || null,
      ref_no: this.form.ref_no || null,
      note: this.form.note || null,
    };

    const id = this.editId();
    const req$ = id
      ? this.expensesService.updateExpense(id, payload)
      : this.expensesService.createExpense(payload);

    req$.subscribe({
      next: (result) => {
        this.saving.set(false);
        this.form = this._blankForm();
        this.saved.emit(result);
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to save expense' });
      },
    });
  }
}
