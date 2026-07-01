import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';
import { noAuthGuard } from './core/guards/no-auth.guard';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./features/landing/pages/landing-page.component').then(
        (m) => m.LandingPageComponent,
      ),
    pathMatch: 'full',
    canActivate: [noAuthGuard],
  },
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
        path: 'sales/transactions/:id',
        loadComponent: () =>
          import('./features/sales/pages/transaction-detail-page.component').then(
            (m) => m.TransactionDetailPageComponent,
          ),
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
        path: 'returns',
        loadComponent: () =>
          import('./features/returns/pages/returns-page/returns-page.component').then(
            (m) => m.ReturnsPageComponent,
          ),
      },
      {
        path: 'expenses',
        loadComponent: () =>
          import('./features/expenses/pages/expenses-page/expenses-page.component').then(
            (m) => m.ExpensesPageComponent,
          ),
      },
      {
        path: 'orders/:id',
        loadComponent: () =>
          import('./features/orders/pages/order-detail-page.component').then(
            (m) => m.OrderDetailPageComponent,
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
        path: 'customers',
        loadComponent: () =>
          import('./features/customers/pages/customers-page/customers-page.component').then(
            (m) => m.CustomersPageComponent,
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
      {
        path: 'settings/locations',
        loadComponent: () =>
          import('./features/settings/pages/locations-page.component').then(
            (m) => m.LocationsPageComponent,
          ),
      },
      {
        path: 'reports',
        loadComponent: () =>
          import('./features/reports/pages/reports-index.component').then(
            (m) => m.ReportsIndexComponent,
          ),
      },
      {
        path: 'reports/profit-loss',
        loadComponent: () =>
          import('./features/reports/pages/profit-loss-page.component').then(
            (m) => m.ProfitLossPageComponent,
          ),
      },
      {
        path: 'reports/stock',
        loadComponent: () =>
          import('./features/reports/pages/stock-report-page.component').then(
            (m) => m.StockReportPageComponent,
          ),
      },
      {
        path: 'reports/purchase-sale',
        loadComponent: () =>
          import('./features/reports/pages/purchase-sale-page.component').then(
            (m) => m.PurchaseSalePageComponent,
          ),
      },
      {
        path: 'reports/product-sales',
        loadComponent: () =>
          import('./features/reports/pages/product-sales-page.component').then(
            (m) => m.ProductSalesPageComponent,
          ),
      },
      {
        path: 'reports/trending-products',
        loadComponent: () =>
          import('./features/reports/pages/trending-products-page.component').then(
            (m) => m.TrendingProductsPageComponent,
          ),
      },
      {
        path: 'stock-counts',
        loadComponent: () =>
          import('./features/stockcount/pages/stock-count-list-page.component').then(
            (m) => m.StockCountListPageComponent,
          ),
      },
      {
        path: 'stock-counts/:id',
        loadComponent: () =>
          import('./features/stockcount/pages/stock-count-detail-page.component').then(
            (m) => m.StockCountDetailPageComponent,
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
    redirectTo: 'dashboard',
  },
];
