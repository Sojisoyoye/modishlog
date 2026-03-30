import { Component, ChangeDetectionStrategy } from '@angular/core';

@Component({
  selector: 'app-dashboard-page',
  standalone: true,
  imports: [],
  template: `
    <div>
      <h2 class="mb-6 text-xl font-bold text-text">Dashboard</h2>
      <p class="text-muted">Dashboard overview coming soon.</p>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardPageComponent {}
