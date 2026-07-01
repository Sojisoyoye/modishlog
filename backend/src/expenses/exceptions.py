import uuid


class ExpenseNotFoundError(Exception):
    def __init__(self, expense_id: uuid.UUID) -> None:
        self.expense_id = expense_id
        super().__init__(f"Expense {expense_id} not found")


class ExpenseCategoryNotFoundError(Exception):
    def __init__(self, category_id: uuid.UUID) -> None:
        self.category_id = category_id
        super().__init__(f"Expense category {category_id} not found")
