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
      class="fixed inset-y-0 left-0 z-40 w-64 border-r border-gray-200 bg-surface transition-transform lg:static lg:translate-x-0"
      [class.translate-x-0]="mobileOpen()"
      [class.-translate-x-full]="!mobileOpen()"
    >
      <div class="flex h-16 items-center justify-center border-b border-gray-200">
        <h1 class="text-xl font-bold text-primary">ModishLog</h1>
      </div>
      <nav class="mt-4 space-y-1 px-3">
        @for (item of navItems(); track item.route) {
          <a
            [routerLink]="item.route"
            routerLinkActive="bg-primary/10 text-primary"
            (click)="closeMobile.emit()"
            class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted hover:bg-gray-100"
          >
            <i [class]="'pi ' + item.icon"></i>
            {{ item.label }}
          </a>
        }
      </nav>
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
    { label: 'Inventory', route: '/inventory', icon: 'pi-box' },
    { label: 'Orders', route: '/orders', icon: 'pi-truck' },
    { label: 'Pricing', route: '/pricing', icon: 'pi-tag' },
    { label: 'FX Rates', route: '/fx', icon: 'pi-money-bill' },
    { label: 'Cashflow', route: '/cashflow', icon: 'pi-chart-line' },
    { label: 'AI Insights', route: '/recommendations', icon: 'pi-sparkles' },
  ]);
}
