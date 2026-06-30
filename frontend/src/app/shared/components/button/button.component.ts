import {
  Component,
  ChangeDetectionStrategy,
  input,
  output,
  computed,
} from '@angular/core';

@Component({
  selector: 'app-button',
  standalone: true,
  imports: [],
  host: {
    '(click)': 'interceptHostClick($event)',
  },
  template: `
    <button
      [type]="type()"
      [disabled]="disabled() || loading()"
      [class]="buttonClass()"
      (click)="handleClick()"
    >
      @if (loading()) {
        <i class="pi pi-spinner pi-spin mr-1.5"></i>
      }
      <ng-content />
    </button>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ButtonComponent {
  variant = input<'primary' | 'secondary' | 'danger' | 'ghost'>('primary');
  size = input<'sm' | 'md' | 'lg'>('md');
  loading = input<boolean>(false);
  disabled = input<boolean>(false);
  type = input<'button' | 'submit'>('button');

  clicked = output<void>();

  /** Stops host-element click propagation when the button is disabled or loading. */
  interceptHostClick(event: MouseEvent): void {
    if (this.disabled() || this.loading()) {
      event.stopImmediatePropagation();
      event.preventDefault();
    }
  }

  handleClick(): void {
    this.clicked.emit();
  }

  buttonClass = computed(() => {
    const base =
      'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 min-h-[44px] disabled:opacity-50 disabled:cursor-not-allowed';

    const variantClasses: Record<string, string> = {
      primary:
        'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm focus:ring-emerald-500',
      secondary:
        'border border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-300',
      danger:
        'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
      ghost: 'text-gray-600 hover:bg-gray-100 focus:ring-gray-300',
    };

    const sizeClasses: Record<string, string> = {
      sm: 'px-3 py-1.5 text-xs',
      md: 'px-4 py-2.5 text-sm',
      lg: 'px-6 py-3 text-base',
    };

    const variantClass = variantClasses[this.variant()] ?? variantClasses['primary'];
    const sizeClass = sizeClasses[this.size()] ?? sizeClasses['md'];

    return `${base} ${variantClass} ${sizeClass}`;
  });
}
