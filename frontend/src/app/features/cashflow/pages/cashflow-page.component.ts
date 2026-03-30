import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-cashflow-page',
  standalone: true,
  imports: [],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Cashflow</h2>
      <p class="text-muted">Cashflow projection coming soon.</p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CashflowPageComponent {}
