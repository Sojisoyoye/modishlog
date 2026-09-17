import { Component, ChangeDetectionStrategy, computed, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SidebarComponent } from '../sidebar/sidebar.component';
import { TopbarComponent } from '../topbar/topbar.component';
import { BottomNavComponent } from '../bottom-nav/bottom-nav.component';
import { OfflineService } from '../../core/services/offline.service';
import { AuthService, UserProfile } from '../../core/services/auth.service';

export interface SubscriptionBanner {
  kind: 'trial' | 'past_due' | 'read_only';
  message: string;
}

/**
 * Pure function (task #240) so the banner's status->message mapping is
 * unit-testable without rendering the full shell (sidebar/topbar/bottom-nav
 * all have their own dependency graphs). Informational only -- no
 * checkout/upgrade action here, that's task #241's Settings
 * subscription-management page. read_only reuses the existing support
 * mailto link (task #235) as the only actionable step until that page
 * exists.
 */
export function subscriptionBannerFor(
  user: UserProfile | null,
  now: Date = new Date(),
): SubscriptionBanner | null {
  if (!user) return null;

  if (user.business_subscription_status === 'trialing' && user.business_trial_ends_at) {
    const daysLeft = Math.max(
      0,
      Math.ceil((new Date(user.business_trial_ends_at).getTime() - now.getTime()) / 86_400_000),
    );
    return {
      kind: 'trial',
      message: `${daysLeft} day${daysLeft === 1 ? '' : 's'} left in your free trial.`,
    };
  }
  if (user.business_subscription_status === 'past_due') {
    return {
      kind: 'past_due',
      message: 'Your last payment failed. Please update your billing to avoid losing write access.',
    };
  }
  if (user.business_subscription_status === 'read_only') {
    return {
      kind: 'read_only',
      message: 'Your account is read-only due to a billing issue.',
    };
  }
  return null;
}

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
