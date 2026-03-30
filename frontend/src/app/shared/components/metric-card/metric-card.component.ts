import { Component, ChangeDetectionStrategy, input, computed } from '@angular/core';

@Component({
  selector: 'app-metric-card',
  standalone: true,
  imports: [],
  template: `
    <div class="rounded-lg border bg-surface p-4 shadow-sm" [class]="borderClass()">
      <p class="text-sm font-medium text-muted">{{ title() }}</p>
      <p class="mt-1 text-2xl font-bold text-text">{{ value() }}</p>
      <div class="mt-1 flex items-center gap-1 text-xs">
        @if (trend() === 'up') {
          <span class="text-success">&#9650; {{ trendLabel() }}</span>
        } @else if (trend() === 'down') {
          <span class="text-danger">&#9660; {{ trendLabel() }}</span>
        } @else {
          <span class="text-muted">&#8212; {{ trendLabel() }}</span>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MetricCardComponent {
  title = input.required<string>();
  value = input.required<string>();
  trend = input<'up' | 'down' | 'flat'>('flat');
  trendLabel = input<string>('');
  severity = input<'default' | 'success' | 'warning' | 'danger'>('default');

  borderClass = computed(() => {
    const classes: Record<string, string> = {
      default: 'border-gray-200',
      success: 'border-success',
      warning: 'border-warning',
      danger: 'border-danger',
    };
    return classes[this.severity()] ?? 'border-gray-200';
  });
}
