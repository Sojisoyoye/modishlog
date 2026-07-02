import {
  Component,
  ChangeDetectionStrategy,
  DestroyRef,
  inject,
  signal,
  OnInit,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { Dialog } from 'primeng/dialog';
import {
  LocationsService,
  Location,
  LocationCreate,
  LocationType,
} from '../../../core/services/locations.service';

@Component({
  selector: 'app-locations-page',
  standalone: true,
  imports: [FormsModule, Toast, Dialog],
  providers: [MessageService],
  template: `
    <p-toast />

    <div>
      <!-- Page Header -->
      <div class="mb-6 flex items-center justify-between">
        <div>
          <h2 class="text-2xl font-bold text-gray-900">Locations</h2>
          <p class="mt-1 text-sm text-gray-500">Manage your business locations and branches</p>
        </div>
        <button
          data-testid="add-location-btn"
          (click)="openAddDialog()"
          class="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md min-h-[44px]"
        >
          <i class="pi pi-plus text-sm"></i> Add Location
        </button>
      </div>

      <!-- Search Bar -->
      <div class="mb-4 flex items-center gap-3">
        <div class="relative flex-1 max-w-sm">
          <i class="pi pi-search absolute left-3 top-1/2 -translate-y-1/2 text-muted text-sm"></i>
          <input
            type="text"
            [(ngModel)]="searchQuery"
            (ngModelChange)="onSearch()"
            placeholder="Search locations..."
            class="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>
      </div>

      <!-- Locations Table -->
      <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
        <div class="mb-5 flex items-center gap-2">
          <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
            <i class="pi pi-map-marker text-sm text-secondary"></i>
          </div>
          <h3 class="text-base font-semibold text-text">All Locations</h3>
          <span class="ml-auto text-sm text-muted">{{ total() }} location{{ total() === 1 ? '' : 's' }}</span>
        </div>

        @if (loading()) {
          <div class="flex items-center justify-center py-12">
            <i class="pi pi-spin pi-spinner text-2xl text-primary"></i>
          </div>
        } @else if (locations().length === 0) {
          <div class="flex flex-col items-center justify-center py-16 text-center gap-4">
            <div class="flex h-16 w-16 items-center justify-center rounded-full bg-gray-100">
              <i class="pi pi-map-marker text-3xl text-muted"></i>
            </div>
            <div>
              <p class="text-sm font-semibold text-text">No locations yet</p>
              <p class="mt-1 text-xs text-muted">Add your first business location to get started</p>
            </div>
            <button
              (click)="openAddDialog()"
              class="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 min-h-[44px]"
            >
              <i class="pi pi-plus text-sm"></i> Add Location
            </button>
          </div>
        } @else {
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-100 text-sm">
              <caption class="sr-only">Business locations</caption>
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted">Name</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted">Code</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted">Mobile</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted">Email</th>
                  <th class="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-muted">City</th>
                  <th class="px-3 py-2.5 text-center text-xs font-semibold uppercase tracking-wide text-muted">Status</th>
                  <th class="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-muted">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (loc of locations(); track loc.id) {
                  <tr class="transition-colors hover:bg-gray-50/60">
                    <td class="px-3 py-3 font-medium text-text">{{ loc.name }}</td>
                    <td class="px-3 py-3 font-mono text-xs text-muted">{{ loc.location_code }}</td>
                    <td class="px-3 py-3 text-text">{{ loc.mobile ?? '—' }}</td>
                    <td class="px-3 py-3 text-text">{{ loc.email ?? '—' }}</td>
                    <td class="px-3 py-3 text-text">{{ loc.city ?? '—' }}</td>
                    <td class="px-3 py-3 text-center">
                      @if (loc.is_active) {
                        <span class="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800">
                          Active
                        </span>
                      } @else {
                        <span class="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600">
                          Inactive
                        </span>
                      }
                    </td>
                    <td class="px-3 py-3 text-right">
                      <div class="flex items-center justify-end gap-1">
                        <button
                          (click)="openEditDialog(loc)"
                          title="Edit location"
                          class="inline-flex items-center justify-center rounded p-2 text-muted transition-colors hover:bg-gray-100 hover:text-secondary min-h-[44px] min-w-[44px]"
                        >
                          <i class="pi pi-pencil text-xs"></i>
                        </button>
                        <button
                          (click)="toggleActive(loc)"
                          [title]="loc.is_active ? 'Deactivate' : 'Activate'"
                          class="inline-flex items-center justify-center rounded p-2 text-muted transition-colors hover:bg-gray-100 min-h-[44px] min-w-[44px]"
                          [class]="loc.is_active ? 'hover:text-emerald-600' : 'hover:text-text'"
                        >
                          <i class="pi pi-power-off text-xs"></i>
                        </button>
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      </div>
    </div>

    <!-- Add/Edit Location Dialog -->
    <p-dialog
      [(visible)]="showDialog"
      [header]="editingLocation() ? 'Edit Location' : 'Add Location'"
      [modal]="true"
      [style]="{ width: '640px' }"
      [closable]="true"
      [draggable]="false"
    >
      <div class="space-y-4 py-2">
        <!-- Row 1: Name + Code -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">
              Location Name <span class="text-danger">*</span>
            </label>
            <input
              type="text"
              [(ngModel)]="form.name"
              placeholder="e.g. Main Branch"
              maxlength="255"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">
              Location Code <span class="text-danger">*</span>
            </label>
            <input
              type="text"
              [(ngModel)]="form.location_code"
              placeholder="e.g. LOC-001"
              maxlength="20"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Row 2: Mobile + Alternate Number -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Mobile</label>
            <input
              type="text"
              [(ngModel)]="form.mobile"
              placeholder="e.g. 08012345678"
              maxlength="50"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Alternate Number</label>
            <input
              type="text"
              [(ngModel)]="form.alternate_number"
              placeholder="e.g. 07098765432"
              maxlength="50"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Row 3: Email + Website -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Email</label>
            <input
              type="email"
              [(ngModel)]="form.email"
              placeholder="branch@example.com"
              maxlength="255"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Website</label>
            <input
              type="url"
              [(ngModel)]="form.website"
              placeholder="https://example.com"
              maxlength="255"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Row 4: City + State -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">City</label>
            <input
              type="text"
              [(ngModel)]="form.city"
              placeholder="e.g. Lagos"
              maxlength="100"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">State</label>
            <input
              type="text"
              [(ngModel)]="form.state"
              placeholder="e.g. Lagos State"
              maxlength="100"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Row 5: Country + Zip Code -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Country</label>
            <input
              type="text"
              [(ngModel)]="form.country"
              placeholder="e.g. Nigeria"
              maxlength="100"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Zip Code</label>
            <input
              type="text"
              [(ngModel)]="form.zip_code"
              placeholder="e.g. 100001"
              maxlength="20"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
        </div>

        <!-- Row 6: Landmark -->
        <div>
          <label class="mb-1.5 block text-xs font-medium text-muted">Landmark</label>
          <input
            type="text"
            [(ngModel)]="form.landmark"
            placeholder="e.g. Near Central Bank"
            maxlength="255"
            class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
          />
        </div>

        <!-- Row 7: Currency + Timezone -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Currency</label>
            <select
              [(ngModel)]="form.currency"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            >
              <option value="NGN">NGN</option>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
              <option value="EUR">EUR</option>
            </select>
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Timezone</label>
            <select
              [(ngModel)]="form.timezone"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            >
              <option value="Africa/Lagos">Africa/Lagos</option>
              <option value="UTC">UTC</option>
              <option value="Europe/London">Europe/London</option>
              <option value="America/New_York">America/New_York</option>
            </select>
          </div>
        </div>

        <!-- Row 8: Tax Number + Location Type -->
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Tax Number</label>
            <input
              type="text"
              [(ngModel)]="form.tax_number"
              placeholder="e.g. TIN-1234567"
              maxlength="100"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            />
          </div>
          <div>
            <label class="mb-1.5 block text-xs font-medium text-muted">Location Type</label>
            <select
              [(ngModel)]="form.location_type"
              class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
            >
              <option [ngValue]="null">— None —</option>
              <option value="retail">Retail</option>
              <option value="warehouse">Warehouse</option>
              <option value="online">Online</option>
            </select>
          </div>
        </div>
      </div>

      <ng-template #footer>
        <div class="flex justify-end gap-3 pt-2">
          <button
            (click)="closeDialog()"
            class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 min-h-[44px]"
          >
            Cancel
          </button>
          <button
            (click)="saveLocation()"
            [disabled]="saving()"
            class="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 disabled:opacity-50 min-h-[44px]"
          >
            @if (saving()) {
              <i class="pi pi-spin pi-spinner text-xs"></i>
            }
            {{ editingLocation() ? 'Save Changes' : 'Add Location' }}
          </button>
        </div>
      </ng-template>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LocationsPageComponent implements OnInit {
  private readonly locationsService = inject(LocationsService);
  private readonly messageService = inject(MessageService);
  private readonly destroyRef = inject(DestroyRef);

  locations = signal<Location[]>([]);
  total = signal(0);
  loading = signal(false);
  saving = signal(false);
  searchQuery = '';

  showDialog = false;
  editingLocation = signal<Location | null>(null);

  form: {
    name: string;
    location_code: string;
    mobile: string;
    alternate_number: string;
    email: string;
    website: string;
    landmark: string;
    city: string;
    state: string;
    country: string;
    zip_code: string;
    currency: string;
    timezone: string;
    tax_number: string;
    location_type: LocationType | null;
  } = {
    name: '',
    location_code: '',
    mobile: '',
    alternate_number: '',
    email: '',
    website: '',
    landmark: '',
    city: '',
    state: '',
    country: '',
    zip_code: '',
    currency: 'NGN',
    timezone: 'Africa/Lagos',
    tax_number: '',
    location_type: null,
  };

  ngOnInit(): void {
    this.loadLocations();
  }

  loadLocations(): void {
    this.loading.set(true);
    this.locationsService
      .getAll(this.searchQuery || undefined)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (res) => {
          this.locations.set(res.items);
          this.total.set(res.total);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to load locations',
          });
        },
      });
  }

  onSearch(): void {
    this.loadLocations();
  }

  openAddDialog(): void {
    this.editingLocation.set(null);
    this.resetForm();
    this.showDialog = true;
  }

  openEditDialog(loc: Location): void {
    this.editingLocation.set(loc);
    this.form = {
      name: loc.name,
      location_code: loc.location_code,
      mobile: loc.mobile ?? '',
      alternate_number: loc.alternate_number ?? '',
      email: loc.email ?? '',
      website: loc.website ?? '',
      landmark: loc.landmark ?? '',
      city: loc.city ?? '',
      state: loc.state ?? '',
      country: loc.country ?? '',
      zip_code: loc.zip_code ?? '',
      currency: loc.currency ?? 'NGN',
      timezone: loc.timezone ?? 'Africa/Lagos',
      tax_number: loc.tax_number ?? '',
      location_type: loc.location_type ?? null,
    };
    this.showDialog = true;
  }

  closeDialog(): void {
    this.showDialog = false;
    this.editingLocation.set(null);
    this.resetForm();
  }

  saveLocation(): void {
    if (!this.form.name.trim() || !this.form.location_code.trim()) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Validation',
        detail: 'Name and Location Code are required',
      });
      return;
    }

    this.saving.set(true);

    const payload: LocationCreate = {
      name: this.form.name.trim(),
      location_code: this.form.location_code.trim(),
      mobile: this.form.mobile.trim() || null,
      alternate_number: this.form.alternate_number.trim() || null,
      email: this.form.email.trim() || null,
      website: this.form.website.trim() || null,
      landmark: this.form.landmark.trim() || null,
      city: this.form.city.trim() || null,
      state: this.form.state.trim() || null,
      country: this.form.country.trim() || null,
      zip_code: this.form.zip_code.trim() || null,
      currency: this.form.currency,
      timezone: this.form.timezone,
      tax_number: this.form.tax_number.trim() || null,
      location_type: this.form.location_type,
    };

    const editing = this.editingLocation();
    const request$ = editing
      ? this.locationsService.update(editing.id, payload)
      : this.locationsService.create(payload);

    request$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.saving.set(false);
        this.closeDialog();
        this.loadLocations();
        this.messageService.add({
          severity: 'success',
          summary: 'Success',
          detail: editing ? 'Location updated successfully' : 'Location created successfully',
        });
      },
      error: (err) => {
        this.saving.set(false);
        const detail =
          err?.error?.detail ?? (editing ? 'Failed to update location' : 'Failed to create location');
        this.messageService.add({ severity: 'error', summary: 'Error', detail });
      },
    });
  }

  toggleActive(loc: Location): void {
    this.locationsService
      .update(loc.id, { is_active: !loc.is_active })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.loadLocations();
          this.messageService.add({
            severity: 'success',
            summary: 'Success',
            detail: loc.is_active ? 'Location deactivated' : 'Location activated',
          });
        },
        error: () => {
          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: 'Failed to update location status',
          });
        },
      });
  }

  private resetForm(): void {
    this.form = {
      name: '',
      location_code: '',
      mobile: '',
      alternate_number: '',
      email: '',
      website: '',
      landmark: '',
      city: '',
      state: '',
      country: '',
      zip_code: '',
      currency: 'NGN',
      timezone: 'Africa/Lagos',
      tax_number: '',
      location_type: null,
    };
  }
}
