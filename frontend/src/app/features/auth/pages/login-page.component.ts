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
      class="flex min-h-screen items-center justify-center bg-gradient-to-br from-primary to-secondary p-4"
    >
      <div class="w-full max-w-md">
        <!-- Card -->
        <div class="rounded-2xl bg-white p-8 shadow-2xl">
          <!-- Logo -->
          <div class="mb-6 text-center">
            <div
              class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-xl bg-primary text-xl font-bold text-white shadow-lg"
            >
              M
            </div>
            <h1 class="text-2xl font-bold text-text">ModishLog</h1>
            <p class="mt-1 text-sm text-muted">Sign in to your business dashboard</p>
          </div>

          @if (errorMessage()) {
            <div
              class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
            >
              <i class="pi pi-exclamation-circle"></i>
              {{ errorMessage() }}
            </div>
          }

          <form (ngSubmit)="onLogin()">
            <div class="mb-4">
              <label class="mb-1.5 block text-sm font-medium text-text">Email</label>
              <div class="relative">
                <i
                  class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                ></i>
                <input
                  type="email"
                  [(ngModel)]="email"
                  name="email"
                  class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-3 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  placeholder="you@example.com"
                  required
                />
              </div>
            </div>
            <div class="mb-6">
              <label class="mb-1.5 block text-sm font-medium text-text">Password</label>
              <div class="relative">
                <i
                  class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                ></i>
                <input
                  type="password"
                  [(ngModel)]="password"
                  name="password"
                  class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-3 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  required
                  minlength="8"
                />
              </div>
            </div>
            <button
              type="submit"
              [disabled]="loading()"
              class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
            >
              @if (loading()) {
                <i class="pi pi-spinner pi-spin text-sm"></i>
                Signing in...
              } @else {
                Sign In
              }
            </button>
          </form>
        </div>

        <!-- Footer -->
        <p class="mt-6 text-center text-xs text-white/70">
          Smart business management for everyday traders
        </p>
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
