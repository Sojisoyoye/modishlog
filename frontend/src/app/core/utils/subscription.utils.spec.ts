import { trialDaysLeft } from './subscription.utils';

describe('trialDaysLeft', () => {
  it('computes whole days remaining, rounded up', () => {
    const now = new Date('2026-01-01T00:00:00Z');
    expect(trialDaysLeft('2026-01-04T00:00:00Z', now)).toBe(3);
  });

  it('floors at 0 once the trial has already ended', () => {
    const now = new Date('2026-01-10T00:00:00Z');
    expect(trialDaysLeft('2026-01-04T00:00:00Z', now)).toBe(0);
  });
});
