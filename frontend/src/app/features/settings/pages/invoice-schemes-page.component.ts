import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  OnInit,
  computed,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  InvoiceSchemesService,
  InvoiceScheme,
  SchemeCreate,
  SchemeUpdate,
  SchemeType,
} from '../../../core/services/invoice-schemes.service';

@Component({
  selector: 'app-invoice-schemes-page',
  standalone: true,
  imports: [FormsModule, Toast, Dialog],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />

    <!-- Page Header -->
    <div class="mb-6">
      <div class="flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-gray-900">Invoice Schemes</h2>
          <p class="mt-1 text-sm text-gray-500">Manage invoice numbering schemes</p>
        </div>
        <button
          (click)="openAddDialog()"
          class="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md min-h-[44px]"
        >
          <i class="pi pi-plus text-sm"></i> Add Scheme
        </button>
      </div>
    </div>

    <!-- Schemes Table -->
    <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
      @if (loading()) {
        <div class="flex items-center justify-center py-16">
          <i class="pi pi-spinner pi-spin text-2xl text-muted"></i>
        </div>
      } @else if (schemes().length === 0) {
        <div class="flex flex-col items-center justify-center gap-3 py-16">
          <i class="pi pi-file-edit text-4xl text-muted"></i>
          <p class="text-sm text-muted">No invoice schemes yet. Create one to get started.</p>
        </div>
      } @else {
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead>
              <tr class="border-b border-gray-100 bg-gray-50">
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Name</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Prefix</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Type</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Digits</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Next Number</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Status</th>
                <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted">Preview</th>
                <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted">Actions</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100">
              @for (scheme of schemes(); track scheme.id) {
                <tr class="hover:bg-gray-50 transition-colors">
                  <td class="px-4 py-3 text-sm font-medium text-text">{{ scheme.name }}</td>
                  <td class="px-4 py-3 text-sm text-muted font-mono">{{ scheme.prefix || '—' }}</td>
                  <td class="px-4 py-3">
                    <span
                      class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
                      [class]="scheme.scheme_type === 'year' ? 'bg-blue-50 text-blue-700' : 'bg-gray-100 text-gray-600'"
                    >
                      {{ scheme.scheme_type === 'year' ? 'Year' : 'Blank' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-sm text-text">{{ scheme.total_digits }}</td>
                  <td class="px-4 py-3 text-sm text-text">{{ scheme.next_number }}</td>
                  <td class="px-4 py-3">
                    <span
                      class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium"
                      [class]="scheme.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-gray-100 text-gray-600'"
                    >
                      {{ scheme.is_active ? 'Active' : 'Inactive' }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-sm font-mono text-muted">{{ computePreview(scheme) }}</td>
                  <td class="px-4 py-3 text-right">
                    <button
                      (click)="openEditDialog(scheme)"
                      class="inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-secondary hover:bg-blue-50 transition-colors min-h-[44px]"
                    >
                      <i class="pi pi-pencil text-xs"></i> Edit
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>

    <!-- Add/Edit Dialog -->
    <p-dialog
      [(visible)]="dialogVisible"
      [header]="editingScheme() ? 'Edit Scheme' : 'Add Scheme'"
      [modal]="true"
      [style]="{ width: '480px' }"
      [closable]="true"
    >
      <div class="space-y-4 pt-2">
        <!-- Name -->
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Name <span class="text-danger">*</span></label>
          <input
            type="text"
            [(ngModel)]="form.name"
            placeholder="e.g. Default Invoice"
            maxlength="255"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>

        <!-- Type -->
        <div>
          <label class="mb-2 block text-xs font-medium text-muted">Type</label>
          <div class="flex gap-4">
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name="scheme_type"
                value="blank"
                [(ngModel)]="form.scheme_type"
                class="accent-emerald-600"
              />
              <span>Blank <span class="text-xs text-muted">(prefix + number)</span></span>
            </label>
            <label class="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="radio"
                name="scheme_type"
                value="year"
                [(ngModel)]="form.scheme_type"
                class="accent-emerald-600"
              />
              <span>Year <span class="text-xs text-muted">(prefix + year + number)</span></span>
            </label>
          </div>
        </div>

        <!-- Prefix -->
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Prefix</label>
          <input
            type="text"
            [(ngModel)]="form.prefix"
            placeholder="e.g. INV-"
            maxlength="20"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>

        <!-- Start Number -->
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Start Number</label>
          <input
            type="number"
            [(ngModel)]="form.start_number"
            min="1"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>

        <!-- Total Digits -->
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Total Digits (3–8)</label>
          <input
            type="number"
            [(ngModel)]="form.total_digits"
            min="3"
            max="8"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>

        <!-- Live Preview -->
        <div class="rounded-lg bg-gray-50 px-4 py-3">
          <span class="text-xs font-medium text-muted">Preview: </span>
          <span class="font-mono text-sm font-semibold text-text">{{ localPreview() }}</span>
        </div>
      </div>

      <ng-template #footer>
        <div class="flex justify-end gap-2 pt-4">
          <button
            (click)="dialogVisible = false"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors min-h-[44px]"
          >
            Cancel
          </button>
          <button
            (click)="saveScheme()"
            [disabled]="saving()"
            class="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50 transition-all min-h-[44px]"
          >
            @if (saving()) {
              <i class="pi pi-spinner pi-spin text-sm"></i>
            }
            {{ editingScheme() ? 'Save Changes' : 'Create Scheme' }}
          </button>
        </div>
      </ng-template>
    </p-dialog>
  `,
})
export class InvoiceSchemesPageComponent implements OnInit {
  private readonly svc = inject(InvoiceSchemesService);
  private readonly msg = inject(MessageService);

  schemes = signal<InvoiceScheme[]>([]);
  loading = signal(true);
  saving = signal(false);
  dialogVisible = false;
  editingScheme = signal<InvoiceScheme | null>(null);

  form: {
    name: string;
    scheme_type: SchemeType;
    prefix: string;
    start_number: number;
    total_digits: number;
  } = {
    name: '',
    scheme_type: 'blank',
    prefix: '',
    start_number: 1,
    total_digits: 5,
  };

  localPreview = computed(() => {
    const year = new Date().getFullYear();
    const n = this.form.start_number ?? 1;
    const digits = this.form.total_digits ?? 5;
    const padded = String(n).padStart(digits, '0');
    if (this.form.scheme_type === 'year') {
      return `${this.form.prefix}${year}-${padded}`;
    }
    return `${this.form.prefix}${padded}`;
  });

  ngOnInit(): void {
    this.loadSchemes();
  }

  computePreview(scheme: InvoiceScheme): string {
    const year = new Date().getFullYear();
    const padded = String(scheme.next_number).padStart(scheme.total_digits, '0');
    if (scheme.scheme_type === 'year') {
      return `${scheme.prefix}${year}-${padded}`;
    }
    return `${scheme.prefix}${padded}`;
  }

  loadSchemes(): void {
    this.loading.set(true);
    this.svc.getAll().subscribe({
      next: (res) => {
        this.schemes.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Error', detail: 'Failed to load schemes' });
        this.loading.set(false);
      },
    });
  }

  openAddDialog(): void {
    this.editingScheme.set(null);
    this.form = { name: '', scheme_type: 'blank', prefix: '', start_number: 1, total_digits: 5 };
    this.dialogVisible = true;
  }

  openEditDialog(scheme: InvoiceScheme): void {
    this.editingScheme.set(scheme);
    this.form = {
      name: scheme.name,
      scheme_type: scheme.scheme_type,
      prefix: scheme.prefix,
      start_number: scheme.start_number,
      total_digits: scheme.total_digits,
    };
    this.dialogVisible = true;
  }

  saveScheme(): void {
    if (!this.form.name.trim()) {
      this.msg.add({ severity: 'warn', summary: 'Validation', detail: 'Name is required' });
      return;
    }

    this.saving.set(true);
    const editing = this.editingScheme();

    if (editing) {
      const data: SchemeUpdate = {
        name: this.form.name,
        scheme_type: this.form.scheme_type,
        prefix: this.form.prefix,
        total_digits: this.form.total_digits,
      };
      this.svc.update(editing.id, data).subscribe({
        next: (updated) => {
          this.schemes.update((list) => list.map((s) => (s.id === updated.id ? updated : s)));
          this.msg.add({ severity: 'success', summary: 'Saved', detail: 'Scheme updated' });
          this.dialogVisible = false;
          this.saving.set(false);
        },
        error: () => {
          this.msg.add({ severity: 'error', summary: 'Error', detail: 'Failed to update scheme' });
          this.saving.set(false);
        },
      });
    } else {
      const data: SchemeCreate = {
        name: this.form.name,
        scheme_type: this.form.scheme_type,
        prefix: this.form.prefix,
        start_number: this.form.start_number,
        total_digits: this.form.total_digits,
      };
      this.svc.create(data).subscribe({
        next: (created) => {
          this.schemes.update((list) => [...list, created]);
          this.msg.add({ severity: 'success', summary: 'Created', detail: 'Scheme created' });
          this.dialogVisible = false;
          this.saving.set(false);
        },
        error: () => {
          this.msg.add({ severity: 'error', summary: 'Error', detail: 'Failed to create scheme' });
          this.saving.set(false);
        },
      });
    }
  }
}
