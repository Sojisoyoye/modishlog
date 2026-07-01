export interface Sale {
  id: string;
  sale_date: string;
  total_amount: string;
  customer_name: string | null;
  product_id: string;
}

export interface SaleListResponse {
  items: Sale[];
  total: number;
  page: number;
  page_size: number;
}

export interface SellReturn {
  id: string;
  sale_id: string;
  ref_no: string | null;
  return_date: string;
  total_amount: string;
  amount_paid: string;
  notes: string | null;
  created_at: string;
}

export interface SellReturnCreate {
  return_date: string;
  total_amount: string;
  amount_paid?: string;
  ref_no?: string | null;
  notes?: string | null;
}

export interface SellReturnListResponse {
  items: SellReturn[];
  total: number;
  page: number;
  page_size: number;
}

export interface PurchaseReturn {
  id: string;
  original_order_id: string;
  ref_no: string | null;
  return_date: string;
  notes: string | null;
  total_amount: string;
  created_by: string;
  created_at: string;
}

export interface PurchaseReturnListResponse {
  items: PurchaseReturn[];
  total: number;
  page: number;
  page_size: number;
}
