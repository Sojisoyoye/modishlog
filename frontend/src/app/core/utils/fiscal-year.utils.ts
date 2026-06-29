function toDateString(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * Compute the default report date range from a fiscal year start configuration.
 * Mirrors the resolve_default_date_range logic in the backend service.
 */
export function computeDefaultDateRange(
  month: number | null,
  day: number | null,
): { start: string; end: string } {
  const today = new Date();
  const end = toDateString(today);

  if (month === null || day === null) {
    const yearAgo = new Date(today);
    yearAgo.setFullYear(today.getFullYear() - 1);
    return { start: toDateString(yearAgo), end };
  }

  // Most recent FY start ≤ today
  const fysThisYear = new Date(today.getFullYear(), month - 1, day);
  if (fysThisYear <= today) {
    return { start: toDateString(fysThisYear), end };
  }
  return { start: toDateString(new Date(today.getFullYear() - 1, month - 1, day)), end };
}
