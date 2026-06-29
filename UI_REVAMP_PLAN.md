# ModishLog UI Revamp — Design System Reference

## Stack
- Angular 21 (standalone components, Signals, OnPush)
- Tailwind CSS v4 (@theme in src/styles.css — no tailwind.config.js)
- PrimeNG v21 (Aura preset, emerald primary scale)
- Inter font (npm @fontsource/inter)

## Color Tokens (styles.css @theme)
| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#059669` | CTA buttons, active states, links |
| `--color-primary-light` | `#ECFDF5` | Button hover tints, icon badge backgrounds |
| `--color-secondary` | `#047857` | Button hover, secondary actions |
| `--color-success` | `#059669` | Positive indicators |
| `--color-warning` | `#D97706` | Caution states |
| `--color-danger` | `#DC2626` | Errors, destructive actions |
| `--color-info` | `#2563EB` | Informational |
| `--color-text` | `#111827` | Primary body text |
| `--color-muted` | `#6B7280` | Secondary/helper text |
| `--color-background` | `#F9FAFB` | Page background |
| `--color-surface` | `#FFFFFF` | Cards, modals |
| `--color-border` | `#E5E7EB` | All borders |

## Component Patterns

### Primary Button
```html
<button class="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-secondary min-h-[44px]">
  Label
</button>
```

### Card
```html
<div class="rounded-xl border border-[--color-border] bg-white p-5 shadow-sm">
```

### Page Header
```html
<div class="mb-6">
  <h2 class="text-2xl font-bold text-text">Title</h2>
  <p class="mt-1 text-sm text-muted">Subtitle</p>
</div>
```

### Section Icon Badge
```html
<div class="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50">
  <i class="pi pi-[icon] text-sm text-emerald-700"></i>
</div>
```

### Tab Navigation
```html
<!-- Active tab -->
<button class="whitespace-nowrap border-b-2 border-primary px-4 py-2.5 text-sm font-semibold text-primary">
<!-- Inactive tab -->
<button class="whitespace-nowrap border-b-2 border-transparent px-4 py-2.5 text-sm text-muted hover:text-text">
```

## Accessibility Rules
- All interactive elements: `min-h-[44px]` (WCAG 2.5.5 touch target)
- Focus ring: `outline: 2px solid var(--color-primary); outline-offset: 2px`
- Color contrast: primary on white passes AA (4.6:1 ratio)

## Conventions
- All components: `standalone: true`, `ChangeDetectionStrategy.OnPush`
- No separate .html files — templates inline in .ts
- Signal-based state throughout
- No NgModules
