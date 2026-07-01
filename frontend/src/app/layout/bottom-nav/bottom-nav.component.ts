import { Component, ChangeDetectionStrategy, input, output } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  selector: 'app-bottom-nav',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  template: `
    <nav
      data-testid="bottom-nav"
      aria-label="Mobile navigation"
      class="fixed bottom-0 inset-x-0 z-50 md:hidden bg-white border-t border-gray-200 grid grid-cols-4"
      [class.hidden]="mobileOpen()"
    >
      <a
        routerLink="/dashboard"
        routerLinkActive="text-emerald-600"
        [routerLinkActiveOptions]="{ exact: true }"
        class="flex min-h-[56px] min-w-[44px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-gray-500 transition-colors"
      >
        <i class="pi pi-home text-lg"></i>
        <span>Dashboard</span>
      </a>

      <a
        routerLink="/sales"
        routerLinkActive="text-emerald-600"
        class="flex min-h-[56px] min-w-[44px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-gray-500 transition-colors"
      >
        <i class="pi pi-shopping-cart text-lg"></i>
        <span>Sales</span>
      </a>

      <a
        routerLink="/inventory"
        routerLinkActive="text-emerald-600"
        class="flex min-h-[56px] min-w-[44px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-gray-500 transition-colors"
      >
        <i class="pi pi-box text-lg"></i>
        <span>Inventory</span>
      </a>

      <button
        type="button"
        (click)="openMore.emit()"
        class="flex min-h-[56px] min-w-[44px] flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-gray-500 transition-colors"
        [class.text-emerald-600]="mobileOpen()"
        aria-label="More"
      >
        <i class="pi pi-bars text-lg"></i>
        <span>More</span>
      </button>
    </nav>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BottomNavComponent {
  mobileOpen = input(false);
  openMore = output<void>();
}
