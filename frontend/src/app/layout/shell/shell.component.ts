import { Component, ChangeDetectionStrategy, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SidebarComponent } from '../sidebar/sidebar.component';
import { TopbarComponent } from '../topbar/topbar.component';
import { BottomNavComponent } from '../bottom-nav/bottom-nav.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, SidebarComponent, TopbarComponent, BottomNavComponent],
  template: `
    <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:rounded focus:bg-primary focus:px-4 focus:py-2 focus:text-white">Skip to content</a>
    <div class="flex h-screen bg-background">
      <app-sidebar
        [mobileOpen]="mobileOpen()"
        [collapsed]="sidebarCollapsed()"
        (closeMobile)="mobileOpen.set(false)"
      />
      <div class="flex flex-1 flex-col overflow-hidden">
        <app-topbar
          (toggleMenu)="onToggleMenu()"
          [sidebarCollapsed]="sidebarCollapsed()"
        />
        <main id="main-content" class="flex-1 overflow-y-auto p-4 pb-20 md:p-6 md:pb-6 lg:p-8">
          <router-outlet />
        </main>
      </div>
    </div>

    <app-bottom-nav (openMore)="mobileOpen.set(true)" />

    @if (mobileOpen()) {
      <div
        class="fixed inset-0 z-30 bg-gray-900/60 backdrop-blur-sm md:hidden"
        (click)="mobileOpen.set(false)"
      ></div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShellComponent {
  mobileOpen = signal(false);
  sidebarCollapsed = signal(false);

  onToggleMenu(): void {
    // On mobile: toggle the mobile overlay sidebar
    // On desktop: toggle the collapsed state
    if (window.innerWidth >= 768) {
      this.sidebarCollapsed.update((v) => !v);
    } else {
      this.mobileOpen.update((v) => !v);
    }
  }
}
