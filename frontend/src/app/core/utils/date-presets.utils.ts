/** Shared date-range preset logic used by all report pages. */

export interface DatePreset {
  label: string;
  key: string;
  range: () => { start: string; end: string };
}

function toIso(d: Date): string {
  return d.toLocaleDateString('en-CA'); // YYYY-MM-DD in local time
}

function startOfWeek(): Date {
  const d = new Date();
  d.setDate(d.getDate() - d.getDay());
  d.setHours(0, 0, 0, 0);
  return d;
}

function startOfMonth(offset = 0): Date {
  const d = new Date();
  d.setMonth(d.getMonth() + offset, 1);
  d.setHours(0, 0, 0, 0);
  return d;
}

function endOfMonth(offset = 0): Date {
  const d = new Date();
  d.setMonth(d.getMonth() + offset + 1, 0);
  d.setHours(23, 59, 59, 999);
  return d;
}

function startOfQuarter(): Date {
  const d = new Date();
  const q = Math.floor(d.getMonth() / 3);
  d.setMonth(q * 3, 1);
  d.setHours(0, 0, 0, 0);
  return d;
}

function endOfQuarter(): Date {
  const d = new Date();
  const q = Math.floor(d.getMonth() / 3);
  d.setMonth(q * 3 + 3, 0);
  d.setHours(23, 59, 59, 999);
  return d;
}

export const DATE_PRESETS: DatePreset[] = [
  {
    label: 'This Week',
    key: 'this_week',
    range: () => ({ start: toIso(startOfWeek()), end: toIso(new Date()) }),
  },
  {
    label: 'This Month',
    key: 'this_month',
    range: () => ({ start: toIso(startOfMonth()), end: toIso(endOfMonth()) }),
  },
  {
    label: 'Last 30 Days',
    key: 'last_30',
    range: () => {
      const d = new Date();
      d.setDate(d.getDate() - 30);
      return { start: toIso(d), end: toIso(new Date()) };
    },
  },
  {
    label: 'This Quarter',
    key: 'this_quarter',
    range: () => ({ start: toIso(startOfQuarter()), end: toIso(endOfQuarter()) }),
  },
  {
    label: 'YTD',
    key: 'ytd',
    range: () => {
      const d = new Date();
      d.setMonth(0, 1);
      d.setHours(0, 0, 0, 0);
      return { start: toIso(d), end: toIso(new Date()) };
    },
  },
  {
    label: 'Last Year',
    key: 'last_year',
    range: () => {
      const y = new Date().getFullYear() - 1;
      return { start: `${y}-01-01`, end: `${y}-12-31` };
    },
  },
];
