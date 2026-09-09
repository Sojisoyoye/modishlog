import { Component, ChangeDetectionStrategy, signal, inject, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-verify-email-page',
  standalone: true,
  imports: [],
  template: `
    <div class="flex min-h-screen">
      <!-- Left brand panel (hidden on mobile) -->
      <div class="hidden lg:flex lg:w-[45%] flex-col justify-between bg-gradient-to-br from-gray-900 via-emerald-950 to-gray-900 p-12 text-white">
        <div>
          <div class="mb-4">
            <div class="rounded-xl bg-primary text-white w-14 h-14 flex items-center justify-center text-2xl font-bold mb-4">M</div>
            <h1 class="text-3xl font-bold tracking-tight">ModishLog</h1>
          </div>
          <p class="mt-3 text-lg text-emerald-200">
            Your shop runs better when you can see the numbers.
          </p>
        </div>
        <div class="bg-white/10 rounded-xl p-5 text-sm text-white/90">
          <p class="mb-4 text-sm italic text-white/80 leading-relaxed">
            "I used to spend 2 hours every evening on my books. Now it takes 4 minutes."
          </p>
          <p class="text-sm font-semibold text-emerald-300">Adaeze O., Lagos Market Trader</p>
          <p class="mt-1.5 text-emerald-400 text-sm tracking-widest">&#9679;&#9679;&#9679;&#9679;&#9679;</p>
        </div>
      </div>

      <!-- Right panel -->
      <div class="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-16 bg-white">
        <div class="w-full max-w-md">
          <div class="mb-8 text-center lg:hidden">
            <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-xl font-bold text-white shadow-lg">
              M
            </div>
            <span class="text-2xl font-bold text-gray-900">ModishLog</span>
          </div>

          <h2 class="mb-2 text-2xl font-bold text-gray-900">Verify your email</h2>

          @if (!token()) {
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
            >
              <i class="pi pi-exclamation-circle"></i>
              Invalid or missing verification link. Please request a new one.
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
          } @else if (errorMessage()) {
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
            >
              <i class="pi pi-exclamation-circle"></i>
              {{ errorMessage() }}
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
          } @else {
            <p class="mb-8 text-sm text-gray-500">
              <i class="pi pi-spinner pi-spin mr-2"></i>
              Verifying your email...
            </p>
          }
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VerifyEmailPageComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  token = signal('');
  loading = signal(false);
  errorMessage = signal('');
  successMessage = signal('');

  ngOnInit(): void {
    const tokenParam = this.route.snapshot.queryParamMap.get('token') ?? '';
    this.token.set(tokenParam);
    if (tokenParam) {
      this.verify(tokenParam);
    }
  }

  goToLogin(): void {
    this.router.navigate(['/login']);
  }

  private verify(token: string): void {
    this.loading.set(true);
    this.authService.verifyEmail(token).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.successMessage.set(res.message || 'Email verified successfully.');
        setTimeout(() => {
          this.router.navigate(['/login']);
        }, 2000);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        if (err.status === 400) {
          this.errorMessage.set(
            'This verification link is invalid or has expired. Please request a new one.',
          );
        } else {
          this.errorMessage.set('An unexpected error occurred. Please try again.');
        }
      },
    });
  }
}
