import { Component, ChangeDetectionStrategy, inject } from '@angular/core';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [],
  template: `
    <header class="flex h-16 items-center justify-between border-b border-gray-200 bg-surface px-6">
      <div class="text-lg font-semibold text-text">ModishLog</div>
      <button
        (click)="onLogout()"
        class="rounded-lg px-4 py-2 text-sm font-medium text-muted hover:bg-gray-100"
      >
        Logout
      </button>
    </header>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TopbarComponent {
  private readonly authService = inject(AuthService);

  onLogout(): void {
    this.authService.logout();
  }
}
