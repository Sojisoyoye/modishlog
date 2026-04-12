import { Component, ChangeDetectionStrategy, signal, input, output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

interface NavItem {
  label: string;
  route: string;
  icon: string;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <aside
      class="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-gray-200 bg-white transition-transform duration-200 lg:static lg:translate-x-0"
      [class.translate-x-0]="mobileOpen()"
      [class.-translate-x-full]="!mobileOpen()"
    >
      <!-- Brand -->
      <div class="flex h-16 shrink-0 items-center gap-2 border-b border-gray-200 px-6">
        <div
          class="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white"
        >
          M
        </div>
        <span class="text-lg font-bold text-primary">ModishLog</span>
      </div>

      <!-- Navigation -->
      <nav class="flex-1 space-y-1 overflow-y-auto px-3 py-4">
        @for (item of navItems(); track item.route) {
          <a
            [routerLink]="item.route"
            routerLinkActive="!bg-primary/10 !text-primary !font-semibold"
            [routerLinkActiveOptions]="{ exact: item.route === '/dashboard' }"
            (click)="closeMobile.emit()"
            class="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-gray-100 hover:text-text"
          >
            <i [class]="'pi ' + item.icon + ' text-base'"></i>
            {{ item.label }}
          </a>
        }
      </nav>

      <!-- Footer -->
      <div class="border-t border-gray-200 px-4 py-3">
        <p class="text-xs text-muted">ModishLog v1.0</p>
      </div>
    </aside>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SidebarComponent {
  mobileOpen = input(false);
  closeMobile = output<void>();

  readonly navItems = signal<NavItem[]>([
    { label: 'Dashboard', route: '/dashboard', icon: 'pi-home' },
    { label: 'Sales', route: '/sales', icon: 'pi-shopping-cart' },
    { label: 'Products', route: '/products', icon: 'pi-barcode' },
    { label: 'Inventory', route: '/inventory', icon: 'pi-box' },
    { label: 'Orders', route: '/orders', icon: 'pi-truck' },
    { label: 'Pricing', route: '/pricing', icon: 'pi-tag' },
    { label: 'FX Rates', route: '/fx', icon: 'pi-money-bill' },
    { label: 'Cashflow', route: '/cashflow', icon: 'pi-chart-line' },
    { label: 'AI Insights', route: '/recommendations', icon: 'pi-sparkles' },
  ]);
}
