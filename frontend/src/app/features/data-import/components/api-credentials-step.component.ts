import { Component, ChangeDetectionStrategy, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ImportService } from '../services/import.service';
import { ApiCredentials, MigrationJob, SourceSystem, TestConnectionResponse } from '../models/import.models';

@Component({
  selector: 'app-api-credentials-step',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h3 class="mb-1 text-lg font-semibold text-text">Connect to {{ sourceLabel() }}</h3>
    <p class="mb-5 text-sm text-muted">
      Enter your connection details below. Credentials are used once to connect and are never stored.
    </p>

    <div class="max-w-md space-y-4 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <div>
        <label class="mb-1 block text-sm font-medium text-text">{{ urlLabel() }}</label>
        <input
          type="text"
          [(ngModel)]="apiBaseUrl"
          [placeholder]="urlPlaceholder()"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none min-h-[40px]"
        />
      </div>

      @if (sourceSystem() === 'ultimatepos') {
        <div>
          <label class="mb-1 block text-sm font-medium text-text">Username</label>
          <input
            type="text"
            [(ngModel)]="username"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none min-h-[40px]"
          />
        </div>
        <div>
          <label class="mb-1 block text-sm font-medium text-text">Password</label>
          <input
            type="password"
            [(ngModel)]="password"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none min-h-[40px]"
          />
        </div>
      } @else {
        <div>
          <label class="mb-1 block text-sm font-medium text-text">Access Token</label>
          <input
            type="password"
            [(ngModel)]="accessToken"
            class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none min-h-[40px]"
          />
          <p class="mt-1 text-xs text-muted">{{ tokenHelpText() }}</p>
        </div>
      }

      <button
        (click)="testConnection()"
        [disabled]="!canTest() || testing()"
        class="w-full rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40 min-h-[40px]"
      >
        @if (testing()) {
          <i class="pi pi-spinner pi-spin mr-1"></i> Testing connection...
        } @else {
          Test connection
        }
      </button>

      @if (testResult(); as result) {
        <div class="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm">
          <p class="font-medium text-emerald-800">
            <i class="pi pi-check-circle mr-1"></i> Connected to {{ sourceLabel() }}
          </p>
          <p class="mt-2 font-medium text-text">What we found:</p>
          <ul class="mt-1 space-y-0.5 text-gray-700">
            @for (entry of countEntries(result); track entry[0]) {
              <li class="flex justify-between">
                <span class="capitalize">{{ entry[0].replace('_', ' ') }}</span>
                <span class="font-medium">{{ entry[1] | number }}</span>
              </li>
            }
          </ul>
          @if (result.date_range?.earliest) {
            <p class="mt-2 text-xs text-muted">
              Sales history: {{ result.date_range!.earliest }} – {{ result.date_range!.latest }}
            </p>
          }
        </div>
      }

      @if (testError()) {
        <div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <i class="pi pi-exclamation-circle mr-1"></i> {{ testError() }}
        </div>
      }
    </div>

    <div class="mt-6 flex justify-between">
      <button (click)="back.emit()" class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]">
        Back
      </button>
      <button
        (click)="submit()"
        [disabled]="!testResult() || submitting()"
        class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-40 min-h-[40px]"
      >
        @if (submitting()) {
          <i class="pi pi-spinner pi-spin mr-1"></i> Connecting...
        } @else {
          Continue
        }
      </button>
    </div>
  `,
})
export class ApiCredentialsStepComponent {
  private readonly importService = inject(ImportService);

  sourceSystem = input.required<SourceSystem>();
  back = output<void>();
  jobCreated = output<MigrationJob>();
  failed = output<string>();

  apiBaseUrl = '';
  username = '';
  password = '';
  accessToken = '';

  testing = signal(false);
  submitting = signal(false);
  testResult = signal<TestConnectionResponse | null>(null);
  testError = signal<string | null>(null);

  sourceLabel(): string {
    const labels: Record<SourceSystem, string> = {
      ultimatepos: 'UltimatePOS',
      quickbooks: 'QuickBooks',
      shopify: 'Shopify',
      generic: 'Generic CSV',
    };
    return labels[this.sourceSystem()];
  }

  urlLabel(): string {
    return this.sourceSystem() === 'shopify' ? 'Store admin API URL' : 'Store URL';
  }

  urlPlaceholder(): string {
    switch (this.sourceSystem()) {
      case 'ultimatepos':
        return 'https://pos.yourstore.com';
      case 'shopify':
        return 'https://mystore.myshopify.com/admin/api/2024-01';
      case 'quickbooks':
        return 'https://quickbooks.api.intuit.com/v3/company/{realm_id}';
      default:
        return '';
    }
  }

  tokenHelpText(): string {
    if (this.sourceSystem() === 'shopify') {
      return 'Generate an Admin API access token from a custom app in your Shopify admin (Settings → Apps → Develop apps).';
    }
    return 'Obtain an access token via the QuickBooks Developer Portal / OAuth Playground for your app.';
  }

  private buildCredentials(): ApiCredentials {
    return {
      api_base_url: this.apiBaseUrl.trim(),
      username: this.username.trim() || undefined,
      password: this.password || undefined,
      access_token: this.accessToken.trim() || undefined,
    };
  }

  canTest(): boolean {
    if (!this.apiBaseUrl.trim()) return false;
    if (this.sourceSystem() === 'ultimatepos') return !!this.username.trim() && !!this.password;
    return !!this.accessToken.trim();
  }

  countEntries(result: TestConnectionResponse): [string, number][] {
    return Object.entries(result.counts || {});
  }

  testConnection(): void {
    this.testing.set(true);
    this.testError.set(null);
    this.testResult.set(null);
    this.importService.testConnection(this.sourceSystem(), this.buildCredentials()).subscribe({
      next: (result) => {
        this.testing.set(false);
        this.testResult.set(result);
      },
      error: (err) => {
        this.testing.set(false);
        this.testError.set(err?.error?.detail || 'Could not connect — check your URL and credentials.');
      },
    });
  }

  submit(): void {
    this.submitting.set(true);
    this.importService.createApiJob(this.sourceSystem(), this.buildCredentials()).subscribe({
      next: (job) => {
        this.submitting.set(false);
        this.jobCreated.emit(job);
      },
      error: (err) => {
        this.submitting.set(false);
        const message = err?.error?.detail || 'Failed to start import';
        this.testError.set(message);
        this.failed.emit(message);
      },
    });
  }
}
