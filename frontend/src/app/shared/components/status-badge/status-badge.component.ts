import { Component, ChangeDetectionStrategy, input, computed } from '@angular/core';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  imports: [],
  template: `
    <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium" [class]="badgeClass()">
      {{ label() }}
    </span>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusBadgeComponent {
  label = input.required<string>();
  status = input<'success' | 'warning' | 'danger' | 'info' | 'neutral'>('neutral');

  badgeClass = computed(() => {
    const classes: Record<string, string> = {
      success: 'bg-green-100 text-success',
      warning: 'bg-amber-100 text-warning',
      danger: 'bg-red-100 text-danger',
      info: 'bg-blue-100 text-secondary',
      neutral: 'bg-gray-100 text-muted',
    };
    return classes[this.status()] ?? 'bg-gray-100 text-muted';
  });
}
