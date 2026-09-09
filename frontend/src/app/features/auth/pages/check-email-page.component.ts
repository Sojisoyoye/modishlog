import { Component, ChangeDetectionStrategy, signal, inject, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-check-email-page',
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

      <!-- Right form panel -->
      <div class="flex flex-1 flex-col items-center justify-center px-6 py-12 lg:px-16 bg-white">
        <div class="w-full max-w-md text-center">
          <div class="mb-8 text-center lg:hidden">
            <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-xl font-bold text-white shadow-lg">
              M
            </div>
            <span class="text-2xl font-bold text-gray-900">ModishLog</span>
          </div>

          <div class="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50">
            <i class="pi pi-envelope text-2xl text-primary"></i>
          </div>

          <h2 class="mb-2 text-2xl font-bold text-gray-900">Check your email</h2>
          <p class="mb-8 text-sm text-gray-500">
            We sent a verification link to
            @if (email()) {
              <span class="font-medium text-gray-700">{{ email() }}</span>
            } @else {
              your email address
            }. Click it to activate your account.
          </p>

          @if (resendMessage()) {
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700"
            >
              <i class="pi pi-check-circle"></i>
              {{ resendMessage() }}
            </div>
          }

          @if (email()) {
            <button
              type="button"
              [disabled]="resendLoading()"
              (click)="onResend()"
              class="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-white transition-colors hover:bg-secondary disabled:opacity-50 min-h-[44px] flex items-center justify-center gap-2"
            >
              @if (resendLoading()) {
                <i class="pi pi-spinner pi-spin text-sm"></i>
                Resending...
              } @else {
                Resend verification email
              }
            </button>
          }

          <div class="mt-4 text-center">
            <button
              type="button"
              (click)="goToLogin()"
              class="text-sm text-primary hover:underline"
            >
              Back to login
            </button>
          </div>
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CheckEmailPageComponent implements OnInit {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  email = signal('');
  resendLoading = signal(false);
  resendMessage = signal('');

  ngOnInit(): void {
    const emailParam = this.route.snapshot.queryParamMap.get('email') ?? '';
    this.email.set(emailParam);
  }

  goToLogin(): void {
    this.router.navigate(['/login']);
  }

  onResend(): void {
    if (!this.email()) return;
    this.resendLoading.set(true);
    this.resendMessage.set('');

    this.authService.resendVerification(this.email()).subscribe({
      next: (res) => {
        this.resendLoading.set(false);
        this.resendMessage.set(res.message);
      },
      error: (_err: HttpErrorResponse) => {
        this.resendLoading.set(false);
        // Never reveal enumeration info even on unexpected errors.
        this.resendMessage.set(
          'If that email is registered and unverified, a verification link has been sent.',
        );
      },
    });
  }
}
