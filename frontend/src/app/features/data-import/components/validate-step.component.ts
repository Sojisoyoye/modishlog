import { Component, ChangeDetectionStrategy, inject, input, output, signal, OnInit, computed } from '@angular/core';
import { ImportService } from '../services/import.service';
import { MigrationJob, ValidationIssue } from '../models/import.models';

@Component({
  selector: 'app-validate-step',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading()) {
      <h3 class="mb-1 text-lg font-semibold text-text">Validating...</h3>
      <p class="mb-5 text-sm text-muted">Checking your data for issues before import.</p>
      <div class="flex items-center gap-2 text-muted">
        <i class="pi pi-spinner pi-spin"></i> This usually only takes a moment.
      </div>
    } @else if (job(); as j) {
      <h3 class="mb-1 text-lg font-semibold text-text">Validation results</h3>
      <p class="mb-5 text-sm text-muted">
        {{ j.validation_errors.length }} error{{ j.validation_errors.length === 1 ? '' : 's' }},
        {{ j.validation_warnings.length }} warning{{ j.validation_warnings.length === 1 ? '' : 's' }}
        across {{ totalRecords() }} record{{ totalRecords() === 1 ? '' : 's' }}.
      </p>

      <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
        <table class="min-w-full divide-y divide-gray-200 text-sm">
          <caption class="sr-only">Validation summary by entity</caption>
          <thead>
            <tr class="bg-gray-50">
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Entity</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Records</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Errors</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Warnings</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            @for (entry of entityRows(); track entry.entity) {
              <tr>
                <td class="px-4 py-3 capitalize text-gray-700">{{ entry.entity.replace('_', ' ') }}</td>
                <td class="px-4 py-3 text-right text-gray-700">{{ entry.count }} record{{ entry.count === 1 ? '' : 's' }}</td>
                <td class="px-4 py-3 text-right" [class.text-red-600]="entry.errors > 0" [class.font-medium]="entry.errors > 0">
                  {{ entry.errors }} error{{ entry.errors === 1 ? '' : 's' }}
                </td>
                <td class="px-4 py-3 text-right" [class.text-amber-600]="entry.warnings > 0">
                  {{ entry.warnings }} warning{{ entry.warnings === 1 ? '' : 's' }}
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      @if (j.validation_errors.length > 0) {
        <div class="mt-4 rounded-xl border border-red-200 bg-red-50 p-4">
          <p class="mb-2 text-sm font-semibold text-red-800">Errors — must be fixed before import</p>
          <ul class="max-h-64 space-y-1 overflow-y-auto text-sm text-red-700">
            @for (issue of j.validation_errors.slice(0, 50); track $index) {
              <li>{{ formatIssue(issue) }}</li>
            }
          </ul>
          @if (j.validation_errors.length > 50) {
            <p class="mt-2 text-xs text-red-600">{{ j.validation_errors.length - 50 }} more errors not shown.</p>
          }
        </div>
      }

      @if (j.validation_warnings.length > 0) {
        <div class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p class="mb-2 text-sm font-semibold text-amber-800">Warnings — non-blocking</p>
          <ul class="max-h-48 space-y-1 overflow-y-auto text-sm text-amber-700">
            @for (issue of j.validation_warnings.slice(0, 50); track $index) {
              <li>{{ formatIssue(issue) }}</li>
            }
          </ul>
        </div>
      }

      <div class="mt-6 flex justify-between">
        <button (click)="back.emit()" class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]">
          @if (j.validation_errors.length > 0) {
            Fix & Re-upload
          } @else {
            Back
          }
        </button>
        @if (j.validation_errors.length === 0) {
          <button (click)="proceed.emit()" class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 min-h-[40px]">
            @if (j.validation_warnings.length > 0) {
              Proceed with warnings
            } @else {
              Looks good — proceed to import
            }
          </button>
        }
      </div>
    } @else if (error()) {
      <div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        <i class="pi pi-exclamation-circle mr-1"></i> {{ error() }}
      </div>
      <div class="mt-6">
        <button (click)="back.emit()" class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]">
          Back
        </button>
      </div>
    }
  `,
})
export class ValidateStepComponent implements OnInit {
  private readonly importService = inject(ImportService);

  jobId = input.required<string>();
  back = output<void>();
  proceed = output<void>();

  loading = signal(true);
  job = signal<MigrationJob | null>(null);
  error = signal<string | null>(null);

  entityRows = computed(() => {
    const j = this.job();
    if (!j) return [];
    return Object.entries(j.row_counts)
      .map(([entity, count]) => ({
        entity,
        count,
        errors: j.validation_errors.filter((i) => i.entity === entity).length,
        warnings: j.validation_warnings.filter((i) => i.entity === entity).length,
      }))
      // Hide entities the user never uploaded — a wall of "0 records / 0
      // errors / 0 warnings" rows for every optional entity is just noise.
      // Still show a 0-record entity if it has errors (e.g. every row in
      // that file failed validation).
      .filter((row) => row.count > 0 || row.errors > 0 || row.warnings > 0);
  });

  totalRecords = computed(() => {
    const j = this.job();
    if (!j) return 0;
    return Object.values(j.row_counts).reduce((sum, n) => sum + n, 0);
  });

  ngOnInit(): void {
    this.importService.validateJob(this.jobId()).subscribe({
      next: (job) => {
        this.loading.set(false);
        this.job.set(job);
      },
      error: (err) => {
        this.loading.set(false);
        this.error.set(err?.error?.detail || 'Validation failed unexpectedly.');
      },
    });
  }

  formatIssue(issue: ValidationIssue): string {
    const field = issue.field ? ` | field: ${issue.field}` : '';
    return `Row ${issue.row}${field} | ${issue.message}`;
  }
}
