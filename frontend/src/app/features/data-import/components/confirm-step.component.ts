import { Component, ChangeDetectionStrategy, inject, input, output, signal, OnInit, computed } from '@angular/core';
import { ImportService } from '../services/import.service';
import { ConfirmationSnapshot, MigrationJob, humanizeKey } from '../models/import.models';

@Component({
  selector: 'app-confirm-step',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (loading()) {
      <div class="flex items-center gap-2 text-muted">
        <i class="pi pi-spinner pi-spin"></i> Loading import summary...
      </div>
    } @else if (staleMessage()) {
      <div class="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        <i class="pi pi-info-circle mr-1"></i> {{ staleMessage() }}
      </div>
    } @else if (snapshot(); as s) {
      <h3 class="mb-1 text-lg font-semibold text-text">Review your import</h3>
      <p class="mb-5 text-sm text-muted">
        Source: <span class="capitalize font-medium text-text">{{ s.source_system }}</span>
        <span class="ml-2 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium uppercase text-gray-600">
          {{ s.extraction_mode }} connection
        </span>
      </p>

      <div class="rounded-xl border border-gray-100 bg-white shadow-sm">
        <table class="min-w-full divide-y divide-gray-200 text-sm">
          <caption class="sr-only">What will be imported</caption>
          <thead>
            <tr class="bg-gray-50">
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Entity</th>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Records</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Sample</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            @for (entity of nonEmptyEntities(); track entity.name) {
              <tr>
                <td class="px-4 py-3 capitalize text-gray-700">{{ humanizeKey(entity.name) }}</td>
                <td class="px-4 py-3 text-right text-gray-700">{{ entity.count }} record{{ entity.count === 1 ? '' : 's' }}</td>
                <td class="max-w-[280px] truncate px-4 py-3 text-gray-500">{{ sampleText(entity) }}</td>
              </tr>
            }
          </tbody>
          <tfoot>
            <tr class="bg-gray-50 font-medium text-text">
              <td class="px-4 py-3">Total</td>
              <td class="px-4 py-3 text-right">{{ s.total_rows }} records</td>
              <td class="px-4 py-3"></td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div class="mt-4 rounded-xl border border-gray-100 bg-white p-4">
        <p class="mb-2 text-sm font-semibold text-text">Notices</p>
        @if (s.warnings.length === 0) {
          <p class="text-sm text-muted">No issues detected.</p>
        } @else {
          <ul class="space-y-1 text-sm text-amber-700">
            @for (w of s.warnings.slice(0, 20); track $index) {
              <li>• {{ w.message }}</li>
            }
          </ul>
        }
      </div>

      @if (emptyEntities().length > 0) {
        <p class="mt-3 text-xs text-muted">
          Not included: {{ emptyEntities().join(', ') }} — no records found in your data.
        </p>
      }

      <p class="mt-5 text-sm text-muted">
        This action will add data to your ModishLog account. You can undo this import from
        Settings › Data Imports at any time.
      </p>

      <div class="mt-6 flex justify-between">
        <button
          (click)="decline()"
          [disabled]="submitting()"
          class="rounded-lg border border-gray-300 px-6 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40 min-h-[40px]"
        >
          ✗ Cancel — don't import
        </button>
        <button
          (click)="approve()"
          [disabled]="submitting()"
          class="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-40 min-h-[40px]"
        >
          @if (submitting()) {
            <i class="pi pi-spinner pi-spin mr-1"></i> Importing...
          } @else {
            ✓ Yes, import this data
          }
        </button>
      </div>
    }
  `,
})
export class ConfirmStepComponent implements OnInit {
  private readonly importService = inject(ImportService);

  jobId = input.required<string>();
  cancelled = output<void>();
  confirmed = output<MigrationJob>();
  failed = output<string>();

  loading = signal(true);
  submitting = signal(false);
  snapshot = signal<ConfirmationSnapshot | null>(null);
  staleMessage = signal<string | null>(null);

  humanizeKey = humanizeKey;

  nonEmptyEntities = computed(() => (this.snapshot()?.entities ?? []).filter((e) => e.count > 0));
  emptyEntities = computed(() =>
    (this.snapshot()?.entities ?? [])
      .filter((e) => e.count === 0)
      .map((e) => humanizeKey(e.name)),
  );

  ngOnInit(): void {
    this.importService.getConfirmationSnapshot(this.jobId()).subscribe({
      next: (snapshot) => {
        this.loading.set(false);
        this.snapshot.set(snapshot);
      },
      error: (err) => {
        this.loading.set(false);
        if (err?.status === 409) {
          this.staleMessage.set(
            'This import has already been processed. View its status in Data Imports history.',
          );
        } else {
          this.staleMessage.set(err?.error?.detail || 'Could not load import summary.');
        }
      },
    });
  }

  sampleText(entity: ConfirmationSnapshot['entities'][number]): string {
    if (!entity.sample_rows?.length) return '';
    return entity.sample_rows.map((row) => this.sampleRowLabel(row)).join(', ');
  }

  private sampleRowLabel(row: Record<string, string>): string {
    const name = row['name']?.trim();
    if (name) return name;
    const sku = row['sku']?.trim();
    if (sku) return sku;
    // Entities like sales have no name/sku — fall back to the first
    // non-empty non-id field so the preview shows something meaningful
    // instead of a raw internal id.
    const firstNonId = Object.entries(row).find(([key, value]) => !key.endsWith('_id') && value?.trim());
    if (firstNonId) return firstNonId[1].trim();
    const firstAny = Object.values(row).find((value) => value?.trim());
    return firstAny?.trim() || '(no data)';
  }

  approve(): void {
    this.submitting.set(true);
    this.importService.confirmJob(this.jobId(), true).subscribe({
      next: (job) => {
        this.submitting.set(false);
        this.confirmed.emit(job);
      },
      error: (err) => {
        this.submitting.set(false);
        this.failed.emit(err?.error?.detail || 'Failed to import data.');
      },
    });
  }

  decline(): void {
    this.submitting.set(true);
    this.importService.confirmJob(this.jobId(), false).subscribe({
      next: () => {
        this.submitting.set(false);
        this.cancelled.emit();
      },
      error: (err) => {
        this.submitting.set(false);
        this.failed.emit(err?.error?.detail || 'Failed to cancel import.');
      },
    });
  }
}
