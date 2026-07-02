import { Component, ChangeDetectionStrategy, ChangeDetectorRef, OnInit, inject, signal, computed, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Toast } from 'primeng/toast';
import { SettingsService, BusinessProfile } from '../../../core/services/settings.service';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];
const MONTH_MAX_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [FormsModule, RouterLink, Toast],
  template: `
    <p-toast />
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-gray-900">Settings</h2>
        <p class="mt-1 text-sm text-gray-500">Manage business profile, API keys and preferences</p>
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">

        <!-- Business Profile Section -->
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-building text-sm text-blue-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Business Profile</h3>
          </div>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Business Name</label>
              <input
                type="text"
                [(ngModel)]="bpForm.business_name"
                placeholder="e.g. Ade Traders Ltd"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Phone</label>
              <input
                type="text"
                [(ngModel)]="bpForm.phone"
                placeholder="e.g. +234 801 234 5678"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Email</label>
              <input
                type="email"
                [(ngModel)]="bpForm.email"
                placeholder="info@business.com"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Address</label>
              <input
                type="text"
                [(ngModel)]="bpForm.address_line_1"
                placeholder="123 Market Street"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">City</label>
              <input
                type="text"
                [(ngModel)]="bpForm.city"
                placeholder="e.g. Lagos"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Country</label>
              <input
                type="text"
                [(ngModel)]="bpForm.country"
                placeholder="e.g. Nigeria"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Tax Number</label>
              <input
                type="text"
                [(ngModel)]="bpForm.tax_number"
                placeholder="e.g. TIN-1234567"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Currency</label>
              <select
                [(ngModel)]="bpForm.currency"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              >
                <option value="NGN">NGN — Nigerian Naira</option>
                <option value="USD">USD — US Dollar</option>
                <option value="GBP">GBP — British Pound</option>
                <option value="EUR">EUR — Euro</option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Timezone</label>
              <select
                [(ngModel)]="bpForm.timezone"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              >
                <option value="Africa/Lagos">Africa/Lagos (WAT +01:00)</option>
                <option value="UTC">UTC</option>
                <option value="Europe/London">Europe/London (GMT/BST)</option>
                <option value="America/New_York">America/New_York (EST/EDT)</option>
              </select>
            </div>
          </div>
          <div class="mt-4 flex items-center gap-3">
            <button
              (click)="saveBusinessProfile()"
              [disabled]="bpSaving()"
              class="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:opacity-50 min-h-[44px]"
            >
              <i class="pi pi-save text-sm"></i> Save Business Profile
            </button>
            @if (bpStatus() === 'saved') {
              <span class="text-sm text-emerald-600"><i class="pi pi-check-circle mr-1 text-xs"></i>Saved</span>
            }
            @if (bpStatus() === 'error') {
              <span class="text-sm text-red-600"><i class="pi pi-times-circle mr-1 text-xs"></i>Failed to save</span>
            }
          </div>
        </div>

        <!-- API Key Section -->
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
              <i class="pi pi-key text-sm text-purple-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">API Key</h3>
          </div>
          <div class="space-y-4">
            @if (apiKeyConfigured()) {
              <div class="flex flex-col gap-2 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                <div class="flex items-center gap-2">
                  <i class="pi pi-check-circle text-xs"></i>
                  <span>Configured</span>
                  <button
                    (click)="apiKeyConfigured.set(false); apiKeyStatus.set(null)"
                    class="ml-auto text-xs text-muted underline hover:text-text"
                    type="button"
                  >
                    Update
                  </button>
                </div>
                @if (apiKeyStatus() === 'saved') {
                  <p class="text-xs text-emerald-700">API key saved successfully</p>
                }
              </div>
              <button
                (click)="testApiKey()"
                [disabled]="apiKeyTesting()"
                class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 min-h-[44px]"
              >
                @if (apiKeyTesting()) {
                  <i class="pi pi-spin pi-spinner text-sm"></i>
                } @else {
                  <i class="pi pi-play text-sm"></i>
                }
                Test Connection
              </button>
              @if (apiKeyTestResult()) {
                <div
                  class="rounded-lg p-3 text-sm"
                  [class]="apiKeyTestResult()!.success ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'"
                >
                  <i class="pi mr-1 text-xs" [class]="apiKeyTestResult()!.success ? 'pi-check-circle' : 'pi-times-circle'"></i>
                  {{ apiKeyTestResult()!.message }}
                  @if (apiKeyTestResult()!.latency_ms !== null) {
                    <span class="ml-2 text-xs opacity-70">({{ apiKeyTestResult()!.latency_ms }}ms)</span>
                  }
                </div>
              }
            } @else {
              <div>
                <label class="mb-1.5 block text-xs font-medium text-muted">API Key</label>
                <div class="relative">
                  <input
                    [type]="apiKeyVisible() ? 'text' : 'password'"
                    [(ngModel)]="apiKey"
                    placeholder="Enter your API key"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 pr-10 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
                  />
                  <button
                    (click)="apiKeyVisible.set(!apiKeyVisible())"
                    class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-text min-h-[44px] min-w-[44px] flex items-center justify-center"
                    type="button"
                  >
                    <i class="pi text-sm" [class]="apiKeyVisible() ? 'pi-eye-slash' : 'pi-eye'"></i>
                  </button>
                </div>
              </div>
              <div class="flex gap-2">
                <button
                  (click)="saveApiKey()"
                  [disabled]="saving()"
                  class="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:opacity-50 min-h-[44px]"
                >
                  <i class="pi pi-save text-sm"></i> Save
                </button>
              </div>
              @if (apiKeyStatus() === 'saved') {
                <div class="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
                  <i class="pi pi-check-circle mr-1 text-xs"></i>API key saved successfully
                </div>
              }
            }
          </div>
        </div>

        <!-- FX Alert Thresholds Section -->
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-50">
              <i class="pi pi-bell text-sm text-amber-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">FX Alert Thresholds</h3>
          </div>
          <div class="space-y-4">
            <p class="text-sm text-muted">
              Configure rate alert thresholds on the FX Rates page. Alerts notify you when
              exchange rates cross your defined thresholds.
            </p>
            <div class="rounded-lg bg-gray-50 p-4">
              <div class="flex items-center gap-3">
                <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-100">
                  <i class="pi pi-money-bill text-lg text-amber-700"></i>
                </div>
                <div>
                  <p class="text-sm font-semibold text-text">Manage FX Alerts</p>
                  <p class="text-xs text-muted">Create and manage rate alerts from the FX page</p>
                </div>
              </div>
            </div>
            <a
              routerLink="/fx"
              class="flex items-center gap-1.5 rounded-lg border border-secondary px-4 py-2.5 text-sm font-semibold text-secondary transition-all hover:bg-secondary hover:text-white"
            >
              <i class="pi pi-external-link text-sm"></i> Go to FX Rates
            </a>
          </div>
        </div>

        <!-- Fiscal Year Section -->
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-calendar text-sm text-blue-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">Fiscal Year</h3>
          </div>
          <div class="space-y-4">
            <p class="text-sm text-muted">
              Set the start of your financial year. Reports will default to this date. Leave as
              <em>Not configured</em> to use a rolling 365-day window.
            </p>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label for="fy-month" class="mb-1.5 block text-xs font-medium text-muted">Start Month</label>
                <select
                  id="fy-month"
                  [ngModel]="fyMonth()"
                  (ngModelChange)="fyMonth.set($event); fyDay.set(null); fyStatus.set(null)"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
                >
                  <option value="">Not configured</option>
                  @for (name of monthNames; track $index) {
                    <option [value]="'' + ($index + 1)">{{ name }}</option>
                  }
                </select>
              </div>
              <div>
                <label for="fy-day" class="mb-1.5 block text-xs font-medium text-muted">Start Day</label>
                <input
                  id="fy-day"
                  type="number"
                  [ngModel]="fyDay()"
                  (ngModelChange)="fyDay.set($event ? +$event : null); fyStatus.set(null)"
                  [disabled]="!fyMonth()"
                  min="1"
                  max="31"
                  placeholder="Day"
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-muted min-h-[44px]"
                />
                @if (fyDayWarning()) {
                  <p class="mt-1 text-xs text-warning">{{ fyDayWarning() }}</p>
                }
              </div>
            </div>
            <button
              (click)="saveFiscalYear()"
              [disabled]="fysSaving()"
              class="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:opacity-50 min-h-[44px]"
            >
              <i class="pi pi-save text-sm"></i> Save Fiscal Year
            </button>
            @if (fyStatus() === 'saved') {
              <div class="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
                <i class="pi pi-check-circle mr-1 text-xs"></i>Fiscal year start saved
              </div>
            }
            @if (fyStatus() === 'error') {
              <div class="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                <i class="pi pi-times-circle mr-1 text-xs"></i>Failed to save — check the day value and try again
              </div>
            }
          </div>
        </div>

        <!-- General Preferences -->
        <div class="rounded-xl border border-gray-100 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50">
              <i class="pi pi-sliders-h text-sm text-emerald-700"></i>
            </div>
            <h3 class="text-base font-semibold text-text">General Preferences</h3>
          </div>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Default Currency Pair</label>
              <select
                [(ngModel)]="defaultPair"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              >
                <option value="USDNGN">USD/NGN</option>
                <option value="EURUSD">EUR/USD</option>
              </select>
            </div>
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Low Stock Alert Threshold (Global Default)</label>
              <input
                type="number"
                [(ngModel)]="globalStockThreshold"
                min="0"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 min-h-[44px]"
              />
            </div>
          </div>
          <div class="mt-4 flex items-center gap-3">
            <button
              (click)="savePreferences()"
              [disabled]="prefSaving()"
              class="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-emerald-700 hover:shadow-md disabled:opacity-50 min-h-[44px]"
            >
              <i class="pi pi-save text-sm"></i> Save Preferences
            </button>
            @if (prefStatus() === 'saved') {
              <span class="text-sm text-emerald-600"><i class="pi pi-check-circle mr-1 text-xs"></i>Saved</span>
            }
            @if (prefStatus() === 'error') {
              <span class="text-sm text-red-600"><i class="pi pi-times-circle mr-1 text-xs"></i>Failed to save</span>
            }
          </div>
          <p class="mt-4 text-xs text-muted">
            <i class="pi pi-info-circle mr-1 text-[10px]"></i>
            Per-product thresholds can be edited directly in the Inventory page.
          </p>
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SettingsPageComponent implements OnInit {
  private readonly settingsService = inject(SettingsService);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);

  readonly monthNames = MONTH_NAMES;

  // Business Profile
  bpForm: Partial<BusinessProfile> = {
    business_name: null,
    address_line_1: null,
    city: null,
    state: null,
    country: null,
    zip_code: null,
    phone: null,
    email: null,
    tax_number: null,
    currency: 'NGN',
    timezone: 'Africa/Lagos',
  };
  bpSaving = signal(false);
  bpStatus = signal<'saved' | 'error' | null>(null);

  // API Key
  apiKey = '';
  apiKeyVisible = signal(false);
  apiKeyStatus = signal<'saved' | null>(null);
  apiKeyConfigured = signal(false);
  apiKeyTesting = signal(false);
  apiKeyTestResult = signal<{ success: boolean; message: string; latency_ms: number | null } | null>(null);
  saving = signal(false);

  // Fiscal Year
  fyMonth = signal('');
  fyDay = signal<number | null>(null);
  fysSaving = signal(false);
  fyStatus = signal<'saved' | 'error' | null>(null);

  // Preferences
  defaultPair = 'USDNGN';
  globalStockThreshold = 10;
  prefSaving = signal(false);
  prefStatus = signal<'saved' | 'error' | null>(null);

  fyDayWarning = computed(() => {
    const m = parseInt(this.fyMonth(), 10);
    const d = this.fyDay();
    if (!m || d === null) return null;
    const max = MONTH_MAX_DAYS[m - 1];
    if (d > max) return `${MONTH_NAMES[m - 1]} has at most ${max} days`;
    return null;
  });

  ngOnInit(): void {
    this.settingsService.getApiKeyStatus('anthropic').subscribe({
      next: (status) => this.apiKeyConfigured.set(status.is_configured),
      error: () => {},
    });
    this.settingsService
      .getFiscalYearStart()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (fy) => {
          this.fyMonth.set(fy.fiscal_year_start_month ? String(fy.fiscal_year_start_month) : '');
          this.fyDay.set(fy.fiscal_year_start_day ?? null);
        },
        error: () => {},
      });
    this.settingsService
      .getBusinessProfile()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (bp) => {
          this.bpForm = {
            business_name: bp.business_name,
            address_line_1: bp.address_line_1,
            city: bp.city,
            state: bp.state,
            country: bp.country,
            zip_code: bp.zip_code,
            phone: bp.phone,
            email: bp.email,
            tax_number: bp.tax_number,
            currency: bp.currency,
            timezone: bp.timezone,
          };
          this.cdr.markForCheck();
        },
        error: () => {},
      });
    this.settingsService
      .getAppSettings()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (settings) => {
          this.defaultPair = settings['default_currency_pair'] ?? 'USDNGN';
          this.globalStockThreshold = parseInt(settings['global_low_stock_threshold'] ?? '10', 10);
          this.cdr.markForCheck();
        },
        error: () => {},
      });
  }

  saveBusinessProfile(): void {
    this.bpSaving.set(true);
    this.bpStatus.set(null);
    this.settingsService.updateBusinessProfile(this.bpForm).subscribe({
      next: () => {
        this.bpSaving.set(false);
        this.bpStatus.set('saved');
      },
      error: () => {
        this.bpSaving.set(false);
        this.bpStatus.set('error');
      },
    });
  }

  saveApiKey(): void {
    if (!this.apiKey.trim()) return;
    this.saving.set(true);
    this.settingsService.saveApiKey('anthropic', this.apiKey).subscribe({
      next: () => {
        this.apiKey = '';
        this.apiKeyConfigured.set(true);
        this.apiKeyStatus.set('saved');
        this.saving.set(false);
      },
      error: () => {
        this.saving.set(false);
      },
    });
  }

  testApiKey(): void {
    this.apiKeyTesting.set(true);
    this.apiKeyTestResult.set(null);
    this.settingsService.testApiKey('anthropic').subscribe({
      next: (result) => {
        this.apiKeyTesting.set(false);
        this.apiKeyTestResult.set(result);
      },
      error: () => {
        this.apiKeyTesting.set(false);
        this.apiKeyTestResult.set({ success: false, message: 'Connection test failed', latency_ms: null });
      },
    });
  }

  saveFiscalYear(): void {
    const month = this.fyMonth() ? parseInt(this.fyMonth(), 10) : null;
    const day = this.fyMonth() ? this.fyDay() : null;
    if (month !== null && day === null) {
      this.fyStatus.set('error');
      return;
    }
    this.fysSaving.set(true);
    this.fyStatus.set(null);
    this.settingsService.updateFiscalYearStart(month, day).subscribe({
      next: () => {
        this.fysSaving.set(false);
        this.fyStatus.set('saved');
      },
      error: () => {
        this.fysSaving.set(false);
        this.fyStatus.set('error');
      },
    });
  }

  savePreferences(): void {
    this.prefSaving.set(true);
    this.prefStatus.set(null);
    const pair$ = this.settingsService.updateAppSetting('default_currency_pair', this.defaultPair);
    const threshold$ = this.settingsService.updateAppSetting('global_low_stock_threshold', String(this.globalStockThreshold));
    let done = 0;
    const onDone = () => {
      done++;
      if (done === 2) {
        this.prefSaving.set(false);
        this.prefStatus.set('saved');
      }
    };
    pair$.subscribe({ next: onDone, error: () => { this.prefSaving.set(false); this.prefStatus.set('error'); } });
    threshold$.subscribe({ next: onDone, error: () => { this.prefSaving.set(false); this.prefStatus.set('error'); } });
  }
}
