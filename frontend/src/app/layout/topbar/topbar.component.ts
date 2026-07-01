import { Component, ChangeDetectionStrategy, inject, input, output } from '@angular/core';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [],
  template: `
    <header
      class="flex h-16 shrink-0 items-center justify-between border-b-2 border-b-primary bg-white px-4 md:px-6"
    >
      <div class="flex items-center gap-3">
        <button
          (click)="toggleMenu.emit()"
          data-testid="topbar-menu-toggle"
          class="hidden min-h-[44px] min-w-[44px] rounded-lg p-2 text-muted transition-colors hover:bg-gray-100 hover:text-text md:flex md:items-center md:justify-center"
        >
          <i [class]="'pi text-lg ' + (sidebarCollapsed() ? 'pi-bars' : 'pi-times')"></i>
        </button>
        <div class="hidden items-center gap-2 lg:flex">
          <i class="pi pi-building text-muted"></i>
          <span class="text-sm font-medium text-muted">Business Dashboard</span>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <div
          class="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary"
        >
          A
        </div>
        <button
          (click)="onLogout()"
          class="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-red-50 hover:text-danger"
        >
          <i class="pi pi-sign-out text-sm"></i>
          <span class="hidden sm:inline">Logout</span>
        </button>
      </div>
    </header>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TopbarComponent {
  private readonly authService = inject(AuthService);
  sidebarCollapsed = input(false);
  toggleMenu = output<void>();

  onLogout(): void {
    this.authService.logout();
  }
}
