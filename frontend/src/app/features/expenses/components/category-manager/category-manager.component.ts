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
import { ExpenseCategory } from '../../models/expense.model';

@Component({
  selector: 'app-category-manager',
  standalone: true,
  imports: [FormsModule, Dialog, Toast],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />
    <p-dialog
      header="Expense Categories"
      [visible]="visible()"
      (visibleChange)="onVisibleChange($event)"
      [modal]="true"
      [style]="{ width: '420px' }"
      [draggable]="false"
    >
      <div class="flex flex-col gap-4 py-2">
        <!-- Add category form -->
        <div class="flex gap-2">
          <input
            type="text"
            [(ngModel)]="newName"
            placeholder="Category name"
            class="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
            (keydown.enter)="addCategory()"
          />
          <button
            (click)="addCategory()"
            [disabled]="saving() || !newName.trim()"
            class="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50 min-h-[40px]"
          >
            {{ saving() ? '…' : 'Add' }}
          </button>
        </div>

        <!-- List -->
        @if (loading()) {
          <div class="flex justify-center py-4">
            <i class="pi pi-spinner pi-spin text-xl text-muted"></i>
          </div>
        } @else {
          <ul class="max-h-64 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-100">
            @for (cat of categories(); track cat.id) {
              <li class="flex items-center justify-between px-3 py-2 text-sm">
                <span class="font-medium text-gray-800">{{ cat.name }}</span>
              </li>
            } @empty {
              <li class="py-6 text-center text-sm text-muted">No categories yet.</li>
            }
          </ul>
        }

        <div class="flex justify-end pt-1">
          <button
            (click)="close()"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
          >
            Close
          </button>
        </div>
      </div>
    </p-dialog>
  `,
})
export class CategoryManagerComponent {
  private readonly expensesService = inject(ExpensesService);
  private readonly messageService = inject(MessageService);

  visible = input(false);
  closed = output<ExpenseCategory[]>();

  categories = signal<ExpenseCategory[]>([]);
  loading = signal(false);
  saving = signal(false);
  newName = '';

  private loaded = false;

  constructor() {
    effect(() => {
      if (this.visible() && !this.loaded) {
        this.loaded = true;
        this.load();
      }
    });
  }

  private load(): void {
    this.loading.set(true);
    this.expensesService.listCategories().subscribe({
      next: (cats) => {
        this.categories.set(cats);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  addCategory(): void {
    const name = this.newName.trim();
    if (!name) return;
    this.saving.set(true);
    this.expensesService.createCategory({ name }).subscribe({
      next: (cat) => {
        this.categories.update((list) => [...list, cat]);
        this.newName = '';
        this.saving.set(false);
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to add category' });
      },
    });
  }

  onVisibleChange(v: boolean): void {
    if (!v) this.close();
  }

  close(): void {
    this.closed.emit(this.categories());
  }
}
