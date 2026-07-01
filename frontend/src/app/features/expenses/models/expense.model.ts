export interface ExpenseCategory {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface ExpenseCategoryCreate {
  name: string;
  description?: string | null;
}

export interface ExpenseRead {
  id: string;
  category_id: string | null;
  category_name: string | null;
  ref_no: string | null;
  amount_ngn: string;
  fx_rate: string | null;
  amount_usd: string;
  currency: string;
  expense_date: string;
  payment_method: string | null;
  note: string | null;
  location_id: string | null;
  created_by: string;
  created_at: string;
}

export interface ExpenseCreate {
  category_id?: string | null;
  ref_no?: string | null;
  amount_ngn: string;
  fx_rate?: string | null;
  amount_usd: string;
  currency?: string;
  expense_date: string;
  payment_method?: string | null;
  note?: string | null;
  location_id?: string | null;
}

export interface ExpenseUpdate {
  category_id?: string | null;
  ref_no?: string | null;
  amount_ngn?: string;
  fx_rate?: string | null;
  amount_usd?: string;
  currency?: string;
  expense_date?: string;
  payment_method?: string | null;
  note?: string | null;
}

export interface ExpenseListResponse {
  items: ExpenseRead[];
  total: number;
  page: number;
  page_size: number;
}
