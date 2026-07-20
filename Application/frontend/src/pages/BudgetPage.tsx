import { useEffect, useState } from "react";
import { fetchBudgets, fetchGoals } from "../features/budget/api";
import { BudgetItem, GoalItem } from "../features/budget/types";
import { getOrCreateUserId } from "../services/userService";

export default function BudgetPage() {
  const [budgets, setBudgets] = useState<BudgetItem[]>([]);
  const [goals, setGoals] = useState<GoalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const userId = await getOrCreateUserId();
        const [budgetData, goalData] = await Promise.all([
          fetchBudgets(userId),
          fetchGoals(userId),
        ]);
        if (mounted) {
          setBudgets(budgetData);
          setGoals(goalData);
        }
      } catch (err) {
        if (mounted) setError(err instanceof Error ? err.message : "Failed to load budget data");
      } finally {
        if (mounted) setLoading(false);
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="container">
      <h1>Budget</h1>
      <div className="card">
        {loading && <p>Connecting to budget API...</p>}
        {error && <p className="muted">{error}</p>}
        {!loading && !error && (
          <>
            <h2>Budgets</h2>
            <ul>
              {budgets.map((budget) => (
                <li key={budget.id}>{budget.name}</li>
              ))}
            </ul>
            <h2>Goals</h2>
            <ul>
              {goals.map((goal) => (
                <li key={goal.id}>{goal.name}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
