import { Component, ChangeDetectionStrategy, input, computed } from '@angular/core';

@Component({
  selector: 'app-metric-card',
  standalone: true,
  imports: [],
  template: `
    <div
      class="rounded-xl border bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
      [class]="borderClass()"
    >
      <p class="text-sm font-medium text-muted">{{ title() }}</p>
      <p class="mt-2 text-2xl font-bold text-text">{{ value() }}</p>
      <div class="mt-2 flex items-center gap-1 text-xs">
        @if (trend() === 'up') {
          <span class="flex items-center gap-0.5 font-medium text-success">
            <i class="pi pi-arrow-up text-[10px]"></i> {{ trendLabel() }}
          </span>
        } @else if (trend() === 'down') {
          <span class="flex items-center gap-0.5 font-medium text-danger">
            <i class="pi pi-arrow-down text-[10px]"></i> {{ trendLabel() }}
          </span>
        } @else {
          <span class="text-muted">{{ trendLabel() }}</span>
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
      success: 'border-l-4 border-l-success border-t-gray-200 border-r-gray-200 border-b-gray-200',
      warning: 'border-l-4 border-l-warning border-t-gray-200 border-r-gray-200 border-b-gray-200',
      danger: 'border-l-4 border-l-danger border-t-gray-200 border-r-gray-200 border-b-gray-200',
    };
    return classes[this.severity()] ?? 'border-gray-200';
  });
}
