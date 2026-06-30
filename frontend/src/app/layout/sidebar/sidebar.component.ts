import { Component, ChangeDetectionStrategy, input, output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

interface NavItem {
  label: string;
  route: string;
  icon: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <aside
      class="fixed inset-y-0 left-0 z-40 flex flex-col border-r border-gray-200 bg-white transition-all duration-200 lg:static lg:h-full lg:translate-x-0"
      [class.w-64]="!collapsed()"
      [class.w-16]="collapsed()"
      [class.translate-x-0]="mobileOpen()"
      [class.-translate-x-full]="!mobileOpen() && !collapsed()"
    >
      <!-- Brand -->
      <div class="flex h-16 shrink-0 items-center gap-2 border-b border-gray-200 px-4">
        <div
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white"
        >
          M
        </div>
        @if (!collapsed()) {
          <span class="text-lg font-bold text-primary">ModishLog</span>
        }
      </div>

      <!-- Navigation -->
      <nav aria-label="Main navigation" class="flex-1 overflow-y-auto px-2 py-4">
        <!-- Dashboard (ungrouped) -->
        @for (item of dashboardItems; track item.route) {
          <a
            [routerLink]="item.route"
            routerLinkActive="!bg-primary/10 !text-primary !font-semibold"
            [routerLinkActiveOptions]="{ exact: true }"
            (click)="closeMobile.emit()"
            class="flex min-h-[44px] items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
            [title]="collapsed() ? item.label : ''"
          >
            <i [class]="'pi ' + item.icon + ' text-base shrink-0'"></i>
            @if (!collapsed()) {
              <span>{{ item.label }}</span>
            }
          </a>
        }

        <!-- Grouped sections -->
        @for (group of navGroups; track group.label) {
          <hr class="my-2 border-gray-100">
          @if (!collapsed()) {
            <p class="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-gray-400">{{ group.label }}</p>
          }
          @for (item of group.items; track item.route) {
            <a
              [routerLink]="item.route"
              routerLinkActive="!bg-primary/10 !text-primary !font-semibold"
              [routerLinkActiveOptions]="{ exact: item.route === '/settings' }"
              (click)="closeMobile.emit()"
              class="flex min-h-[44px] items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
              [title]="collapsed() ? item.label : ''"
            >
              <i [class]="'pi ' + item.icon + ' text-base shrink-0'"></i>
              @if (!collapsed()) {
                <span>{{ item.label }}</span>
              }
            </a>
          }
        }
      </nav>

      <!-- Footer -->
      @if (!collapsed()) {
        <div class="border-t border-gray-200 px-4 py-3">
          <p class="text-xs text-muted">ModishLog v1.0</p>
        </div>
      }
    </aside>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SidebarComponent {
  mobileOpen = input(false);
  collapsed = input(false);
  closeMobile = output<void>();

  readonly dashboardItems: NavItem[] = [
    { label: 'Dashboard', route: '/dashboard', icon: 'pi-home' },
  ];

  readonly navGroups: NavGroup[] = [
    {
      label: 'OPERATIONS',
      items: [
        { label: 'Sales', route: '/sales', icon: 'pi-shopping-cart' },
        { label: 'Products', route: '/products', icon: 'pi-barcode' },
        { label: 'Inventory', route: '/inventory', icon: 'pi-box' },
        { label: 'Stock Counts', route: '/stock-counts', icon: 'pi-clipboard' },
        { label: 'Orders', route: '/orders', icon: 'pi-truck' },
        { label: 'Suppliers', route: '/suppliers', icon: 'pi-users' },
      ],
    },
    {
      label: 'FINANCE',
      items: [
        { label: 'Pricing', route: '/pricing', icon: 'pi-tag' },
        { label: 'FX Rates', route: '/fx', icon: 'pi-money-bill' },
        { label: 'Cashflow', route: '/cashflow', icon: 'pi-chart-line' },
        { label: 'Reports', route: '/reports', icon: 'pi-chart-bar' },
      ],
    },
    {
      label: 'INTELLIGENCE',
      items: [
        { label: 'AI Insights', route: '/recommendations', icon: 'pi-sparkles' },
      ],
    },
    {
      label: 'SETTINGS',
      items: [
        { label: 'Invoice Schemes', route: '/settings/invoice-schemes', icon: 'pi-file-edit' },
        { label: 'Locations', route: '/settings/locations', icon: 'pi-map-marker' },
        { label: 'Settings', route: '/settings', icon: 'pi-cog' },
      ],
    },
  ];
}
