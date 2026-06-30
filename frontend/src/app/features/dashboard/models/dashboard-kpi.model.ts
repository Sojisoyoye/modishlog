export interface RecentSaleItem {
  product_name: string;
  quantity: number;
  revenue: string;
  margin_pct: string | null;
}

export interface DashboardKpiSummary {
  total_sales: string;
  net: string;
  invoice_due: string;
  total_sell_return: string;
  total_sell_return_paid: string;
  total_purchase: string;
  purchase_due: string;
  total_purchase_return: string;
  total_purchase_return_paid: string;
  expense: string;
  transaction_count: number;
  yesterday_sales: string;
  recent_sales: RecentSaleItem[];
}
