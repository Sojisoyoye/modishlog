import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-inventory-page',
  standalone: true,
  imports: [],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Inventory</h2>
      <p class="text-muted">Inventory management coming soon.</p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InventoryPageComponent {}
