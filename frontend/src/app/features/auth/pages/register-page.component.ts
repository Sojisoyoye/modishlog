import { Component, ChangeDetectionStrategy, signal, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { NgClass } from '@angular/common';
import { AuthService, RegisterRequest } from '../../../core/services/auth.service';

@Component({
  selector: 'app-register-page',
  standalone: true,
  imports: [FormsModule, RouterLink, NgClass],
  changeDetection: ChangeDetectionStrategy.OnPush,
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
          <div class="mb-6 text-center lg:hidden">
            <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-xl font-bold text-white shadow-lg">
              M
            </div>
            <span class="text-2xl font-bold text-gray-900">ModishLog</span>
          </div>

          <h2 class="mb-6 text-2xl font-bold text-gray-900">Create your account</h2>

          <!-- Step progress pills -->
          <div class="mb-6 flex items-center gap-3">
            <span
              [ngClass]="{
                'bg-emerald-600 text-white': currentStep() === 1,
                'bg-gray-100 text-gray-500': currentStep() !== 1
              }"
              class="rounded-full px-4 py-1.5 text-sm font-semibold transition-colors"
            >
              1 &middot; Account
            </span>
            <span class="text-gray-300 text-lg font-light">&#8594;</span>
            <span
              [ngClass]="{
                'bg-emerald-600 text-white': currentStep() === 2,
                'bg-gray-100 text-gray-500': currentStep() !== 2
              }"
              class="rounded-full px-4 py-1.5 text-sm font-semibold transition-colors"
            >
              2 &middot; Business
            </span>
          </div>

          <!-- Error banner -->
          @if (errorMsg()) {
            <div
              role="alert"
              aria-live="polite"
              class="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-danger"
            >
              <i class="pi pi-exclamation-circle"></i>
              {{ errorMsg() }}
            </div>
          }

          <!-- ======================== STEP 1: Account ======================== -->
          @if (currentStep() === 1) {
            <form (ngSubmit)="goToStep2()">
              <!-- Full name -->
              <div class="mb-4">
                <label for="reg-full-name" class="mb-1.5 block text-sm font-medium text-gray-700">
                  Full name <span class="text-danger">*</span>
                </label>
                <div class="relative">
                  <i class="pi pi-user absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-full-name"
                    type="text"
                    [(ngModel)]="fullName"
                    name="fullName"
                    autocomplete="name"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="Jane Doe"
                    required
                  />
                </div>
              </div>

              <!-- Email -->
              <div class="mb-4">
                <label for="reg-email" class="mb-1.5 block text-sm font-medium text-gray-700">
                  Email <span class="text-danger">*</span>
                </label>
                <div class="relative">
                  <i class="pi pi-envelope absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-email"
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

              <!-- Password -->
              <div class="mb-4">
                <label for="reg-password" class="mb-1.5 block text-sm font-medium text-gray-700">
                  Password <span class="text-danger">*</span>
                </label>
                <div class="relative">
                  <i class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-password"
                    [type]="showPassword() ? 'text' : 'password'"
                    [(ngModel)]="password"
                    name="password"
                    autocomplete="new-password"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10 pr-10"
                    placeholder="At least 8 characters"
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

              <!-- Confirm password -->
              <div class="mb-6">
                <label for="reg-confirm-password" class="mb-1.5 block text-sm font-medium text-gray-700">
                  Confirm password <span class="text-danger">*</span>
                </label>
                <div class="relative">
                  <i class="pi pi-lock absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-confirm-password"
                    [type]="showPassword() ? 'text' : 'password'"
                    [(ngModel)]="confirmPassword"
                    name="confirmPassword"
                    autocomplete="new-password"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="Repeat your password"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                class="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-white transition-colors hover:bg-secondary disabled:opacity-50 min-h-[44px] flex items-center justify-center gap-2"
              >
                Next &rarr;
              </button>
            </form>
          } @else {
            <!-- ======================== STEP 2: Business ======================== -->
            <form (ngSubmit)="onRegister()">
              <!-- Business name -->
              <div class="mb-4">
                <label for="reg-business-name" class="mb-1.5 block text-sm font-medium text-gray-700">
                  Business name <span class="text-danger">*</span>
                </label>
                <div class="relative">
                  <i class="pi pi-shop absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-business-name"
                    type="text"
                    [(ngModel)]="businessName"
                    name="businessName"
                    autocomplete="organization"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="e.g. Adaeze's Fashion Store"
                    required
                  />
                </div>
              </div>

              <!-- Currency -->
              <div class="mb-4">
                <label for="reg-currency" class="mb-1.5 block text-sm font-medium text-gray-700">Currency</label>
                <select
                  id="reg-currency"
                  [(ngModel)]="currency"
                  name="currency"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px]"
                >
                  <option value="NGN">NGN — Nigerian Naira</option>
                  <option value="USD">USD — US Dollar</option>
                  <option value="GBP">GBP — British Pound</option>
                  <option value="EUR">EUR — Euro</option>
                </select>
              </div>

              <!-- Timezone -->
              <div class="mb-4">
                <label for="reg-timezone" class="mb-1.5 block text-sm font-medium text-gray-700">Timezone</label>
                <select
                  id="reg-timezone"
                  [(ngModel)]="timezone"
                  name="timezone"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px]"
                >
                  <option value="Africa/Lagos">Africa/Lagos (WAT, UTC+1)</option>
                  <option value="Africa/Accra">Africa/Accra (GMT, UTC+0)</option>
                  <option value="Africa/Nairobi">Africa/Nairobi (EAT, UTC+3)</option>
                  <option value="Europe/London">Europe/London (GMT/BST)</option>
                  <option value="America/New_York">America/New_York (ET)</option>
                  <option value="America/Los_Angeles">America/Los_Angeles (PT)</option>
                  <option value="UTC">UTC</option>
                </select>
              </div>

              <!-- Country (optional) -->
              <div class="mb-4">
                <label for="reg-country" class="mb-1.5 block text-sm font-medium text-gray-700">Country <span class="text-gray-400 text-xs">(optional)</span></label>
                <div class="relative">
                  <i class="pi pi-map-marker absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-country"
                    type="text"
                    [(ngModel)]="country"
                    name="country"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="e.g. Nigeria"
                  />
                </div>
              </div>

              <!-- City (optional) -->
              <div class="mb-4">
                <label for="reg-city" class="mb-1.5 block text-sm font-medium text-gray-700">City <span class="text-gray-400 text-xs">(optional)</span></label>
                <div class="relative">
                  <i class="pi pi-building absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-city"
                    type="text"
                    [(ngModel)]="city"
                    name="city"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="e.g. Lagos"
                  />
                </div>
              </div>

              <!-- Phone (optional) -->
              <div class="mb-6">
                <label for="reg-phone" class="mb-1.5 block text-sm font-medium text-gray-700">Phone <span class="text-gray-400 text-xs">(optional)</span></label>
                <div class="relative">
                  <i class="pi pi-phone absolute left-3 top-1/2 -translate-y-1/2 text-sm text-gray-400"></i>
                  <input
                    id="reg-phone"
                    type="tel"
                    [(ngModel)]="phone"
                    name="phone"
                    autocomplete="tel"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary min-h-[44px] pl-10"
                    placeholder="+234 800 000 0000"
                  />
                </div>
              </div>

              <!-- Action buttons -->
              <div class="flex items-center gap-3">
                <button
                  type="button"
                  (click)="goBack()"
                  class="flex-none rounded-lg border border-gray-300 px-5 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 min-h-[44px]"
                >
                  &larr; Back
                </button>
                <button
                  type="submit"
                  [disabled]="isLoading()"
                  class="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-white transition-colors hover:bg-secondary disabled:opacity-50 min-h-[44px] flex items-center justify-center gap-2"
                >
                  @if (isLoading()) {
                    <i class="pi pi-spinner pi-spin text-sm"></i>
                    Creating account...
                  } @else {
                    Create Account
                  }
                </button>
              </div>
            </form>
          }

          <!-- Footer -->
          <p class="mt-8 text-center text-xs text-gray-400">
            Already have an account?
            <a routerLink="/login" class="text-emerald-600 hover:underline">Log in</a>
          </p>
        </div>
      </div>
    </div>
  `,
})
export class RegisterPageComponent {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  currentStep = signal<1 | 2>(1);
  isLoading = signal(false);
  errorMsg = signal<string | null>(null);

  // Step 1 fields
  fullName = '';
  email = '';
  password = '';
  confirmPassword = '';
  showPassword = signal(false);

  // Step 2 fields
  businessName = '';
  currency = 'NGN';
  timezone = 'Africa/Lagos';
  country = '';
  state = '';
  city = '';
  phone = '';
  taxNumber = '';
  fiscalYearStartMonth = 1;

  goToStep2(): void {
    if (!this.fullName.trim() || !this.email.trim() || !this.password) {
      this.errorMsg.set('Please fill in all required fields.');
      return;
    }
    if (this.password !== this.confirmPassword) {
      this.errorMsg.set('Passwords do not match.');
      return;
    }
    this.errorMsg.set(null);
    this.currentStep.set(2);
  }

  goBack(): void {
    this.errorMsg.set(null);
    this.currentStep.set(1);
  }

  onRegister(): void {
    if (!this.businessName.trim()) {
      this.errorMsg.set('Business name is required.');
      return;
    }
    this.isLoading.set(true);
    this.errorMsg.set(null);

    const payload: RegisterRequest = {
      full_name: this.fullName,
      email: this.email,
      password: this.password,
      business_name: this.businessName,
      currency: this.currency,
      timezone: this.timezone,
      fiscal_year_start_month: this.fiscalYearStartMonth,
    };

    if (this.country) payload.country = this.country;
    if (this.state) payload.state = this.state;
    if (this.city) payload.city = this.city;
    if (this.phone) payload.phone = this.phone;
    if (this.taxNumber) payload.tax_number = this.taxNumber;

    this.authService.register(payload).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.router.navigate(['/dashboard']);
      },
      error: (err: { error?: { detail?: string | Array<{ msg: string }> } }) => {
        this.isLoading.set(false);
        const detail = err?.error?.detail;
        const msg = Array.isArray(detail)
          ? detail.map((d) => d.msg).join('; ')
          : (detail ?? 'Registration failed. Please try again.');
        this.errorMsg.set(msg);
      },
    });
  }
}
