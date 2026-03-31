import { Component, ChangeDetectionStrategy, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SidebarComponent } from '../sidebar/sidebar.component';
import { TopbarComponent } from '../topbar/topbar.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, SidebarComponent, TopbarComponent],
  template: `
    <div class="flex h-screen bg-background">
      <app-sidebar [mobileOpen]="mobileOpen()" (closeMobile)="mobileOpen.set(false)" />
      <div class="flex flex-1 flex-col overflow-hidden">
        <app-topbar (toggleMenu)="mobileOpen.update((v) => !v)" />
        <main class="flex-1 overflow-y-auto p-4 md:p-6">
          <router-outlet />
        </main>
      </div>
    </div>

    @if (mobileOpen()) {
      <div
        class="fixed inset-0 z-30 bg-black/50 lg:hidden"
        (click)="mobileOpen.set(false)"
      ></div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShellComponent {
  mobileOpen = signal(false);
}
