import { formatMoney } from './money.utils';

describe('formatMoney', () => {
  it('formats a number as NGN currency with no decimal places', () => {
    expect(formatMoney(5000)).toBe('₦5,000');
  });

  it('formats a numeric string the same way as a number', () => {
    expect(formatMoney('5000')).toBe(formatMoney(5000));
  });

  it('rounds fractional amounts to the nearest whole naira', () => {
    expect(formatMoney(1999.6)).toBe('₦2,000');
  });

  it('formats zero', () => {
    expect(formatMoney(0)).toBe('₦0');
  });
});
