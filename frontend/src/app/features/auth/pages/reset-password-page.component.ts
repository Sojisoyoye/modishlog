import { Component, ChangeDetectionStrategy, signal, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-reset-password-page',
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
            <h1 class="text-2xl font-bold text-text">Reset Password</h1>
            <p class="mt-1 text-sm text-muted">Enter your new password below</p>
          </div>

          @if (!token()) {
            <!-- No token in URL -->
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
            >
              <i class="pi pi-exclamation-circle"></i>
              Invalid or missing reset token. Please request a new password reset link.
            </div>
            <div class="mt-4 text-center">
              <button
                type="button"
                (click)="goToLogin()"
                class="text-sm text-primary hover:underline"
              >
                Back to login
              </button>
            </div>
          } @else if (successMessage()) {
            <!-- Success state -->
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700"
            >
              <i class="pi pi-check-circle"></i>
              {{ successMessage() }}
            </div>
            <p class="mt-3 text-center text-sm text-muted">
              You will be redirected to login shortly.
            </p>
          } @else {
            <!-- Reset form -->
            @if (errorMessage()) {
              <div
                role="alert"
                aria-live="polite"
                class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
              >
                <i class="pi pi-exclamation-circle"></i>
                {{ errorMessage() }}
              </div>
            }

            <form (ngSubmit)="onSubmit()">
              <div class="mb-4">
                <label for="new-password" class="mb-1.5 block text-sm font-medium text-text">
                  New Password
                </label>
                <div class="relative">
                  <i
                    class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                  ></i>
                  <input
                    id="new-password"
                    [type]="showNewPassword() ? 'text' : 'password'"
                    [(ngModel)]="newPassword"
                    name="newPassword"
                    autocomplete="new-password"
                    class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-10 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="At least 12 characters"
                    required
                    minlength="12"
                  />
                  <button
                    type="button"
                    (click)="showNewPassword.set(!showNewPassword())"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-text focus:outline-none"
                    [attr.aria-label]="showNewPassword() ? 'Hide password' : 'Show password'"
                  >
                    <i [class]="showNewPassword() ? 'pi pi-eye-slash text-sm' : 'pi pi-eye text-sm'"></i>
                  </button>
                </div>
              </div>

              <div class="mb-6">
                <label for="confirm-password" class="mb-1.5 block text-sm font-medium text-text">
                  Confirm Password
                </label>
                <div class="relative">
                  <i
                    class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted"
                  ></i>
                  <input
                    id="confirm-password"
                    [type]="showConfirmPassword() ? 'text' : 'password'"
                    [(ngModel)]="confirmPassword"
                    name="confirmPassword"
                    autocomplete="new-password"
                    class="w-full rounded-lg border border-gray-300 py-2.5 pl-10 pr-10 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                    placeholder="Repeat your new password"
                    required
                  />
                  <button
                    type="button"
                    (click)="showConfirmPassword.set(!showConfirmPassword())"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-text focus:outline-none"
                    [attr.aria-label]="showConfirmPassword() ? 'Hide password' : 'Show password'"
                  >
                    <i [class]="showConfirmPassword() ? 'pi pi-eye-slash text-sm' : 'pi pi-eye text-sm'"></i>
                  </button>
                </div>
              </div>

              <button
                type="submit"
                [disabled]="loading()"
                class="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
              >
                @if (loading()) {
                  <i class="pi pi-spinner pi-spin text-sm"></i>
                  Resetting...
                } @else {
                  Reset Password
                }
              </button>
            </form>

            <div class="mt-4 text-center">
              <button
                type="button"
                (click)="goToLogin()"
                class="text-sm text-primary hover:underline"
              >
                Back to login
              </button>
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
export class ResetPasswordPageComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  token = signal('');
  newPassword = '';
  confirmPassword = '';
  loading = signal(false);
  errorMessage = signal('');
  successMessage = signal('');
  showNewPassword = signal(false);
  showConfirmPassword = signal(false);

  ngOnInit(): void {
    const tokenParam = this.route.snapshot.queryParamMap.get('token') ?? '';
    this.token.set(tokenParam);
  }

  goToLogin(): void {
    this.router.navigate(['/login']);
  }

  onSubmit(): void {
    this.errorMessage.set('');

    if (!this.newPassword || !this.confirmPassword) {
      return;
    }

    if (this.newPassword !== this.confirmPassword) {
      this.errorMessage.set('Passwords do not match. Please try again.');
      return;
    }

    this.loading.set(true);

    this.authService.resetPassword(this.token(), this.newPassword).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.successMessage.set(res.message || 'Password has been reset successfully.');
        // Redirect to login after 2 seconds
        setTimeout(() => {
          this.router.navigate(['/login']);
        }, 2000);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 400) {
          this.errorMessage.set(
            err.error?.detail ?? 'Invalid or expired reset token. Please request a new link.',
          );
        } else {
          this.errorMessage.set('An unexpected error occurred. Please try again.');
        }
      },
    });
  }
}
