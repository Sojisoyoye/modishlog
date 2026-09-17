import { Component, ChangeDetectionStrategy, computed, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SidebarComponent } from '../sidebar/sidebar.component';
import { TopbarComponent } from '../topbar/topbar.component';
import { BottomNavComponent } from '../bottom-nav/bottom-nav.component';
import { OfflineService } from '../../core/services/offline.service';
import { AuthService } from '../../core/services/auth.service';
import { subscriptionBannerFor } from '../../core/utils/subscription.utils';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, SidebarComponent, TopbarComponent, BottomNavComponent],
  template: `
    <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:rounded focus:bg-primary focus:px-4 focus:py-2 focus:text-white">Skip to content</a>

    @if (offline.isOffline()) {
      <div role="alert" aria-live="assertive" class="fixed top-0 inset-x-0 z-50 flex items-center justify-center gap-2 bg-warning px-4 py-2 text-sm font-medium text-white shadow">
        <span>⚠</span>
        <span>Network disconnected — last data cached locally. Reconnecting…</span>
      </div>
    }

    <div class="flex h-screen bg-background" [class.pt-9]="offline.isOffline()">
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
        @if (subscriptionBanner(); as banner) {
          <div
            role="alert"
            class="flex flex-wrap items-center justify-center gap-2 px-4 py-2 text-center text-sm font-medium text-white"
            [class.bg-primary]="banner.kind === 'trial'"
            [class.bg-warning]="banner.kind === 'past_due'"
            [class.bg-danger]="banner.kind === 'read_only'"
            data-testid="subscription-banner"
          >
            <span>{{ banner.message }}</span>
            @if (banner.kind === 'read_only') {
              <a href="mailto:contact@modishlog.com" class="underline">Contact support</a>
            }
          </div>
        }
        <main id="main-content" class="flex-1 overflow-y-auto p-4 pb-20 md:p-6 md:pb-6 lg:p-8">
          <router-outlet />
        </main>
      </div>
    </div>

    <app-bottom-nav [mobileOpen]="mobileOpen()" (openMore)="mobileOpen.set(true)" />

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
  readonly offline = inject(OfflineService);
  private readonly authService = inject(AuthService);
  mobileOpen = signal(false);
  sidebarCollapsed = signal(false);

  readonly subscriptionBanner = computed(() =>
    subscriptionBannerFor(this.authService.currentUser()),
  );

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
