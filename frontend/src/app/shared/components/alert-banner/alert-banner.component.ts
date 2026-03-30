import { Component, ChangeDetectionStrategy, input, output, computed } from '@angular/core';

@Component({
  selector: 'app-alert-banner',
  standalone: true,
  imports: [],
  template: `
    <div class="flex items-center gap-3 rounded-lg border-l-4 bg-surface p-4 shadow-sm" [class]="bannerClass()">
      <i [class]="iconClass()"></i>
      <p class="flex-1 text-sm text-text">{{ message() }}</p>
      <button (click)="dismissed.emit()" class="text-muted hover:text-text">
        <i class="pi pi-times"></i>
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
      info: 'border-l-secondary',
      success: 'border-l-success',
      warning: 'border-l-warning',
      danger: 'border-l-danger',
    };
    return classes[this.severity()] ?? 'border-l-secondary';
  });

  iconClass = computed(() => {
    const icons: Record<string, string> = {
      info: 'pi pi-info-circle text-secondary',
      success: 'pi pi-check-circle text-success',
      warning: 'pi pi-exclamation-triangle text-warning',
      danger: 'pi pi-times-circle text-danger',
    };
    return icons[this.severity()] ?? 'pi pi-info-circle text-secondary';
  });
}
