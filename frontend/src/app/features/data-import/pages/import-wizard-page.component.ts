import { Component, ChangeDetectionStrategy, inject, signal, computed, OnInit } from '@angular/core';
import { DatePipe, Location } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { Toast } from 'primeng/toast';
import { ImportService } from '../services/import.service';
import {
  MigrationJob,
  SourceSystem,
  ExtractionMode,
  SOURCE_LABELS,
  humanizeKey,
  sumRowCounts,
  UNDO_CONFIRM_MESSAGE,
  UNDO_FAILED_MESSAGE,
} from '../models/import.models';
import { CsvUploadStepComponent } from '../components/csv-upload-step.component';
import { ApiCredentialsStepComponent } from '../components/api-credentials-step.component';
import { ValidateStepComponent } from '../components/validate-step.component';
import { ConfirmStepComponent } from '../components/confirm-step.component';
import { SummaryStepComponent } from '../components/summary-step.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';

type WizardStep =
  | 'history'
  | 'source'
  | 'method'
  | 'upload'
  | 'validate'
  | 'confirm'
  | 'summary';

interface SourceOption {
  system: SourceSystem;
  label: string;
  description: string;
  icon: string;
  supportsApi: boolean;
}

const SOURCE_OPTIONS: SourceOption[] = [
  {
    system: 'ultimatepos',
    label: SOURCE_LABELS.ultimatepos,
    description: 'Export from UltimatePOS/Laravel. We auto-detect your column names.',
    icon: 'pi-desktop',
    supportsApi: true,
  },
  {
    system: 'quickbooks',
    label: SOURCE_LABELS.quickbooks,
    description: 'Use QuickBooks CSV export (Items, Invoices, Bills, Vendors).',
    icon: 'pi-book',
    supportsApi: true,
  },
  {
    system: 'shopify',
    label: SOURCE_LABELS.shopify,
    description: "Use Shopify's built-in Products and Orders CSV export.",
    icon: 'pi-shopping-bag',
    supportsApi: true,
  },
  {
    system: 'generic',
    label: SOURCE_LABELS.generic,
    description: 'Use our templates. Works with any spreadsheet (Excel, Google Sheets).',
    icon: 'pi-file',
    supportsApi: false,
  },
];

@Component({
  selector: 'app-import-wizard-page',
  standalone: true,
  imports: [
    DatePipe,
    Toast,
    StatusBadgeComponent,
    CsvUploadStepComponent,
    ApiCredentialsStepComponent,
    ValidateStepComponent,
    ConfirmStepComponent,
    SummaryStepComponent,
  ],
  providers: [MessageService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p-toast />

    <div class="mb-6 flex items-center gap-3">
      <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
        <i class="pi pi-upload text-lg"></i>
      </div>
      <div>
        <h2 class="text-2xl font-bold text-text">Data Imports</h2>
        <p class="mt-0.5 text-sm text-muted">Migrate your existing data into ModishLog</p>
      </div>
    </div>

    @switch (step()) {
      @case ('history') {
        <div class="mb-4 flex justify-end">
          <button
            (click)="startNewImport()"
            class="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90 min-h-[40px]"
          >
            <i class="pi pi-plus text-sm"></i> Start New Import
          </button>
        </div>

        <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
          <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200 text-sm">
              <caption class="sr-only">Past data import jobs</caption>
              <thead>
                <tr class="bg-gray-50">
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Date</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Source</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Method</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Records</th>
                  <th class="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100">
                @for (job of history(); track job.id) {
                  <tr class="hover:bg-gray-50">
                    <td class="px-4 py-3 text-gray-700">{{ job.created_at | date: 'mediumDate' }}</td>
                    <td class="px-4 py-3 capitalize text-gray-700">{{ job.source_system }}</td>
                    <td class="px-4 py-3 uppercase text-gray-500">{{ job.extraction_mode }}</td>
                    <td class="px-4 py-3">
                      <app-status-badge [label]="statusLabel(job.status)" [status]="statusBadgeVariant(job.status)" />
                    </td>
                    <td class="px-4 py-3 text-right text-gray-700">{{ totalRows(job) }}</td>
                    <td class="px-4 py-3 text-right">
                      @if (job.status === 'done') {
                        <button
                          (click)="undoFromHistory(job)"
                          [disabled]="undoingJobIds().has(job.id)"
                          class="rounded px-2 py-1 text-xs text-muted hover:bg-red-50 hover:text-red-600 disabled:opacity-40"
                        >
                          @if (undoingJobIds().has(job.id)) {
                            Undoing...
                          } @else {
                            Undo
                          }
                        </button>
                      }
                    </td>
                  </tr>
                } @empty {
                  <tr>
                    <td colspan="6" class="py-12 text-center text-sm text-muted">
                      No imports yet. Start one to migrate your existing data.
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      }

      @case ('source') {
        <h3 class="mb-1 text-lg font-semibold text-text">Choose your source</h3>
        <p class="mb-5 text-sm text-muted">Where is your business data coming from?</p>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          @for (opt of sourceOptions; track opt.system) {
            <button
              type="button"
              (click)="selectedSource.set(opt.system)"
              [class]="sourceCardClass(opt.system)"
            >
              <i class="pi text-2xl text-primary" [class]="opt.icon"></i>
              <span class="mt-2 block font-semibold text-text">{{ opt.label }}</span>
              <span class="mt-1 block text-sm text-muted">{{ opt.description }}</span>
            </button>
          }
        </div>

        <div class="mt-6 flex justify-end">
          <button
            (click)="step.set('method')"
            [disabled]="!selectedSource()"
            class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-40 min-h-[40px]"
          >
            Next
          </button>
        </div>
      }

      @case ('method') {
        <h3 class="mb-1 text-lg font-semibold text-text">How do you want to import?</h3>
        <p class="mb-5 text-sm text-muted">Both options work — pick whichever is easier for you.</p>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <button
            type="button"
            (click)="supportsApi() ? selectedMode.set('api') : null"
            [disabled]="!supportsApi()"
            [class]="methodCardClass('api')"
            [title]="!supportsApi() ? 'Direct connection not available for this source. Use CSV upload.' : ''"
          >
            <i class="pi pi-bolt text-2xl text-primary"></i>
            <span class="mt-2 block font-semibold text-text">Connect directly</span>
            <span class="mt-1 block text-sm text-muted">
              We connect to your system and pull everything automatically. Best for most businesses.
            </span>
          </button>
          <button
            type="button"
            (click)="selectedMode.set('csv')"
            [class]="methodCardClass('csv')"
          >
            <i class="pi pi-file-import text-2xl text-primary"></i>
            <span class="mt-2 block font-semibold text-text">Upload CSV files</span>
            <span class="mt-1 block text-sm text-muted">
              Download our templates, fill them in, upload back. Best for technical users or custom formats.
            </span>
          </button>
        </div>

        <div class="mt-6 flex justify-between">
          <button
            (click)="step.set('source')"
            class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
          >
            Back
          </button>
          <button
            (click)="step.set('upload')"
            [disabled]="!selectedMode()"
            class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-40 min-h-[40px]"
          >
            Next
          </button>
        </div>
      }

      @case ('upload') {
        @if (selectedMode() === 'csv') {
          <app-csv-upload-step
            [sourceSystem]="selectedSource()!"
            (back)="step.set('method')"
            (jobCreated)="onJobCreated($event)"
          />
        } @else {
          <app-api-credentials-step
            [sourceSystem]="selectedSource()!"
            (back)="step.set('method')"
            (jobCreated)="onJobCreated($event)"
          />
        }
      }

      @case ('validate') {
        <app-validate-step
          [jobId]="activeJob()!.id"
          (back)="step.set('upload')"
          (proceed)="step.set('confirm')"
        />
      }

      @case ('confirm') {
        <app-confirm-step
          [jobId]="activeJob()!.id"
          (cancelled)="onCancelled()"
          (confirmed)="onConfirmed($event)"
          (failed)="onError($event)"
        />
      }

      @case ('summary') {
        <app-summary-step
          [job]="activeJob()!"
          (undone)="onUndone()"
          (failed)="onError($event)"
        />
      }
    }
  `,
})
export class ImportWizardPageComponent implements OnInit {
  private readonly importService = inject(ImportService);
  private readonly messageService = inject(MessageService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly location = inject(Location);

  readonly sourceOptions = SOURCE_OPTIONS;

  step = signal<WizardStep>('history');
  history = signal<MigrationJob[]>([]);
  selectedSource = signal<SourceSystem | null>(null);
  selectedMode = signal<ExtractionMode | null>(null);
  activeJob = signal<MigrationJob | null>(null);
  undoingJobIds = signal<ReadonlySet<string>>(new Set());

  supportsApi = computed(() => {
    const source = this.selectedSource();
    return !!source && this.sourceOptions.find((o) => o.system === source)!.supportsApi;
  });

  ngOnInit(): void {
    const jobId = this.route.snapshot.paramMap.get('jobId');
    if (!jobId) {
      this.loadHistory();
      return;
    }

    this.importService.getJob(jobId).subscribe({
      next: (job) => {
        this.activeJob.set(job);
        this.selectedSource.set(job.source_system);
        this.selectedMode.set(job.extraction_mode);
        const step = this.stepForStatus(job.status);
        this.step.set(step);
        if (step === 'history') {
          this.messageService.add({
            severity: 'info',
            summary: 'Import unavailable',
            detail: `This import is ${humanizeKey(job.status)} — showing import history instead.`,
          });
          this.loadHistory();
        }
      },
      error: (err) => {
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: err?.error?.detail || 'Could not load this import — showing import history instead.',
        });
        this.loadHistory();
        this.location.go('/settings/import');
        this.step.set('history');
      },
    });
  }

  private stepForStatus(status: MigrationJob['status']): WizardStep {
    switch (status) {
      case 'awaiting_confirmation':
        return 'confirm';
      case 'done':
        return 'summary';
      case 'pending':
      case 'extracting':
      case 'transforming':
        return 'validate';
      default:
        // importing/recomputing (mid-flight elsewhere) and the terminal
        // failed/cancelled/rolled_back statuses must never land on
        // 'validate' — that step unconditionally re-POSTs validateJob(),
        // which would re-run extraction on a job that's already finished
        // or in progress.
        return 'history';
    }
  }

  private loadHistory(): void {
    this.importService.listJobs().subscribe({
      next: (res) => this.history.set(res.items),
      error: () => {},
    });
  }

  startNewImport(): void {
    this.selectedSource.set(null);
    this.selectedMode.set(null);
    this.activeJob.set(null);
    this.location.go('/settings/import');
    this.step.set('source');
  }

  private selectionCardClass(selected: boolean, extraBase = ''): string {
    const base = `rounded-xl border-2 p-5 text-left transition-colors min-h-[44px]${extraBase}`;
    return selected
      ? `${base} border-primary bg-emerald-50`
      : `${base} border-gray-200 bg-white hover:border-gray-300`;
  }

  sourceCardClass(system: SourceSystem): string {
    return this.selectionCardClass(this.selectedSource() === system);
  }

  methodCardClass(mode: ExtractionMode): string {
    return this.selectionCardClass(
      this.selectedMode() === mode,
      ' disabled:cursor-not-allowed disabled:opacity-40',
    );
  }

  onJobCreated(job: MigrationJob): void {
    this.activeJob.set(job);
    // Location.go (not Router.navigate) — /settings/import and
    // /settings/import/:jobId are separate Route entries, so a router
    // navigation between them destroys and recreates this component. If
    // validateJob() (triggered by the 'validate' step below) resolves
    // before that recreation settles, ngOnInit's re-fetch can see the job
    // already at awaiting_confirmation and jump straight to 'confirm',
    // skipping the validate step's UI entirely.
    this.location.go(`/settings/import/${job.id}`);
    this.step.set('validate');
  }

  onConfirmed(job: MigrationJob): void {
    this.activeJob.set(job);
    this.step.set('summary');
    this.loadHistory();
  }

  onCancelled(): void {
    this.messageService.add({ severity: 'info', summary: 'Cancelled', detail: 'Import cancelled. No data was changed.' });
    // Location.go (not Router.navigate) — /settings/import and
    // /settings/import/:jobId are separate Route entries, so a router
    // navigation between them destroys and recreates this component,
    // wiping the just-queued toast before it can render.
    this.location.go('/settings/import');
    this.activeJob.set(null);
    this.step.set('history');
    this.loadHistory();
  }

  private notifyImportUndone(): void {
    this.messageService.add({ severity: 'success', summary: 'Import undone', detail: 'All imported records were removed.' });
  }

  onUndone(): void {
    this.notifyImportUndone();
    this.location.go('/settings/import');
    this.activeJob.set(null);
    this.step.set('history');
    this.loadHistory();
  }

  undoFromHistory(job: MigrationJob): void {
    if (this.undoingJobIds().has(job.id)) return;
    if (!window.confirm(UNDO_CONFIRM_MESSAGE)) return;
    this.undoingJobIds.update((ids) => new Set(ids).add(job.id));
    this.importService.rollbackJob(job.id).subscribe({
      next: () => {
        this.undoingJobIds.update((ids) => {
          const next = new Set(ids);
          next.delete(job.id);
          return next;
        });
        this.notifyImportUndone();
        this.loadHistory();
      },
      error: () => {
        this.undoingJobIds.update((ids) => {
          const next = new Set(ids);
          next.delete(job.id);
          return next;
        });
        this.messageService.add({ severity: 'error', summary: 'Error', detail: UNDO_FAILED_MESSAGE });
      },
    });
  }

  onError(message: string): void {
    this.messageService.add({ severity: 'error', summary: 'Error', detail: message });
  }

  totalRows(job: MigrationJob): number {
    return sumRowCounts(job.row_counts || {});
  }

  statusLabel(status: MigrationJob['status']): string {
    // Unlike other humanizeKey() call sites, this feeds app-status-badge
    // and toast text directly with no surrounding `capitalize` CSS class,
    // so it needs to capitalize each word itself.
    return humanizeKey(status).replace(/\b\w/g, (c) => c.toUpperCase());
  }

  statusBadgeVariant(status: MigrationJob['status']): 'success' | 'warning' | 'danger' | 'neutral' {
    if (status === 'done') return 'success';
    if (status === 'failed') return 'danger';
    if (status === 'rolled_back' || status === 'cancelled') return 'neutral';
    return 'warning';
  }
}
