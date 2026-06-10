import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./layout/shell/shell.component').then((m) => m.ShellComponent),
    canActivate: [authGuard],
    children: [
      {
        path: '',
        redirectTo: 'dashboard',
        pathMatch: 'full',
      },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/pages/dashboard-page.component').then(
            (m) => m.DashboardPageComponent,
          ),
      },
      {
        path: 'sales',
        loadComponent: () =>
          import('./features/sales/pages/sales-page.component').then((m) => m.SalesPageComponent),
      },
      {
        path: 'inventory',
        loadComponent: () =>
          import('./features/inventory/pages/inventory-page.component').then(
            (m) => m.InventoryPageComponent,
          ),
      },
      {
        path: 'orders',
        loadComponent: () =>
          import('./features/orders/pages/orders-page.component').then(
            (m) => m.OrdersPageComponent,
          ),
      },
      {
        path: 'pricing',
        loadComponent: () =>
          import('./features/pricing/pages/pricing-page.component').then(
            (m) => m.PricingPageComponent,
          ),
      },
      {
        path: 'cashflow',
        loadComponent: () =>
          import('./features/cashflow/pages/cashflow-page.component').then(
            (m) => m.CashflowPageComponent,
          ),
      },
      {
        path: 'fx',
        loadComponent: () =>
          import('./features/fx/pages/fx-page.component').then((m) => m.FxPageComponent),
      },
      {
        path: 'recommendations',
        loadComponent: () =>
          import('./features/recommendations/pages/recommendations-page.component').then(
            (m) => m.RecommendationsPageComponent,
          ),
      },
      {
        path: 'products',
        loadComponent: () =>
          import('./features/products/pages/products-page.component').then(
            (m) => m.ProductsPageComponent,
          ),
      },
      {
        path: 'suppliers',
        loadComponent: () =>
          import('./features/suppliers/pages/suppliers-page.component').then(
            (m) => m.SuppliersPageComponent,
          ),
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./features/settings/pages/settings-page.component').then(
            (m) => m.SettingsPageComponent,
          ),
      },
      {
        path: 'settings/invoice-schemes',
        loadComponent: () =>
          import('./features/settings/pages/invoice-schemes-page.component').then(
            (m) => m.InvoiceSchemesPageComponent,
          ),
      },
    ],
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/pages/login-page.component').then((m) => m.LoginPageComponent),
  },
  {
    path: 'forgot-password',
    loadComponent: () =>
      import('./features/auth/pages/login-page.component').then((m) => m.LoginPageComponent),
  },
  {
    path: 'reset-password',
    loadComponent: () =>
      import('./features/auth/pages/reset-password-page.component').then(
        (m) => m.ResetPasswordPageComponent,
      ),
  },
  {
    path: '**',
    redirectTo: '',
  },
];
