import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-pricing-page',
  standalone: true,
  imports: [],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Pricing</h2>
      <p class="text-muted">Pricing and margin optimization coming soon.</p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PricingPageComponent {}
