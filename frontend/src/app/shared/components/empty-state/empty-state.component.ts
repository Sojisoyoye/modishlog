import { Component, ChangeDetectionStrategy, input } from '@angular/core';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [],
  template: `
    <div class="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div class="flex h-20 w-20 items-center justify-center rounded-full bg-gray-100 mb-4">
        <i class="text-3xl text-gray-400" [class]="'pi ' + icon()"></i>
      </div>
      @if (message()) {
        <p class="text-base font-medium text-gray-700 mb-1">{{ message() }}</p>
      }
      @if (subMessage()) {
        <p class="text-sm text-gray-500 mb-4">{{ subMessage() }}</p>
      }
      <ng-content />
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmptyStateComponent {
  icon = input<string>('pi-inbox');
  message = input<string>('No data');
  subMessage = input<string>('');
}
