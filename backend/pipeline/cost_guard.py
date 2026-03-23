from loguru import logger

from backend.config import settings


class BudgetExceededError(Exception):
    pass


class InsufficientEvidenceError(Exception):
    pass


class CostGuard:
    def __init__(self, max_budget: float | None = None) -> None:
        self.max_budget = max_budget or settings.max_budget_usd
        self.total_cost = 0.0
        self._calls: list[dict] = []

    def track(self, agent: str, cost: float) -> None:
        self.total_cost += cost
        self._calls.append({"agent": agent, "cost": cost, "cumulative": self.total_cost})
        logger.info(f"Cost tracker: {agent} ${cost:.4f} | Total: ${self.total_cost:.4f} / ${self.max_budget:.2f}")
        if self.total_cost > self.max_budget:
            raise BudgetExceededError(
                f"Budget exceeded: ${self.total_cost:.4f} > ${self.max_budget:.2f}"
            )

    @property
    def remaining(self) -> float:
        return max(0, self.max_budget - self.total_cost)

    @property
    def summary(self) -> list[dict]:
        return self._calls
