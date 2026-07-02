import {
  Component,
  ChangeDetectionStrategy,
  DestroyRef,
  signal,
  OnInit,
  inject,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { SuppliersPageComponent } from '../../suppliers/pages/suppliers-page.component';
import { CustomersPageComponent } from '../../customers/pages/customers-page/customers-page.component';

type ContactTab = 'suppliers' | 'customers';

@Component({
  selector: 'app-contacts-page',
  standalone: true,
  imports: [SuppliersPageComponent, CustomersPageComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-3">
      <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <i class="pi pi-address-book text-lg"></i>
      </div>
      <div>
        <h2 class="text-2xl font-bold text-text">Contacts</h2>
        <p class="mt-0.5 text-sm text-muted">Manage your suppliers and customers</p>
      </div>
    </div>

    <!-- Tab bar -->
    <div
      class="mb-6 flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1 w-fit"
      role="tablist"
      aria-label="Contact type"
    >
      <button
        role="tab"
        id="tab-suppliers"
        [attr.aria-selected]="activeTab() === 'suppliers'"
        (click)="setTab('suppliers')"
        class="rounded px-5 py-2 text-sm font-medium transition-colors min-h-[38px]"
        [class]="activeTab() === 'suppliers'
          ? 'bg-white text-primary shadow-sm font-semibold'
          : 'text-muted hover:text-text'"
      >
        <i class="pi pi-users mr-2 text-xs"></i>Suppliers
      </button>
      <button
        role="tab"
        id="tab-customers"
        [attr.aria-selected]="activeTab() === 'customers'"
        (click)="setTab('customers')"
        class="rounded px-5 py-2 text-sm font-medium transition-colors min-h-[38px]"
        [class]="activeTab() === 'customers'
          ? 'bg-white text-primary shadow-sm font-semibold'
          : 'text-muted hover:text-text'"
      >
        <i class="pi pi-user mr-2 text-xs"></i>Customers
      </button>
    </div>

    <!-- Tab panels -->
    @if (activeTab() === 'suppliers') {
      <div
        id="contacts-panel-suppliers"
        role="tabpanel"
        aria-labelledby="tab-suppliers"
      >
        <app-suppliers-page />
      </div>
    } @else {
      <div
        id="contacts-panel-customers"
        role="tabpanel"
        aria-labelledby="tab-customers"
      >
        <app-customers-page />
      </div>
    }
  `,
})
export class ContactsPageComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  activeTab = signal<ContactTab>('suppliers');

  ngOnInit(): void {
    this.route.queryParams.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const tab = params['tab'] as ContactTab;
      if (tab === 'customers' || tab === 'suppliers') {
        this.activeTab.set(tab);
      }
    });
  }

  setTab(tab: ContactTab): void {
    this.activeTab.set(tab);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { tab },
      queryParamsHandling: 'merge',
    });
  }
}
