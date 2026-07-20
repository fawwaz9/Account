import { get } from "../../services/apiClient";
import { endpoints } from "../../services/endpoints";
import { BudgetItem, GoalItem } from "./types";

export async function fetchBudgets(userId: string): Promise<BudgetItem[]> {
  return get<BudgetItem[]>(endpoints.finances.budgets(userId));
}

export async function fetchGoals(userId: string): Promise<GoalItem[]> {
  return get<GoalItem[]>(endpoints.finances.goals(userId));
}
