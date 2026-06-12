import { Component, ChangeDetectionStrategy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { SettingsService } from '../../../core/services/settings.service';

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
              <div class="flex items-center gap-2 rounded-lg bg-green-50 px-4 py-3 text-sm text-success">
                <i class="pi pi-check-circle text-xs"></i>
                <span>Configured</span>
                <button
                  (click)="apiKeyConfigured.set(false)"
                  class="ml-auto text-xs text-muted underline hover:text-text"
                  type="button"
                >
                  Update
                </button>
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

  apiKey = '';
  apiKeyVisible = signal(false);
  apiKeyStatus = signal<'saved' | 'testing' | null>(null);
  apiKeyConfigured = signal(false);
  saving = signal(false);
  defaultPair = 'USDNGN';
  globalStockThreshold = 10;

  ngOnInit(): void {
    this.settingsService.getApiKeyStatus('anthropic').subscribe({
      next: (status) => this.apiKeyConfigured.set(status.is_configured),
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

  testApiKey(): void {
    this.apiKeyStatus.set('testing');
  }
}
