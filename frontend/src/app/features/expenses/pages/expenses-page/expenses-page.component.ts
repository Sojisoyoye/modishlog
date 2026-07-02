import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  computed,
  OnInit,
} from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ExpensesService } from '../../services/expenses.service';
import { ExpenseCategory, ExpenseRead } from '../../models/expense.model';
import { ExpenseFormModalComponent } from '../../components/expense-form-modal/expense-form-modal.component';
import { CategoryManagerComponent } from '../../components/category-manager/category-manager.component';

@Component({
  selector: 'app-expenses-page',
  standalone: true,
  imports: [DecimalPipe, DatePipe, ExpenseFormModalComponent, CategoryManagerComponent, Toast],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />

    <!-- Header -->
    <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
          <i class="pi pi-wallet text-lg"></i>
        </div>
        <div>
          <h2 class="text-2xl font-bold text-text">Expenses</h2>
          <p class="mt-0.5 text-sm text-muted">Track all business expenses</p>
        </div>
      </div>
      <div class="flex gap-2 shrink-0">
        <button
          (click)="showCategoryManager.set(true)"
          class="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
        >
          <i class="pi pi-tags text-sm"></i> Manage Categories
        </button>
        <button
          (click)="openCreate()"
          class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 min-h-[40px]"
        >
          <i class="pi pi-plus text-sm"></i> Add Expense
        </button>
      </div>
    </div>

    <!-- Summary bar -->
    <div class="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-muted">Total Records</p>
        <p class="mt-1 text-2xl font-bold text-text">{{ total() }}</p>
      </div>
      <div class="rounded-xl border border-gray-100 bg-white px-4 py-3 shadow-sm">
        <p class="text-xs font-semibold uppercase tracking-wider text-muted">Page Total (USD)</p>
        <p class="mt-1 text-2xl font-bold text-emerald-600">
          \${{ totalUsd() | number: '1.2-2' }}
        </p>
      </div>
    </div>

    <!-- Error -->
    @if (loadError()) {
      <div class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        <i class="pi pi-exclamation-circle"></i>
        Failed to load expenses.
        <button (click)="load()" class="ml-auto underline hover:no-underline">Retry</button>
      </div>
    }

    <!-- Table -->
    <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
      <div class="overflow-x-auto">
        @if (loading()) {
          <div class="flex items-center justify-center py-16">
            <i class="pi pi-spinner pi-spin text-2xl text-muted"></i>
          </div>
        } @else {
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <caption class="sr-only">Expenses list</caption>
            <thead>
              <tr class="bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Date</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Ref No</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Category</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Note</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Payment</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Amount (USD)</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Amount (NGN)</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (e of expenses(); track e.id) {
                <tr class="transition-colors hover:bg-gray-50">
                  <td class="px-4 py-3 text-gray-700">{{ e.expense_date | date: 'mediumDate' }}</td>
                  <td class="px-4 py-3 font-mono text-xs text-gray-500">{{ e.ref_no ?? '—' }}</td>
                  <td class="px-4 py-3">
                    @if (e.category_name) {
                      <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                        {{ e.category_name }}
                      </span>
                    } @else {
                      <span class="text-muted">—</span>
                    }
                  </td>
                  <td class="max-w-[200px] truncate px-4 py-3 text-gray-700">{{ e.note ?? '—' }}</td>
                  <td class="px-4 py-3 text-gray-500">{{ e.payment_method ?? '—' }}</td>
                  <td class="px-4 py-3 text-right font-medium text-emerald-700">\${{ +e.amount_usd | number: '1.2-2' }}</td>
                  <td class="px-4 py-3 text-right text-gray-700">₦{{ +e.amount_ngn | number: '1.0-0' }}</td>
                  <td class="px-4 py-3 text-right">
                    <button
                      (click)="openEdit(e)"
                      class="mr-1 rounded px-2 py-1 text-xs text-muted hover:bg-gray-100 hover:text-primary"
                      aria-label="Edit"
                    >
                      <i class="pi pi-pencil"></i> Edit
                    </button>
                    <button
                      (click)="deleteExpense(e)"
                      class="rounded px-2 py-1 text-xs text-muted hover:bg-red-50 hover:text-red-600"
                      aria-label="Delete"
                    >
                      <i class="pi pi-trash"></i>
                    </button>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="8" class="py-12 text-center text-sm text-muted">No expenses found.</td>
                </tr>
              }
            </tbody>
          </table>
        }
      </div>

      <!-- Pagination -->
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

    <!-- Modals -->
    <app-expense-form-modal
      [visible]="showForm()"
      [editId]="editId()"
      [editData]="editData()"
      [categories]="categories()"
      (saved)="onSaved($event)"
      (closed)="closeForm()"
    />

    <app-category-manager
      [visible]="showCategoryManager()"
      (closed)="onCategoriesClosed($event)"
    />
  `,
})
export class ExpensesPageComponent implements OnInit {
  private readonly expensesService = inject(ExpensesService);
  private readonly messageService = inject(MessageService);

  expenses = signal<ExpenseRead[]>([]);
  categories = signal<ExpenseCategory[]>([]);
  loading = signal(false);
  loadError = signal(false);
  total = signal(0);
  page = signal(1);

  showForm = signal(false);
  showCategoryManager = signal(false);
  editId = signal<string | null>(null);
  editData = signal<ExpenseRead | null>(null);

  readonly pageSize = 25;

  totalUsd = computed(() => this.expenses().reduce((s, e) => s + +e.amount_usd, 0));

  pageEnd(): number {
    return Math.min(this.page() * this.pageSize, this.total());
  }

  ngOnInit(): void {
    this.load();
    this.loadCategories();
  }

  load(): void {
    this.loading.set(true);
    this.loadError.set(false);
    this.expensesService
      .listExpenses({ page: String(this.page()), page_size: String(this.pageSize) })
      .subscribe({
        next: (res) => {
          this.expenses.set(res.items);
          this.total.set(res.total);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.loadError.set(true);
        },
      });
  }

  private loadCategories(): void {
    this.expensesService.listCategories().subscribe({
      next: (cats) => this.categories.set(cats),
      error: () => {},
    });
  }

  changePage(p: number): void {
    this.page.set(p);
    this.load();
  }

  openCreate(): void {
    this.editId.set(null);
    this.editData.set(null);
    this.showForm.set(true);
  }

  openEdit(e: ExpenseRead): void {
    this.editId.set(e.id);
    this.editData.set(e);
    this.showForm.set(true);
  }

  closeForm(): void {
    this.showForm.set(false);
    this.editId.set(null);
    this.editData.set(null);
  }

  onSaved(e: ExpenseRead): void {
    this.showForm.set(false);
    this.editId.set(null);
    this.editData.set(null);
    const idx = this.expenses().findIndex((x) => x.id === e.id);
    if (idx >= 0) {
      this.expenses.update((list) => list.map((x) => (x.id === e.id ? e : x)));
    } else {
      this.expenses.update((list) => [e, ...list]);
      this.total.update((t) => t + 1);
    }
  }

  deleteExpense(e: ExpenseRead): void {
    if (!window.confirm('Delete this expense? This cannot be undone.')) return;
    this.expensesService.deleteExpense(e.id).subscribe({
      next: () => {
        this.expenses.update((list) => list.filter((x) => x.id !== e.id));
        this.total.update((t) => t - 1);
        this.messageService.add({ severity: 'success', summary: 'Deleted', detail: 'Expense removed' });
      },
      error: () => {
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to delete expense' });
      },
    });
  }

  onCategoriesClosed(cats: ExpenseCategory[]): void {
    this.categories.set(cats);
    this.showCategoryManager.set(false);
  }
}
