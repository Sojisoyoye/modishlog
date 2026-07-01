import {
  Component,
  ChangeDetectionStrategy,
  inject,
  signal,
  OnInit,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  CustomersService,
  Customer,
  CustomerCreate,
  CustomerUpdate,
} from '../../services/customers.service';

type ActiveFilter = 'all' | 'active' | 'inactive';

@Component({
  selector: 'app-customers-page',
  standalone: true,
  imports: [FormsModule, DecimalPipe, Toast, Dialog],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />

    <div>
      <!-- Header -->
      <div class="mb-6 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
            <i class="pi pi-users text-lg"></i>
          </div>
          <div>
            <h2 class="text-2xl font-bold text-text">Customers</h2>
            <p class="mt-0.5 text-sm text-muted">Manage your customers</p>
          </div>
        </div>
        <button
          (click)="openAddDialog()"
          class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md min-h-[44px]"
        >
          <i class="pi pi-plus text-sm"></i> Add Customer
        </button>
      </div>

      <!-- Search + filter bar -->
      <div class="mb-4 flex flex-wrap gap-3">
        <div class="relative flex-1 min-w-[200px]">
          <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"></i>
          <input
            type="text"
            [(ngModel)]="searchTerm"
            (ngModelChange)="onSearch()"
            placeholder="Search customers..."
            class="w-full rounded-lg border border-gray-300 py-2.5 pl-9 pr-3 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>
        <div class="flex gap-1 rounded-lg border border-gray-300 p-1">
          @for (f of filterOptions; track f.value) {
            <button
              (click)="setActiveFilter(f.value)"
              class="rounded px-3 py-1.5 text-sm font-medium transition-colors min-h-[36px]"
              [class]="activeFilter() === f.value
                ? 'bg-primary text-white'
                : 'text-muted hover:text-text'"
            >
              {{ f.label }}
            </button>
          }
        </div>
      </div>

      <!-- Customers Table -->
      <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
        <div class="overflow-x-auto">
          @if (loading()) {
            <div class="flex items-center justify-center py-16">
              <i class="pi pi-spinner pi-spin text-2xl text-muted"></i>
            </div>
          } @else {
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Customers list</caption>
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Name</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Email</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Contact</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">City</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Country</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Credit Limit</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Balance</th>
                  <th class="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (c of customers(); track c.id) {
                  <tr class="transition-colors hover:bg-gray-50">
                    <td class="px-4 py-3 font-semibold text-gray-900">{{ c.name }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ c.email ?? '—' }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ c.contact_number ?? '—' }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ c.city ?? '—' }}</td>
                    <td class="px-4 py-3 text-sm text-gray-500">{{ c.country ?? '—' }}</td>
                    <td class="px-4 py-3 text-right font-medium">
                      {{ c.credit_limit != null ? (c.credit_limit | number: '1.2-2') : '—' }}
                    </td>
                    <td class="px-4 py-3 text-right font-medium">
                      {{ c.opening_balance | number: '1.2-2' }}
                    </td>
                    <td class="px-4 py-3 text-center">
                      <span
                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                        [class]="c.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'"
                      >
                        {{ c.is_active ? 'Active' : 'Inactive' }}
                      </span>
                    </td>
                    <td class="px-4 py-3 text-right">
                      <button
                        [attr.data-testid]="'edit-customer-' + c.name"
                        (click)="openEditDialog(c)"
                        class="mr-2 inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 text-muted transition-colors hover:bg-gray-100 hover:text-secondary"
                        title="Edit"
                      >
                        <i class="pi pi-pencil text-xs"></i>
                      </button>
                      <button
                        (click)="toggleActive(c)"
                        class="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 text-muted transition-colors hover:bg-gray-100 hover:text-text"
                        [title]="c.is_active ? 'Deactivate' : 'Activate'"
                      >
                        <i class="pi pi-power-off text-xs"></i>
                      </button>
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="9" class="px-4 py-16 text-center">
                      <div class="flex flex-col items-center gap-3">
                        @if (searchTerm || activeFilter() !== 'all') {
                          <i class="pi pi-search text-2xl text-muted"></i>
                          <p class="text-sm text-muted">No customers match your filters.</p>
                        } @else {
                          <div class="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50">
                            <i class="pi pi-users text-3xl text-emerald-300"></i>
                          </div>
                          <p class="font-semibold text-gray-900">No customers yet</p>
                          <p class="text-sm text-muted">Add your first customer to get started.</p>
                          <button
                            (click)="openAddDialog()"
                            class="mt-1 flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 min-h-[44px]"
                          >
                            <i class="pi pi-plus text-xs"></i> Add Customer
                          </button>
                        }
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </div>
        @if (total() > 0) {
          <div class="border-t border-gray-100 px-4 py-2 text-xs text-muted">
            Showing {{ customers().length }} of {{ total() }} customers
          </div>
        }
      </div>
    </div>

    <!-- Add / Edit Dialog -->
    <p-dialog
      [header]="editingCustomer() ? 'Edit Customer' : 'Add Customer'"
      [(visible)]="showForm"
      [modal]="true"
      [style]="{ width: '600px' }"
      [breakpoints]="{ '768px': '95vw' }"
    >
      <div class="space-y-4">
        <!-- Identity -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div class="sm:col-span-2">
            <label class="mb-1 block text-xs font-medium text-muted">
              Customer Name <span class="text-danger">*</span>
            </label>
            <input
              type="text"
              [(ngModel)]="form.name"
              placeholder="Customer name"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Email Address</label>
            <input
              type="email"
              [(ngModel)]="form.email"
              placeholder="Email address"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Contact Number</label>
            <input
              type="tel"
              [(ngModel)]="form.contact_number"
              placeholder="Contact number"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Alternate Number</label>
            <input
              type="tel"
              [(ngModel)]="form.alternate_number"
              placeholder="Alternate number"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Tax Number</label>
            <input
              type="text"
              [(ngModel)]="form.tax_number"
              placeholder="TIN / VAT number"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Customer Group</label>
            <input
              type="text"
              [(ngModel)]="form.customer_group"
              placeholder="e.g. Wholesale, Retail"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Address -->
        <div>
          <p class="mb-2 text-xs font-semibold uppercase text-muted">Address</p>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div class="sm:col-span-2">
              <textarea
                [(ngModel)]="form.address"
                rows="2"
                placeholder="Street address"
                class="w-full resize-none rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
              ></textarea>
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.city"
                placeholder="City"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.state"
                placeholder="State"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.country"
                placeholder="Country"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <input
                type="text"
                [(ngModel)]="form.zip_code"
                placeholder="ZIP / Postal code"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
          </div>
        </div>

        <!-- Payment Terms & Financials -->
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Pay Term</label>
            <input
              type="number"
              [(ngModel)]="form.pay_term_number"
              placeholder="e.g. 30"
              min="1"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Term Type</label>
            <select
              [(ngModel)]="form.pay_term_type"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            >
              <option value="">—</option>
              <option value="days">Days</option>
              <option value="months">Months</option>
            </select>
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Opening Balance</label>
            <input
              type="number"
              [(ngModel)]="form.opening_balance"
              min="0"
              step="0.01"
              placeholder="0.00"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1 block text-xs font-medium text-muted">Credit Limit</label>
            <input
              type="number"
              [(ngModel)]="form.credit_limit"
              min="0"
              step="0.01"
              placeholder="Unlimited"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Active toggle -->
        <label class="flex cursor-pointer items-center gap-3">
          <input type="checkbox" [(ngModel)]="form.is_active" class="h-4 w-4 rounded" />
          <span class="text-sm font-medium text-text">Active</span>
        </label>

        <!-- Notes -->
        <div>
          <label class="mb-1 block text-xs font-medium text-muted">Notes</label>
          <textarea
            [(ngModel)]="form.notes"
            rows="2"
            placeholder="Internal notes about this customer"
            class="w-full resize-none rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          ></textarea>
        </div>

        <div class="flex gap-3">
          <button
            type="button"
            (click)="showForm = false"
            class="flex flex-1 items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-semibold text-gray-700 shadow-sm transition-all hover:bg-gray-50 min-h-[44px]"
          >
            Cancel
          </button>
          <button
            (click)="saveCustomer()"
            [disabled]="saving() || !form.name"
            class="flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50 min-h-[44px]"
          >
            @if (saving()) {
              <i class="pi pi-spinner pi-spin text-sm"></i> Saving...
            } @else {
              <i class="pi pi-check text-sm"></i> Save Customer
            }
          </button>
        </div>
      </div>
    </p-dialog>
  `,
})
export class CustomersPageComponent implements OnInit {
  private readonly customersService = inject(CustomersService);
  private readonly messageService = inject(MessageService);

  customers = signal<Customer[]>([]);
  total = signal(0);
  loading = signal(false);
  saving = signal(false);
  activeFilter = signal<ActiveFilter>('all');
  editingCustomer = signal<Customer | null>(null);

  searchTerm = '';
  showForm = false;

  form: CustomerCreate = this.emptyForm();

  readonly filterOptions: { label: string; value: ActiveFilter }[] = [
    { label: 'All', value: 'all' },
    { label: 'Active', value: 'active' },
    { label: 'Inactive', value: 'inactive' },
  ];

  ngOnInit(): void {
    this.loadCustomers();
  }

  loadCustomers(): void {
    const params: Record<string, string> = { page: '1', page_size: '25' };
    if (this.searchTerm) params['search'] = this.searchTerm;
    if (this.activeFilter() === 'active') params['is_active'] = 'true';
    if (this.activeFilter() === 'inactive') params['is_active'] = 'false';

    this.loading.set(true);
    this.customersService.getCustomers(params).subscribe({
      next: (resp) => {
        this.customers.set(resp.items);
        this.total.set(resp.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to load customers' });
      },
    });
  }

  onSearch(): void {
    this.loadCustomers();
  }

  setActiveFilter(value: ActiveFilter): void {
    this.activeFilter.set(value);
    this.loadCustomers();
  }

  openAddDialog(): void {
    this.editingCustomer.set(null);
    this.form = this.emptyForm();
    this.showForm = true;
  }

  openEditDialog(c: Customer): void {
    this.editingCustomer.set(c);
    this.form = {
      name: c.name,
      contact_number: c.contact_number,
      alternate_number: c.alternate_number,
      email: c.email,
      address: c.address,
      city: c.city,
      state: c.state,
      country: c.country,
      zip_code: c.zip_code,
      tax_number: c.tax_number,
      pay_term_number: c.pay_term_number,
      pay_term_type: c.pay_term_type,
      opening_balance: c.opening_balance,
      credit_limit: c.credit_limit,
      is_active: c.is_active,
      customer_group: c.customer_group,
      notes: c.notes,
    };
    this.showForm = true;
  }

  saveCustomer(): void {
    if (!this.form.name) return;
    this.saving.set(true);
    const existing = this.editingCustomer();

    const payload: CustomerCreate = {
      ...this.form,
      pay_term_type: this.form.pay_term_type || null,
    };

    const req$ = existing
      ? this.customersService.updateCustomer(existing.id, payload)
      : this.customersService.createCustomer(payload);

    req$.subscribe({
      next: () => {
        this.saving.set(false);
        this.showForm = false;
        this.messageService.add({
          severity: 'success',
          summary: existing ? 'Customer updated' : 'Customer added',
          detail: existing ? 'Customer updated successfully' : `${this.form.name} added`,
        });
        this.loadCustomers();
      },
      error: () => {
        this.saving.set(false);
        this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to save customer' });
      },
    });
  }

  toggleActive(c: Customer): void {
    const update: CustomerUpdate = { is_active: !c.is_active };
    this.customersService.updateCustomer(c.id, update).subscribe({
      next: () => this.loadCustomers(),
    });
  }

  private emptyForm(): CustomerCreate {
    return {
      name: '',
      contact_number: null,
      alternate_number: null,
      email: null,
      address: null,
      city: null,
      state: null,
      country: null,
      zip_code: null,
      tax_number: null,
      pay_term_number: null,
      pay_term_type: null,
      opening_balance: 0,
      credit_limit: null,
      is_active: true,
      customer_group: null,
      notes: null,
    };
  }
}
