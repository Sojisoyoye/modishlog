import { Component, ChangeDetectionStrategy, signal, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="flex min-h-screen items-center justify-center bg-background">
      <div class="w-full max-w-md rounded-lg bg-surface p-8 shadow-lg">
        <h1 class="mb-6 text-center text-2xl font-bold text-primary">ModishLog</h1>
        <form (ngSubmit)="onLogin()">
          <div class="mb-4">
            <label class="mb-1 block text-sm font-medium text-text">Email</label>
            <input
              type="email"
              [(ngModel)]="email"
              name="email"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              placeholder="you@example.com"
            />
          </div>
          <div class="mb-6">
            <label class="mb-1 block text-sm font-medium text-text">Password</label>
            <input
              type="password"
              [(ngModel)]="password"
              name="password"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            class="w-full rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
          >
            Sign In
          </button>
        </form>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginPageComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  email = '';
  password = '';

  onLogin(): void {
    this.authService.login({ email: this.email, password: this.password }).subscribe({
      next: () => this.router.navigate(['/']),
    });
  }
}
