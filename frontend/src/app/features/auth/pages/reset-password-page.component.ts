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

          <h2 class="mb-2 text-2xl font-bold text-gray-900">Reset Password</h2>

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
            <p class="mt-3 text-center text-sm text-gray-500">
              You will be redirected to login shortly.
            </p>
          } @else {
            <!-- Reset form (token is present) -->
            <p class="mb-8 text-sm text-gray-500">Enter your new password below</p>

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
                <label for="new-password" class="mb-1.5 block text-sm font-medium text-gray-700">
                  New Password
                </label>
                <div class="relative">
                  <i
                    class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"
                  ></i>
                  <input
                    id="new-password"
                    [type]="showNewPassword() ? 'text' : 'password'"
                    [(ngModel)]="newPassword"
                    name="newPassword"
                    autocomplete="new-password"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10 pr-10"
                    placeholder="At least 12 characters"
                    required
                    minlength="12"
                  />
                  <button
                    type="button"
                    (click)="showNewPassword.set(!showNewPassword())"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 focus:outline-none"
                    [attr.aria-label]="showNewPassword() ? 'Hide password' : 'Show password'"
                  >
                    <i [class]="showNewPassword() ? 'pi pi-eye-slash text-sm' : 'pi pi-eye text-sm'"></i>
                  </button>
                </div>
              </div>

              <div class="mb-6">
                <label for="confirm-password" class="mb-1.5 block text-sm font-medium text-gray-700">
                  Confirm Password
                </label>
                <div class="relative">
                  <i
                    class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"
                  ></i>
                  <input
                    id="confirm-password"
                    [type]="showConfirmPassword() ? 'text' : 'password'"
                    [(ngModel)]="confirmPassword"
                    name="confirmPassword"
                    autocomplete="new-password"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10 pr-10"
                    placeholder="Repeat your new password"
                    required
                  />
                  <button
                    type="button"
                    (click)="showConfirmPassword.set(!showConfirmPassword())"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-700 focus:outline-none"
                    [attr.aria-label]="showConfirmPassword() ? 'Hide password' : 'Show password'"
                  >
                    <i [class]="showConfirmPassword() ? 'pi pi-eye-slash text-sm' : 'pi pi-eye text-sm'"></i>
                  </button>
                </div>
              </div>

              <button
                type="submit"
                [disabled]="loading()"
                class="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-white transition-colors hover:bg-secondary disabled:opacity-50 min-h-[44px] flex items-center justify-center gap-2"
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
          this.errorMessage.set('Invalid or expired reset link. Please request a new one.');
        } else {
          this.errorMessage.set('An unexpected error occurred. Please try again.');
        }
      },
    });
  }
}
