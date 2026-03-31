"""Cashflow domain exceptions."""

import uuid


class ProjectionNotFoundError(Exception):
    def __init__(self, projection_id: uuid.UUID | None = None):
        self.projection_id = projection_id
        msg = "No cashflow projection found"
        if projection_id:
            msg = f"Cashflow projection {projection_id} not found"
        super().__init__(msg)


class LoanNotFoundError(Exception):
    def __init__(self, loan_id: uuid.UUID):
        self.loan_id = loan_id
        super().__init__(f"Loan obligation {loan_id} not found")


class LoanAlreadySettledError(Exception):
    def __init__(self, loan_id: uuid.UUID):
        self.loan_id = loan_id
        super().__init__(f"Loan {loan_id} is already settled")


class ScenarioNotFoundError(Exception):
    def __init__(self, scenario_id: uuid.UUID):
        self.scenario_id = scenario_id
        super().__init__(f"Stress scenario {scenario_id} not found")


class InvalidScenarioTypeError(Exception):
    def __init__(self, scenario_type: str):
        self.scenario_type = scenario_type
        super().__init__(
            f"Invalid scenario type '{scenario_type}'. "
            "Valid types: BASE, FX_SHOCK_10, FX_SHOCK_20, "
            "DEMAND_DROP_10, DEMAND_DROP_20, COMBINED_STRESS"
        )
