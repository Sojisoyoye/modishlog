import { UserProfile } from '../services/auth.service';

export interface SubscriptionBanner {
  kind: 'trial' | 'past_due' | 'read_only';
  message: string;
}

/**
 * Pure function (task #240) so the status->message mapping is
 * unit-testable without rendering a full component tree. Shared between
 * the app-shell status banner and the Settings subscription card (task
 * #241) so trial day-math can't silently drift between the two.
 */
export function subscriptionBannerFor(
  user: UserProfile | null,
  now: Date = new Date(),
): SubscriptionBanner | null {
  if (!user) return null;

  if (user.business_subscription_status === 'trialing' && user.business_trial_ends_at) {
    const daysLeft = trialDaysLeft(user.business_trial_ends_at, now);
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

export function trialDaysLeft(trialEndsAt: string, now: Date = new Date()): number {
  return Math.max(0, Math.ceil((new Date(trialEndsAt).getTime() - now.getTime()) / 86_400_000));
}
