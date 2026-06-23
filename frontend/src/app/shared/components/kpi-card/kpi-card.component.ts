import { Component, ChangeDetectionStrategy, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Tooltip } from 'primeng/tooltip';

export interface KpiSubLine {
  label: string;
  value: string;
}

@Component({
  selector: 'app-kpi-card',
  standalone: true,
  imports: [CommonModule, Tooltip],
  template: `
    <div
      class="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
      data-testid="kpi-card"
    >
      <!-- Circle icon -->
      <div
        class="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-full"
        [style.background-color]="iconBgColor()"
      >
        <i class="text-xl text-white" [class]="iconClass()"></i>
      </div>

      <!-- Label + value -->
      <div class="min-w-0 flex-1">
        <p class="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted">
          {{ label() }}
          @if (tooltipText()) {
            <i
              class="pi pi-info-circle cursor-help text-[10px] text-muted"
              [pTooltip]="tooltipText()!"
              tooltipPosition="top"
            ></i>
          }
        </p>

        @if (loading()) {
          <div class="mt-1 h-7 w-28 rounded skeleton"></div>
        } @else {
          <p class="mt-0.5 text-2xl font-bold text-text">
            ₦ {{ value() }}
          </p>
        }

        @if (subLines() && subLines()!.length > 0) {
          <div class="mt-1 space-y-0.5">
            @for (line of subLines()!; track line.label) {
              @if (loading()) {
                <div class="h-3 w-36 rounded skeleton"></div>
              } @else {
                <p class="text-xs text-muted">
                  {{ line.label }}: <span class="font-medium text-text">₦ {{ line.value }}</span>
                </p>
              }
            }
          </div>
        }
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KpiCardComponent {
  label = input.required<string>();
  value = input<string>('0.00');
  iconClass = input.required<string>();
  iconBgColor = input.required<string>();
  subLines = input<KpiSubLine[] | undefined>(undefined);
  loading = input<boolean>(false);
  tooltipText = input<string | undefined>(undefined);
}
