import { Component, ChangeDetectionStrategy, signal, computed, inject, OnDestroy } from '@angular/core';
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

          @if (lockoutDisplay()) {
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm text-orange-700"
            >
              <i class="pi pi-clock"></i>
              Account locked. Try again in {{ lockoutDisplay() }}
            </div>
          } @else if (errorMessage()) {
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
            >
              <i class="pi pi-exclamation-circle"></i>
              {{ errorMessage() }}
            </div>
          }

          <form (ngSubmit)="onLogin()">
            <div class="mb-4">
              <label for="login-email" class="mb-1.5 block text-sm font-medium text-text">Email</label>
              <div class="relative">
                <i
                  class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                ></i>
                <input
                  id="login-email"
                  type="email"
                  [(ngModel)]="email"
                  name="email"
                  autocomplete="email"
                  class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-3 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  placeholder="you@example.com"
                  required
                />
              </div>
            </div>
            <div class="mb-6">
              <label for="login-password" class="mb-1.5 block text-sm font-medium text-text">Password</label>
              <div class="relative">
                <i
                  class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                ></i>
                <input
                  id="login-password"
                  [type]="showPassword() ? 'text' : 'password'"
                  [(ngModel)]="password"
                  name="password"
                  autocomplete="current-password"
                  class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-10 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  required
                  minlength="8"
                />
                <button
                  type="button"
                  data-testid="toggle-password"
                  (click)="showPassword.set(!showPassword())"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-text focus:outline-none"
                  [attr.aria-label]="showPassword() ? 'Hide password' : 'Show password'"
                >
                  <i [class]="showPassword() ? 'pi pi-eye-slash text-sm' : 'pi pi-eye text-sm'"></i>
                </button>
              </div>
            </div>
            <button
              type="submit"
              [disabled]="loading() || lockoutSeconds() > 0"
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

          <!-- Forgot password link -->
          <div class="mt-4 text-center">
            <button
              type="button"
              (click)="showForgotPassword.set(!showForgotPassword())"
              class="text-sm text-primary hover:underline"
            >
              Forgot password?
            </button>
          </div>

          <!-- Forgot password inline form -->
          @if (showForgotPassword()) {
            <div class="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
              <p class="mb-3 text-sm text-muted">
                Enter your email address and we'll send you a reset link.
              </p>

              @if (forgotPasswordMessage()) {
                <div
                  class="mb-3 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700"
                >
                  <i class="pi pi-check-circle"></i>
                  {{ forgotPasswordMessage() }}
                </div>
              }

              <form (ngSubmit)="onForgotPassword()">
                <div class="mb-3">
                  <label for="forgot-email" class="sr-only">Email for password reset</label>
                  <div class="relative">
                    <i
                      class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                    ></i>
                    <input
                      id="forgot-email"
                      type="email"
                      [(ngModel)]="forgotEmail"
                      name="forgotEmail"
                      autocomplete="email"
                      class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-3 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                      placeholder="you@example.com"
                      required
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  [disabled]="forgotLoading()"
                  class="flex w-full items-center justify-center gap-2 rounded-lg bg-secondary px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-secondary/90 disabled:opacity-50"
                >
                  @if (forgotLoading()) {
                    <i class="pi pi-spinner pi-spin text-sm"></i>
                    Sending...
                  } @else {
                    Send Reset Link
                  }
                </button>
              </form>
            </div>
          }
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
export class LoginPageComponent implements OnDestroy {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private lockoutTimer: ReturnType<typeof setInterval> | null = null;

  email = '';
  password = '';
  loading = signal(false);
  errorMessage = signal('');
  showPassword = signal(false);

  // Lockout countdown state
  lockoutSeconds = signal(0);
  lockoutDisplay = computed(() => {
    const secs = this.lockoutSeconds();
    if (secs <= 0) return '';
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  });

  // Forgot password state
  showForgotPassword = signal(false);
  forgotEmail = '';
  forgotLoading = signal(false);
  forgotPasswordMessage = signal('');

  ngOnDestroy(): void {
    this.clearLockoutTimer();
  }

  private clearLockoutTimer(): void {
    if (this.lockoutTimer !== null) {
      clearInterval(this.lockoutTimer);
      this.lockoutTimer = null;
    }
  }

  private startLockoutCountdown(lockedUntilIso: string): void {
    this.clearLockoutTimer();
    const lockedUntil = new Date(lockedUntilIso).getTime();
    const remaining = Math.max(0, Math.ceil((lockedUntil - Date.now()) / 1000));
    this.lockoutSeconds.set(remaining);
    this.errorMessage.set('');

    if (remaining <= 0) return;

    this.lockoutTimer = setInterval(() => {
      const current = this.lockoutSeconds();
      if (current <= 1) {
        this.lockoutSeconds.set(0);
        this.clearLockoutTimer();
      } else {
        this.lockoutSeconds.set(current - 1);
      }
    }, 1000);
  }

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
        if (err.status === 429 && err.error?.locked_until) {
          this.startLockoutCountdown(err.error.locked_until);
        } else if (err.status === 429) {
          this.errorMessage.set('Account locked due to failed login attempts. Try again later.');
        } else if (err.status === 401) {
          this.errorMessage.set('Invalid email or password.');
        } else {
          this.errorMessage.set('An unexpected error occurred. Please try again.');
        }
      },
    });
  }

  onForgotPassword(): void {
    if (!this.forgotEmail) return;
    this.forgotLoading.set(true);
    this.forgotPasswordMessage.set('');

    this.authService.forgotPassword(this.forgotEmail).subscribe({
      next: (res) => {
        this.forgotLoading.set(false);
        this.forgotPasswordMessage.set(res.message);
      },
      error: () => {
        this.forgotLoading.set(false);
        this.forgotPasswordMessage.set(
          'If an account with that email exists, a reset link has been sent.',
        );
      },
    });
  }
}
