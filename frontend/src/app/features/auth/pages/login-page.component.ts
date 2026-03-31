import { Component, ChangeDetectionStrategy, signal, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div
      class="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary to-secondary"
    >
      <div class="w-full max-w-md rounded-lg bg-surface p-8 shadow-lg">
        <h1 class="mb-2 text-center text-2xl font-bold text-primary">ModishLog</h1>
        <p class="mb-6 text-center text-sm text-muted">Sign in to your account</p>

        @if (errorMessage()) {
          <div class="mb-4 rounded-lg border border-danger/20 bg-red-50 p-3 text-sm text-danger">
            {{ errorMessage() }}
          </div>
        }

        <form (ngSubmit)="onLogin()">
          <div class="mb-4">
            <label class="mb-1 block text-sm font-medium text-text">Email</label>
            <input
              type="email"
              [(ngModel)]="email"
              name="email"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              placeholder="you@example.com"
              required
            />
          </div>
          <div class="mb-6">
            <label class="mb-1 block text-sm font-medium text-text">Password</label>
            <input
              type="password"
              [(ngModel)]="password"
              name="password"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:ring-1 focus:ring-primary"
              required
              minlength="8"
            />
          </div>
          <button
            type="submit"
            [disabled]="loading()"
            class="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
          >
            @if (loading()) {
              Signing in...
            } @else {
              Sign In
            }
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
  loading = signal(false);
  errorMessage = signal('');

  onLogin(): void {
    if (!this.email || !this.password) return;
    this.loading.set(true);
    this.errorMessage.set('');

    this.authService.login({ email: this.email, password: this.password }).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/']);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 429) {
          this.errorMessage.set('Account locked for 15 minutes due to failed login attempts.');
        } else if (err.status === 401) {
          this.errorMessage.set('Invalid email or password.');
        } else {
          this.errorMessage.set('An unexpected error occurred. Please try again.');
        }
      },
    });
  }
}
