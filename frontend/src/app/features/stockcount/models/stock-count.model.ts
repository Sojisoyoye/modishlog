export interface StockCountItem {
  id: string;
  stock_count_id: string;
  product_id: string;
  product_name: string;
  order_line_item_id: string | null;
  system_quantity_at_count: number | null;
  counted_quantity: number | null;
  variance: number | null;
  notes: string | null;
}

export interface StockCount {
  id: string;
  count_date: string;
  count_type: 'PRODUCT' | 'LOT';
  status: 'DRAFT' | 'FINALIZED';
  notes: string | null;
  created_by: string;
  finalized_at: string | null;
  created_at: string;
  items: StockCountItem[];
}

export interface StockCountListItem {
  id: string;
  count_date: string;
  count_type: 'PRODUCT' | 'LOT';
  status: 'DRAFT' | 'FINALIZED';
  notes: string | null;
  created_at: string;
  finalized_at: string | null;
  item_count: number;
}

export interface CreateStockCountRequest {
  count_date: string;
  count_type: 'PRODUCT' | 'LOT';
  notes: string | null;
}
