import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-sales-page',
  standalone: true,
  imports: [],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Sales</h2>
      <p class="text-muted">Daily sales entry coming soon.</p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SalesPageComponent {}
