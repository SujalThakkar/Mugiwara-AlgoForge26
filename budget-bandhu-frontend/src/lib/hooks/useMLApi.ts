import { useCallback, useEffect, useState } from 'react';
import {
    mlApi,
    DashboardData,
    Transaction,
    Budget,
    BudgetRecommendation,
    Goal,
    Gamification,
    TransactionStats,
    Bill,
    Tax80CData,
} from '../api/ml-api';

export function useDashboard(userId: string | null) {
    const [data, setData] = useState<DashboardData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchDashboard = useCallback(async (signal?: AbortSignal) => {
        if (!userId) return;

        setLoading(true);
        setError(null);

        try {
            const dashboardData = await mlApi.dashboard.get(userId);
            if (signal?.aborted) return;
            setData(dashboardData);
        } catch (err) {
            if (signal?.aborted) return;
            setError(err instanceof Error ? err.message : 'Failed to fetch dashboard');
        } finally {
            if (!signal?.aborted) setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        const controller = new AbortController();
        void fetchDashboard(controller.signal);
        return () => controller.abort();
    }, [fetchDashboard]);

    return {
        data,
        loading,
        error,
        refetch: () => fetchDashboard(),
    };
}

export function useTransactions(userId: string | null, options?: {
    limit?: number;
    category?: string;
    anomaliesOnly?: boolean;
}) {
    const [transactions, setTransactions] = useState<Transaction[]>([]);
    const [stats, setStats] = useState<TransactionStats | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchTransactions = useCallback(async (signal?: AbortSignal) => {
        if (!userId) return;

        setLoading(true);
        setError(null);

        try {
            const [txns, txnStats] = await Promise.all([
                mlApi.transactions.getAll(userId, options),
                mlApi.transactions.getStats(userId),
            ]);

            if (signal?.aborted) return;
            setTransactions(txns);
            setStats(txnStats);
        } catch (err) {
            if (signal?.aborted) return;
            setError(err instanceof Error ? err.message : 'Failed to fetch transactions');
        } finally {
            if (!signal?.aborted) setLoading(false);
        }
    }, [userId, options?.anomaliesOnly, options?.category, options?.limit]);

    useEffect(() => {
        const controller = new AbortController();
        void fetchTransactions(controller.signal);
        return () => controller.abort();
    }, [fetchTransactions]);

    const addTransaction = useCallback(async (transaction: Parameters<typeof mlApi.transactions.add>[1]) => {
        if (!userId) return;
        const result = await mlApi.transactions.add(userId, transaction);
        await fetchTransactions();
        return result;
    }, [fetchTransactions, userId]);

    const uploadCsv = useCallback(async (file: File) => {
        if (!userId) return;
        const result = await mlApi.transactions.uploadCsv(userId, file);
        await fetchTransactions();
        return result;
    }, [fetchTransactions, userId]);

    return {
        transactions,
        stats,
        loading,
        error,
        refetch: () => fetchTransactions(),
        addTransaction,
        uploadCsv,
    };
}

export function useBudget(userId: string | null) {
    const [budget, setBudget] = useState<Budget | null>(null);
    const [recommendations, setRecommendations] = useState<BudgetRecommendation[]>([]);
    const [savingsPotential, setSavingsPotential] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchBudget = useCallback(async (signal?: AbortSignal) => {
        if (!userId) return;

        setLoading(true);
        setError(null);

        try {
            const [budgetData, recommendationData] = await Promise.all([
                mlApi.budget.get(userId),
                mlApi.budget.getRecommendations(userId),
            ]);

            if (signal?.aborted) return;
            setBudget(budgetData);
            setRecommendations(recommendationData.recommendations);
            setSavingsPotential(recommendationData.total_savings_potential);
        } catch (err) {
            if (signal?.aborted) return;
            setError(err instanceof Error ? err.message : 'Failed to fetch budget');
        } finally {
            if (!signal?.aborted) setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        const controller = new AbortController();
        void fetchBudget(controller.signal);
        return () => controller.abort();
    }, [fetchBudget]);

    const updateBudget = useCallback(async (allocations: Array<{ category: string; allocated: number }>) => {
        if (!userId || !budget) return;
        await mlApi.budget.update(userId, {
            total_income: budget.total_income,
            allocations: allocations.map((allocation) => ({ ...allocation, spent: 0 })),
        });
        await fetchBudget();
    }, [budget, fetchBudget, userId]);

    const submitFeedback = useCallback(async (category: string, feedback: 'accepted' | 'rejected') => {
        if (!userId) return;
        await mlApi.budget.submitFeedback(userId, category, feedback);
        await fetchBudget();
    }, [fetchBudget, userId]);

    return {
        budget,
        recommendations,
        savingsPotential,
        loading,
        error,
        refetch: () => fetchBudget(),
        updateBudget,
        submitFeedback,
    };
}

export function useGoals(userId: string | null) {
    const [goals, setGoals] = useState<Goal[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchGoals = useCallback(async (signal?: AbortSignal) => {
        if (!userId) return;

        setLoading(true);
        setError(null);

        try {
            const data = await mlApi.goals.getAll(userId);
            if (signal?.aborted) return;
            setGoals(data);
        } catch (err) {
            if (signal?.aborted) return;
            setError(err instanceof Error ? err.message : 'Failed to fetch goals');
        } finally {
            if (!signal?.aborted) setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        const controller = new AbortController();
        void fetchGoals(controller.signal);
        return () => controller.abort();
    }, [fetchGoals]);

    const createGoal = useCallback(async (goal: Omit<Parameters<typeof mlApi.goals.create>[0], 'user_id'>) => {
        if (!userId) return;
        const result = await mlApi.goals.create({ ...goal, user_id: userId });
        await fetchGoals();
        return result;
    }, [fetchGoals, userId]);

    const contributeToGoal = useCallback(async (goalId: string, amount: number) => {
        const result = await mlApi.goals.contribute(goalId, amount);
        await fetchGoals();
        return result;
    }, [fetchGoals]);

    const deleteGoal = useCallback(async (goalId: string) => {
        await mlApi.goals.delete(goalId);
        await fetchGoals();
    }, [fetchGoals]);

    return {
        goals,
        loading,
        error,
        refetch: () => fetchGoals(),
        createGoal,
        contributeToGoal,
        deleteGoal,
    };
}

export function useGamification(userId: string | null) {
    const [gamification, setGamification] = useState<Gamification | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchGamification = useCallback(async () => {
        if (!userId) return;

        setLoading(true);
        setError(null);

        try {
            const data = await mlApi.gamification.get(userId);
            setGamification(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch gamification');
        } finally {
            setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        void fetchGamification();
    }, [fetchGamification]);

    const checkBadges = useCallback(async () => {
        if (!userId) return;
        const result = await mlApi.gamification.checkBadges(userId);
        await fetchGamification();
        return result;
    }, [fetchGamification, userId]);

    return {
        gamification,
        loading,
        error,
        refetch: () => fetchGamification(),
        checkBadges,
    };
}

export function useApiHealth() {
    const [healthy, setHealthy] = useState<boolean | null>(null);
    const [checking, setChecking] = useState(true);

    useEffect(() => {
        const checkHealth = async () => {
            try {
                const result = await mlApi.health();
                setHealthy(result.status === 'healthy');
            } catch {
                setHealthy(false);
            } finally {
                setChecking(false);
            }
        };

        void checkHealth();
    }, []);

    return { healthy, checking };
}

// ── useBills: polls every 30s so dashboard refreshes when Bandhu adds a bill ──
export function useBills(userId: string | null) {
    const [bills, setBills] = useState<Bill[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchBills = useCallback(async () => {
        if (!userId) return;
        setLoading(true);
        try {
            const data = await mlApi.bills.getAll(userId);
            setBills(data);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch bills');
        } finally {
            setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        void fetchBills();
        // Poll every 30s so chat-added bills appear automatically
        const interval = setInterval(() => void fetchBills(), 30_000);
        return () => clearInterval(interval);
    }, [fetchBills]);

    const deleteBill = useCallback(async (billId: string) => {
        if (!userId) return;
        await mlApi.bills.delete(userId, billId);
        await fetchBills();
    }, [userId, fetchBills]);

    return { bills, loading, error, refetch: fetchBills, deleteBill };
}

// ── useTax80C: fetches 80C tracker data from Atlas ───────────────────────────
export function useTax80C(userId: string | null) {
    const [taxData, setTaxData] = useState<Tax80CData | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchTax = useCallback(async () => {
        if (!userId) return;
        setLoading(true);
        try {
            const data = await mlApi.tax.get80C(userId);
            setTaxData(data);
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to fetch 80C data');
        } finally {
            setLoading(false);
        }
    }, [userId]);

    useEffect(() => {
        void fetchTax();
    }, [fetchTax]);

    return { taxData, loading, error, refetch: fetchTax };
}
