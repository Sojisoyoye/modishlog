import { Component, ChangeDetectionStrategy, OnInit, inject, signal, computed, DestroyRef } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { SettingsService } from '../../../core/services/settings.service';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];
const MONTH_MAX_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

@Component({
  selector: 'app-settings-page',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div>
      <div class="mb-6">
        <h2 class="text-2xl font-bold text-text">Settings</h2>
        <p class="mt-1 text-sm text-muted">Manage API keys and alert thresholds</p>
      </div>

      <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <!-- API Key Section -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50">
              <i class="pi pi-key text-sm text-secondary"></i>
            </div>
            <h3 class="text-base font-semibold text-text">API Key</h3>
          </div>
          <div class="space-y-4">
            @if (apiKeyConfigured()) {
              <div class="flex flex-col gap-2 rounded-lg bg-green-50 px-4 py-3 text-sm text-success">
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
                  <p class="text-xs text-success">API key saved successfully</p>
                }
              </div>
            } @else {
              <div>
                <label class="mb-1.5 block text-xs font-medium text-muted">API Key</label>
                <div class="relative">
                  <input
                    [type]="apiKeyVisible() ? 'text' : 'password'"
                    [(ngModel)]="apiKey"
                    placeholder="Enter your API key"
                    class="w-full rounded-lg border border-gray-300 px-3 py-2.5 pr-10 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
                  />
                  <button
                    (click)="apiKeyVisible.set(!apiKeyVisible())"
                    class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 transition-colors hover:text-text"
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
                  class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
                >
                  <i class="pi pi-save text-sm"></i> Save
                </button>
                <button
                  (click)="testApiKey()"
                  class="flex items-center gap-1.5 rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-muted transition-colors hover:bg-gray-50 hover:text-text"
                >
                  <i class="pi pi-play text-sm"></i> Test Connection
                </button>
              </div>
              @if (apiKeyStatus()) {
                <div
                  class="rounded-lg p-3 text-sm"
                  [class]="apiKeyStatus() === 'saved' ? 'bg-green-50 text-success' : 'bg-gray-50 text-muted'"
                >
                  <i class="pi mr-1 text-xs" [class]="apiKeyStatus() === 'saved' ? 'pi-check-circle' : 'pi-info-circle'"></i>
                  {{ apiKeyStatus() === 'saved' ? 'API key saved successfully' : 'Test connection feature coming soon' }}
                </div>
              }
            }
          </div>
        </div>

        <!-- FX Alert Thresholds Section -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50">
              <i class="pi pi-bell text-sm text-danger"></i>
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
                  <i class="pi pi-money-bill text-lg text-warning"></i>
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
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-green-50">
              <i class="pi pi-calendar text-sm text-success"></i>
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
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
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
                  class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-muted"
                />
                @if (fyDayWarning()) {
                  <p class="mt-1 text-xs text-warning">{{ fyDayWarning() }}</p>
                }
              </div>
            </div>
            <button
              (click)="saveFiscalYear()"
              [disabled]="fysSaving()"
              class="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-primary/90 hover:shadow-md disabled:opacity-50"
            >
              <i class="pi pi-save text-sm"></i> Save Fiscal Year
            </button>
            @if (fyStatus() === 'saved') {
              <div class="rounded-lg bg-green-50 p-3 text-sm text-success">
                <i class="pi pi-check-circle mr-1 text-xs"></i>Fiscal year start saved
              </div>
            }
            @if (fyStatus() === 'error') {
              <div class="rounded-lg bg-red-50 p-3 text-sm text-danger">
                <i class="pi pi-times-circle mr-1 text-xs"></i>Failed to save — check the day value and try again
              </div>
            }
          </div>
        </div>

        <!-- General Preferences -->
        <div class="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div class="mb-5 flex items-center gap-2">
            <div class="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-50">
              <i class="pi pi-sliders-h text-sm text-purple-600"></i>
            </div>
            <h3 class="text-base font-semibold text-text">General Preferences</h3>
          </div>
          <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label class="mb-1.5 block text-xs font-medium text-muted">Default Currency Pair</label>
              <select
                [(ngModel)]="defaultPair"
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
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
                class="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm transition-colors focus:border-primary focus:ring-1 focus:ring-primary"
              />
            </div>
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
  private readonly destroyRef = inject(DestroyRef);

  readonly monthNames = MONTH_NAMES;

  apiKey = '';
  apiKeyVisible = signal(false);
  apiKeyStatus = signal<'saved' | 'testing' | null>(null);
  apiKeyConfigured = signal(false);
  saving = signal(false);
  defaultPair = 'USDNGN';
  globalStockThreshold = 10;

  fyMonth = signal('');
  fyDay = signal<number | null>(null);
  fysSaving = signal(false);
  fyStatus = signal<'saved' | 'error' | null>(null);

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

  testApiKey(): void {
    this.apiKeyStatus.set('testing');
  }
}
