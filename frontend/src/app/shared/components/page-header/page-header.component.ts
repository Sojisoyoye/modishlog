import { Component, ChangeDetectionStrategy, input } from '@angular/core';

@Component({
  selector: 'app-page-header',
  standalone: true,
  imports: [],
  template: `
    <div class="mb-6 flex items-start justify-between gap-4">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">{{ title() }}</h2>
        @if (subtitle()) {
          <p class="mt-1 text-sm text-gray-500">{{ subtitle() }}</p>
        }
      </div>
      <div class="flex shrink-0 items-center gap-3">
        <ng-content select="[actions]" />
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PageHeaderComponent {
  title = input<string>('');
  subtitle = input<string>('');
}
