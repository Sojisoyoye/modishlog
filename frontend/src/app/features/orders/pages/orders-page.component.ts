import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-orders-page',
  standalone: true,
  imports: [],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Orders</h2>
      <p class="text-muted">Order management coming soon.</p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OrdersPageComponent {}
