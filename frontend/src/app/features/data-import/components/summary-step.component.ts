import { Component, ChangeDetectionStrategy, inject, input, output, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ImportService } from '../services/import.service';
import { MigrationJob, humanizeKey } from '../models/import.models';

@Component({
  selector: 'app-summary-step',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="rounded-xl border border-emerald-100 bg-emerald-50 p-6">
      <h3 class="flex items-center gap-2 text-lg font-semibold text-emerald-800">
        <i class="pi pi-check-circle text-xl"></i> Import complete
      </h3>

      <ul class="mt-4 space-y-1 text-sm text-gray-700">
        @for (entry of rowEntries(); track entry[0]) {
          <li>{{ entry[1] }} {{ humanizeKey(entry[0]) }} imported</li>
        }
      </ul>

      @if (job().validation_warnings.length > 0) {
        <div class="mt-4 border-t border-emerald-200 pt-4">
          <ul class="space-y-1 text-sm text-amber-700">
            @for (w of job().validation_warnings.slice(0, 20); track $index) {
              <li>• {{ w.message }}</li>
            }
          </ul>
        </div>
      }
    </div>

    <div class="mt-6 flex flex-wrap gap-3">
      <button
        (click)="router.navigate(['/dashboard'])"
        class="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-white hover:bg-primary/90 min-h-[40px]"
      >
        Go to Dashboard
      </button>
      <button
        (click)="router.navigate(['/products'])"
        class="rounded-lg border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 min-h-[40px]"
      >
        View Products
      </button>
      <button
        (click)="undo()"
        [disabled]="undoing()"
        class="ml-auto rounded-lg border border-red-200 px-5 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-40 min-h-[40px]"
      >
        @if (undoing()) {
          <i class="pi pi-spinner pi-spin mr-1"></i> Undoing...
        } @else {
          Undo this import
        }
      </button>
    </div>
  `,
})
export class SummaryStepComponent {
  private readonly importService = inject(ImportService);
  protected readonly router = inject(Router);

  job = input.required<MigrationJob>();
  undone = output<void>();
  failed = output<string>();

  undoing = signal(false);

  humanizeKey = humanizeKey;

  rowEntries(): [string, number][] {
    return Object.entries(this.job().row_counts).filter(([, count]) => count > 0);
  }

  undo(): void {
    if (!window.confirm('Undo this import? All records it created will be removed.')) return;
    this.undoing.set(true);
    this.importService.rollbackJob(this.job().id).subscribe({
      next: () => {
        this.undoing.set(false);
        this.undone.emit();
      },
      error: (err) => {
        this.undoing.set(false);
        this.failed.emit(err?.error?.detail || 'Failed to undo import');
      },
    });
  }
}
