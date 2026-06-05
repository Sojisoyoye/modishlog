import { Component, ChangeDetectionStrategy, input, output } from '@angular/core';
import { Dialog } from 'primeng/dialog';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [Dialog],
  template: `
    <p-dialog
      [header]="header()"
      [visible]="visible()"
      [modal]="true"
      [style]="{ width: '420px' }"
      [closable]="false"
      [closeOnEscape]="false"
    >
      <p class="py-2 text-sm text-text">{{ message() }}</p>
      <div class="flex justify-end gap-2 pt-4">
        <button
          (click)="cancelled.emit()"
          class="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-text transition-colors hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          (click)="confirmed.emit()"
          class="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600"
        >
          {{ confirmLabel() }}
        </button>
      </div>
    </p-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmDialogComponent {
  header = input.required<string>();
  message = input.required<string>();
  confirmLabel = input<string>('Delete');
  visible = input.required<boolean>();

  confirmed = output<void>();
  cancelled = output<void>();
}
