import { Component, ChangeDetectionStrategy, inject, output } from '@angular/core';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [],
  template: `
    <header class="flex h-16 items-center justify-between border-b border-gray-200 bg-surface px-4 md:px-6">
      <div class="flex items-center gap-3">
        <button
          (click)="toggleMenu.emit()"
          class="rounded-lg p-2 text-muted hover:bg-gray-100 lg:hidden"
        >
          <i class="pi pi-bars"></i>
        </button>
        <span class="text-lg font-semibold text-text">ModishLog</span>
      </div>
      <button
        (click)="onLogout()"
        class="rounded-lg px-4 py-2 text-sm font-medium text-muted hover:bg-gray-100"
      >
        <i class="pi pi-sign-out mr-1"></i> Logout
      </button>
    </header>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TopbarComponent {
  private readonly authService = inject(AuthService);
  toggleMenu = output<void>();

  onLogout(): void {
    this.authService.logout();
  }
}
