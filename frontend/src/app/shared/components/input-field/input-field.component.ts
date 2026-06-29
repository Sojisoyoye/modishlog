import {
  Component,
  ChangeDetectionStrategy,
  input,
  output,
} from '@angular/core';

@Component({
  selector: 'app-input-field',
  standalone: true,
  imports: [],
  template: `
    <div class="flex flex-col">
      @if (label()) {
        <label
          [for]="id()"
          class="text-xs font-medium text-gray-600 mb-1.5 block"
        >
          {{ label() }}
          @if (required()) {
            <span class="text-red-500 ml-0.5">*</span>
          }
        </label>
      }
      <input
        [id]="id()"
        [type]="type()"
        [placeholder]="placeholder()"
        [value]="value()"
        [disabled]="disabled()"
        [required]="required()"
        (input)="valueChange.emit($any($event.target).value)"
        class="w-full rounded-lg border px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 transition-colors
          focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500
          disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500 min-h-[44px]"
        [class.border-red-500]="!!errorMessage()"
        [class.border-gray-300]="!errorMessage()"
      />
      @if (errorMessage()) {
        <p class="text-xs text-red-600 mt-1">{{ errorMessage() }}</p>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InputFieldComponent {
  label = input<string>('');
  id = input<string>('');
  type = input<'text' | 'number' | 'email' | 'password'>('text');
  placeholder = input<string>('');
  value = input<string>('');
  errorMessage = input<string>('');
  required = input<boolean>(false);
  disabled = input<boolean>(false);

  valueChange = output<string>();
}
