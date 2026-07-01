import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../../../core/services/api.service';
import {
  ExpenseCategory,
  ExpenseCategoryCreate,
  ExpenseCreate,
  ExpenseListResponse,
  ExpenseRead,
  ExpenseUpdate,
} from '../models/expense.model';

@Injectable({ providedIn: 'root' })
export class ExpensesService {
  private readonly api = inject(ApiService);

  listCategories(): Observable<ExpenseCategory[]> {
    return this.api.get<ExpenseCategory[]>('/expense-categories');
  }

  createCategory(data: ExpenseCategoryCreate): Observable<ExpenseCategory> {
    return this.api.post<ExpenseCategory>('/expense-categories', data);
  }

  listExpenses(params?: Record<string, string>): Observable<ExpenseListResponse> {
    return this.api.get<ExpenseListResponse>('/expenses', params);
  }

  getExpense(id: string): Observable<ExpenseRead> {
    return this.api.get<ExpenseRead>(`/expenses/${id}`);
  }

  createExpense(data: ExpenseCreate): Observable<ExpenseRead> {
    return this.api.post<ExpenseRead>('/expenses', data);
  }

  updateExpense(id: string, data: ExpenseUpdate): Observable<ExpenseRead> {
    return this.api.put<ExpenseRead>(`/expenses/${id}`, data);
  }

  deleteExpense(id: string): Observable<void> {
    return this.api.delete<void>(`/expenses/${id}`);
  }
}
