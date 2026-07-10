import { Component, ChangeDetectionStrategy, inject, input, output, signal } from '@angular/core';
import { ImportService } from '../services/import.service';
import { MigrationJob, SourceSystem, IMPORTABLE_ENTITIES, ImportEntity, ENTITY_LABELS, REQUIRED_ENTITIES } from '../models/import.models';

const SOURCE_INSTRUCTIONS: Record<SourceSystem, string> = {
  ultimatepos:
    'In UltimatePOS, go to each module (Products, Contacts, Sell) and use "Export" to download a CSV, then re-map the columns using our templates below.',
  quickbooks:
    "In QuickBooks, use Reports → Export to CSV for Items, Customers, Vendors and Invoices, then re-map the columns using our templates below.",
  shopify:
    "In Shopify Admin, use the Shopify products and orders CSV export (Products → Export, Orders → Export), then re-map the columns using our templates below.",
  generic: 'Fill in our templates directly — no re-mapping needed.',
};

@Component({
  selector: 'app-csv-upload-step',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (phase() === 'templates') {
      <h3 class="mb-1 text-lg font-semibold text-text">Download templates</h3>
      <p class="mb-4 text-sm text-muted">{{ instructions() }}</p>

      <a
        [href]="allTemplatesUrl"
        download
        class="mb-5 inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
      >
        <i class="pi pi-download text-sm"></i> Download all templates (ZIP)
      </a>

      <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
        <table class="min-w-full divide-y divide-gray-200 text-sm">
          <caption class="sr-only">Import template files</caption>
          <thead>
            <tr class="bg-gray-50">
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Entity</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Required?</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Download</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            @for (entity of entities; track entity) {
              <tr>
                <td class="px-4 py-3 text-gray-700">{{ labelFor(entity) }}</td>
                <td class="px-4 py-3">
                  @if (isRequired(entity)) {
                    <span class="rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700">Required</span>
                  } @else {
                    <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">Optional</span>
                  }
                </td>
                <td class="px-4 py-3 text-right">
                  <a [href]="templateUrl(entity)" download class="text-primary hover:underline">↓ CSV</a>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      <div class="mt-6 flex justify-between">
        <button (click)="back.emit()" class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]">
          Back
        </button>
        <button (click)="phase.set('upload')" class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 min-h-[40px]">
          Next
        </button>
      </div>
    } @else {
      <h3 class="mb-1 text-lg font-semibold text-text">Upload your files</h3>
      <p class="mb-5 text-sm text-muted">Upload the CSVs you filled in. Products is required — everything else is optional.</p>

      <div class="space-y-3">
        @for (entity of entities; track entity) {
          <div
            class="flex items-center justify-between rounded-lg border p-4"
            [class]="fileFor(entity) ? 'border-emerald-200 bg-emerald-50' : isRequired(entity) ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'"
          >
            <div class="flex items-center gap-3">
              @if (fileFor(entity)) {
                <i class="pi pi-check-circle text-emerald-600"></i>
              } @else {
                <i class="pi pi-circle text-gray-300"></i>
              }
              <div>
                <p class="text-sm font-medium text-text">{{ labelFor(entity) }}</p>
                @if (fileFor(entity)) {
                  <p class="text-xs text-muted">{{ fileFor(entity)!.name }}</p>
                } @else if (isRequired(entity)) {
                  <p class="text-xs text-red-600">Required</p>
                } @else {
                  <p class="text-xs text-muted">Optional</p>
                }
              </div>
            </div>
            <label class="cursor-pointer rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 min-h-[40px] flex items-center">
              Choose file
              <input
                type="file"
                accept=".csv"
                [id]="'file-' + entity"
                class="sr-only"
                (change)="onFileChange(entity, $event)"
              />
            </label>
          </div>
        }
      </div>

      @if (errorMessage()) {
        <div class="mt-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <i class="pi pi-exclamation-circle"></i>
          {{ errorMessage() }}
        </div>
      }

      <div class="mt-6 flex justify-between">
        <button (click)="phase.set('templates')" class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]">
          Back
        </button>
        <button
          (click)="submit()"
          [disabled]="!hasRequiredFiles() || submitting()"
          class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-40 min-h-[40px]"
        >
          @if (submitting()) {
            <i class="pi pi-spinner pi-spin mr-1"></i> Uploading...
          } @else {
            Next
          }
        </button>
      </div>
    }
  `,
})
export class CsvUploadStepComponent {
  private readonly importService = inject(ImportService);

  sourceSystem = input.required<SourceSystem>();
  back = output<void>();
  jobCreated = output<MigrationJob>();
  failed = output<string>();

  readonly entities = IMPORTABLE_ENTITIES;
  readonly allTemplatesUrl = this.importService.getAllTemplatesUrl();

  phase = signal<'templates' | 'upload'>('templates');
  files = signal<Partial<Record<ImportEntity, File>>>({});
  submitting = signal(false);
  errorMessage = signal<string | null>(null);

  instructions(): string {
    return SOURCE_INSTRUCTIONS[this.sourceSystem()];
  }

  labelFor(entity: ImportEntity): string {
    return ENTITY_LABELS[entity];
  }

  isRequired(entity: ImportEntity): boolean {
    return REQUIRED_ENTITIES.has(entity);
  }

  templateUrl(entity: ImportEntity): string {
    return this.importService.getEntityTemplateUrl(entity);
  }

  fileFor(entity: ImportEntity): File | null {
    return this.files()[entity] ?? null;
  }

  onFileChange(entity: ImportEntity, event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    this.files.update((f) => ({ ...f, [entity]: file ?? undefined }));
  }

  hasRequiredFiles(): boolean {
    return [...REQUIRED_ENTITIES].every((entity) => !!this.files()[entity]);
  }

  submit(): void {
    this.submitting.set(true);
    this.errorMessage.set(null);
    this.importService.createCsvJob(this.sourceSystem(), this.files()).subscribe({
      next: (job) => {
        this.submitting.set(false);
        this.jobCreated.emit(job);
      },
      error: (err) => {
        this.submitting.set(false);
        const message = err?.error?.detail || 'Failed to upload files';
        this.errorMessage.set(message);
        this.failed.emit(message);
      },
    });
  }
}
