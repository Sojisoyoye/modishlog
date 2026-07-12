import { Component, ChangeDetectionStrategy, signal, computed, inject, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div class="flex min-h-screen">
      <!-- Left brand panel (hidden on mobile) -->
      <div class="hidden lg:flex lg:w-[45%] flex-col justify-between bg-gradient-to-br from-gray-900 via-emerald-950 to-gray-900 p-12 text-white">
        <!-- Top: logo + tagline -->
        <div>
          <div class="mb-4">
            <div class="rounded-xl bg-primary text-white w-14 h-14 flex items-center justify-center text-2xl font-bold mb-4">M</div>
            <h1 class="text-3xl font-bold tracking-tight">ModishLog</h1>
          </div>
          <p class="mt-3 text-lg text-emerald-200">
            Your shop runs better when you can see the numbers.
          </p>
        </div>

        <!-- Bottom: social proof quote -->
        <div class="bg-white/10 rounded-xl p-5 text-sm text-white/90">
          <p class="mb-4 text-sm italic text-white/80 leading-relaxed">
            "I used to spend 2 hours every evening on my books. Now it takes 4 minutes."
          </p>
          <p class="text-sm font-semibold text-emerald-300">Adaeze O., Lagos Market Trader</p>
          <p class="mt-1.5 text-emerald-400 text-sm tracking-widest">&#9679;&#9679;&#9679;&#9679;&#9679;</p>
        </div>
      </div>

      <!-- Right form panel -->
      <div class="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-16 bg-white">
        <div class="w-full max-w-md">
          <!-- Mobile logo (shown only on small screens) -->
          <div class="mb-8 text-center lg:hidden">
            <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-xl font-bold text-white shadow-lg">
              M
            </div>
            <span class="text-2xl font-bold text-gray-900">ModishLog</span>
          </div>

          @if (!showForgotPassword()) {
            <h2 class="mb-8 text-2xl font-bold text-gray-900 text-center lg:text-left">Sign in to your account</h2>

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
                <label for="login-email" class="mb-1.5 block text-sm font-medium text-gray-700">Email</label>
                <div class="relative">
                  <i
                    class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"
                  ></i>
                  <input
                    id="login-email"
                    type="email"
                    [(ngModel)]="email"
                    name="email"
                    autocomplete="email"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="you@example.com"
                    required
                  />
                </div>
              </div>
              <div class="mb-6">
                <label for="login-password" class="mb-1.5 block text-sm font-medium text-gray-700">Password</label>
                <div class="relative">
                  <i
                    class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"
                  ></i>
                  <input
                    id="login-password"
                    [type]="showPassword() ? 'text' : 'password'"
                    [(ngModel)]="password"
                    name="password"
                    autocomplete="current-password"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10 pr-10"
                    required
                    minlength="8"
                  />
                  <button
                    type="button"
                    data-testid="toggle-password"
                    (click)="showPassword.set(!showPassword())"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 focus:outline-none"
                    [attr.aria-label]="showPassword() ? 'Hide password' : 'Show password'"
                  >
                    <i [class]="showPassword() ? 'pi pi-eye-slash text-sm' : 'pi pi-eye text-sm'"></i>
                  </button>
                </div>
              </div>
              <button
                type="submit"
                [disabled]="loading() || lockoutSeconds() > 0"
                class="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-white transition-colors hover:bg-secondary disabled:opacity-50 min-h-[44px] flex items-center justify-center gap-2"
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
                (click)="toggleForgotPassword(true)"
                class="text-sm text-primary hover:underline"
              >
                Forgot password?
              </button>
            </div>

            <!-- Footer text -->
            <p class="mt-8 text-center text-xs text-gray-400">
              Don't have an account? <a routerLink="/register" class="font-medium text-emerald-600 hover:text-emerald-700">Sign up</a>
            </p>
          } @else {
            <!-- Forgot password: replaces the login form entirely (no email/password
                 login inputs rendered here) so this view stays short on every device. -->
            <h2 class="mb-2 text-2xl font-bold text-gray-900 text-center lg:text-left">Reset your password</h2>
            <p class="mb-6 text-sm text-gray-500 text-center lg:text-left">
              Enter your email address and we'll send you a reset link.
            </p>

            @if (lockoutDisplay()) {
              <div
                role="alert"
                aria-live="polite"
                class="mb-4 flex items-center gap-2 rounded-lg border border-orange-200 bg-orange-50 p-3 text-sm text-orange-700"
              >
                <i class="pi pi-clock"></i>
                Your account is still locked. Try again in {{ lockoutDisplay() }} — a password reset won't lift the lockout early.
              </div>
            }

            @if (forgotPasswordMessage()) {
              <div
                role="alert"
                aria-live="polite"
                class="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700"
              >
                <i class="pi pi-check-circle"></i>
                {{ forgotPasswordMessage() }}
              </div>
            }

            <form (ngSubmit)="onForgotPassword()">
              <div class="mb-4">
                <label for="forgot-email" class="mb-1.5 block text-sm font-medium text-gray-700">Email</label>
                <div class="relative">
                  <i
                    class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"
                  ></i>
                  <input
                    id="forgot-email"
                    type="email"
                    [(ngModel)]="forgotEmail"
                    name="forgotEmail"
                    autocomplete="email"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="you@example.com"
                    required
                  />
                </div>
              </div>
              <button
                type="submit"
                [disabled]="forgotLoading()"
                class="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-white transition-colors hover:bg-secondary disabled:opacity-50 min-h-[44px] flex items-center justify-center gap-2"
              >
                @if (forgotLoading()) {
                  <i class="pi pi-spinner pi-spin text-sm"></i>
                  Sending...
                } @else {
                  Send Reset Link
                }
              </button>
            </form>

            <!-- Back to sign in -->
            <div class="mt-4 text-center">
              <button
                type="button"
                (click)="toggleForgotPassword(false)"
                class="text-sm text-primary hover:underline"
              >
                &larr; Back to sign in
              </button>
            </div>
          }
        </div>
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

  /** Switching views must not leak stale state — a leftover error/success
   * banner or a previously typed reset email from an earlier visit should
   * never resurface on a view the user hasn't acted on yet. lockoutSeconds/
   * lockoutTimer are deliberately left untouched: that's real, enforced
   * lockout state (it must keep counting down and re-block Sign In when the
   * user comes back), not stale UI to clear. */
  toggleForgotPassword(show: boolean): void {
    this.showForgotPassword.set(show);
    this.errorMessage.set('');
    this.forgotPasswordMessage.set('');
    this.forgotEmail = '';
  }

  onLogin(): void {
    if (!this.email || !this.password) return;
    this.loading.set(true);
    this.errorMessage.set('');

    this.authService.login({ email: this.email, password: this.password }).subscribe({
      next: () => {
        this.loading.set(false);
        this.router.navigate(['/dashboard']);
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
