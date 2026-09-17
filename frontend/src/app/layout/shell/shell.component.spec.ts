import { subscriptionBannerFor } from './shell.component';
import { UserProfile } from '../../core/services/auth.service';

function makeUser(overrides: Partial<UserProfile>): UserProfile {
  return {
    id: 'u1',
    email: 'owner@example.com',
    full_name: 'Owner',
    role: 'owner',
    ...overrides,
  };
}

describe('subscriptionBannerFor', () => {
  it('returns null when there is no user', () => {
    expect(subscriptionBannerFor(null)).toBeNull();
  });

  it('returns null for an active subscription', () => {
    const user = makeUser({ business_subscription_status: 'active' });
    expect(subscriptionBannerFor(user)).toBeNull();
  });

  it('shows a trial countdown while trialing', () => {
    const now = new Date('2026-01-01T00:00:00Z');
    const user = makeUser({
      business_subscription_status: 'trialing',
      business_trial_ends_at: '2026-01-04T00:00:00Z',
    });
    const banner = subscriptionBannerFor(user, now);
    expect(banner?.kind).toBe('trial');
    expect(banner?.message).toBe('3 days left in your free trial.');
  });

  it('uses singular "day" when exactly one day remains', () => {
    const now = new Date('2026-01-01T00:00:00Z');
    const user = makeUser({
      business_subscription_status: 'trialing',
      business_trial_ends_at: '2026-01-02T00:00:00Z',
    });
    const banner = subscriptionBannerFor(user, now);
    expect(banner?.message).toBe('1 day left in your free trial.');
  });

  it('floors days-left at 0 once the trial has already ended', () => {
    const now = new Date('2026-01-10T00:00:00Z');
    const user = makeUser({
      business_subscription_status: 'trialing',
      business_trial_ends_at: '2026-01-04T00:00:00Z',
    });
    const banner = subscriptionBannerFor(user, now);
    expect(banner?.message).toBe('0 days left in your free trial.');
  });

  it('shows a past-due warning', () => {
    const user = makeUser({ business_subscription_status: 'past_due' });
    const banner = subscriptionBannerFor(user);
    expect(banner?.kind).toBe('past_due');
  });

  it('shows a read-only notice', () => {
    const user = makeUser({ business_subscription_status: 'read_only' });
    const banner = subscriptionBannerFor(user);
    expect(banner?.kind).toBe('read_only');
  });
});
