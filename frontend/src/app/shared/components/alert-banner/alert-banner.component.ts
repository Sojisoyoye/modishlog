import { Component, ChangeDetectionStrategy, input, output, computed } from '@angular/core';

@Component({
  selector: 'app-alert-banner',
  standalone: true,
  imports: [],
  template: `
    <div
      class="flex items-center gap-3 rounded-lg border-l-4 p-4 shadow-sm"
      [class]="bannerClass()"
    >
      <i [class]="iconClass()"></i>
      <p class="flex-1 text-sm text-text">{{ message() }}</p>
      <button
        (click)="dismissed.emit()"
        class="rounded p-1 text-muted transition-colors hover:bg-black/5 hover:text-text"
      >
        <i class="pi pi-times text-xs"></i>
      </button>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AlertBannerComponent {
  message = input.required<string>();
  severity = input<'info' | 'success' | 'warning' | 'danger'>('info');
  dismissed = output<void>();

  bannerClass = computed(() => {
    const classes: Record<string, string> = {
      info: 'border-l-secondary bg-blue-50',
      success: 'border-l-success bg-green-50',
      warning: 'border-l-warning bg-amber-50',
      danger: 'border-l-danger bg-red-50',
    };
    return classes[this.severity()] ?? 'border-l-secondary bg-blue-50';
  });

  iconClass = computed(() => {
    const icons: Record<string, string> = {
      info: 'pi pi-info-circle text-lg text-secondary',
      success: 'pi pi-check-circle text-lg text-success',
      warning: 'pi pi-exclamation-triangle text-lg text-warning',
      danger: 'pi pi-times-circle text-lg text-danger',
    };
    return icons[this.severity()] ?? 'pi pi-info-circle text-lg text-secondary';
  });
}
