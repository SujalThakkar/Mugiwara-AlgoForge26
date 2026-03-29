import { mockData } from './mock-data';
import { ChatMessage } from '../types/chat';

const ML_API_BASE = process.env.NEXT_PUBLIC_ML_API_URL || 'https://unoperated-merideth-sparklike.ngrok-free.dev';

async function callApi<T>(endpoint: string, fallbackData: T, options?: RequestInit): Promise<T> {
    try {
        const body = options?.body;
        const shouldSetJsonHeader = !(typeof FormData !== 'undefined' && body instanceof FormData);

        const response = await fetch(`${ML_API_BASE}${endpoint}`, {
            ...options,
            headers: shouldSetJsonHeader
                ? {
                    'Content-Type': 'application/json',
                    'ngrok-skip-browser-warning': '1',
                    ...options?.headers,
                }
                : {
                    'ngrok-skip-browser-warning': '1',
                    ...options?.headers,
                },
        });

        if (!response.ok) {
            return fallbackData;
        }

        return await response.json() as T;
    } catch {
        return fallbackData;
    }
}

const RAG_API_BASE = process.env.NEXT_PUBLIC_API_URL || 'https://babylike-overtimorously-stacey.ngrok-free.dev';

async function ragCallApi<T>(endpoint: string, fallbackData: T, options?: RequestInit): Promise<T> {
    try {
        const body = options?.body;
        const shouldSetJsonHeader = !(typeof FormData !== 'undefined' && body instanceof FormData);

        const response = await fetch(`${RAG_API_BASE}${endpoint}`, {
            ...options,
            headers: shouldSetJsonHeader
                ? {
                    'Content-Type': 'application/json',
                    'ngrok-skip-browser-warning': '1',
                    ...options?.headers,
                }
                : {
                    'ngrok-skip-browser-warning': '1',
                    ...options?.headers,
                },
        });

        if (!response.ok) {
            // Only warn for unexpected errors, 404 (Not Found) is expected for new users/history
            if (response.status !== 404) {
                console.warn(`[RAG API Fallback] ${endpoint} returned ${response.status}`, await response.text().catch(() => ''));
            }
            return fallbackData;
        }

        return await response.json() as T;
    } catch (e) {
        console.error(`[RAG API Fallback] fetch failed for ${endpoint}:`, e);
        return fallbackData;
    }
}


export interface User {
    id: string;
    mobile_number: string;
    name: string;
    email?: string;
    income: number;
    currency: string;
    created_at: string;
}

export interface UserCreateData {
    name: string;
    mobile_number: string;
    password: string;
    income?: number;
}

export interface TranslationResult {
    translatedText: string;
    detectedLanguage?: string;
}

export interface OCRResult {
    amount?: number;
    description?: string;
    date?: string;
    merchant?: string;
    rawText: string;
}

export interface Transaction {
    id: string;
    user_id: string;
    date: string;
    amount: number;
    description: string;
    type: 'debit' | 'credit';
    category: string;
    category_confidence: number;
    is_anomaly: boolean;
    anomaly_score?: number;
    anomaly_severity: 'HIGH' | 'MEDIUM' | 'LOW' | 'NORMAL';
    anomaly_type?: string;
    anomaly_reason?: string;
    notes?: string;
    created_at: string;
}

export interface TransactionUpload {
    date: string;
    amount: number;
    description: string;
    type?: 'debit' | 'credit';
    category?: string;
    notes?: string;
}

export interface TransactionStats {
    total_transactions: number;
    total_anomalies: number;
    anomaly_rate: number;
    category_breakdown: Record<string, { total: number; count: number }>;
}

export interface Insight {
    type: string;
    title: string;
    description: string;
    severity: 'info' | 'success' | 'warning' | 'error';
    icon: string;
}

export interface DashboardData {
    user: {
        id: string;
        name: string;
        income: number;
    };
    stats: {
        current_balance: number;
        month_spent: number;
        month_saved: number;
        savings_rate: number;
        financial_score: number;
        total_transactions: number;
    };
    category_breakdown: Record<string, { total: number; count: number }>;
    anomalies: {
        count: number;
        rate: number;
    };
    insights: Insight[];
    weekly_summary?: {
        save_potential: number;
        message: string;
    };
    forecast: {
        predicted_spending: number;
        predicted_savings: number;
        confidence: number;
        forecast_7d?: Array<{date: string; predicted_amount: number}>;
        monthly_summary?: { projected_total: number; vs_last_month: number; top_category: string };
    } | null;
    budget_summary: {
        total_allocated: number;
        total_spent: number;
        allocations?: Array<{ category: string; allocated: number; spent: number }>;
    } | null;
    goals_summary: {
        total: number;
        total_saved: number;
        total_target: number;
    };
}

export interface BudgetAllocation {
    category: string;
    allocated: number;
    spent: number;
}

export interface Budget {
    id: string;
    user_id: string;
    total_income: number;
    allocations: BudgetAllocation[];
    savings_target: number;
    current_savings: number;
}

// ── Bills (Chat → Dashboard sync) ────────────────────────────────────────────
export interface Bill {
    id: string;
    title: string;
    amount: number;
    due_date: string;        // YYYY-MM-DD
    category: string;
    status: 'upcoming' | 'due-soon' | 'overdue' | 'future';
    days_until_due: number;
    source?: string;
}

// ── 80C Tax Tracker ───────────────────────────────────────────────────────────
export interface Tax80CData {
    fy: string;
    user_id: string;
    total_invested: number;
    eligible_amount: number;
    limit_80c: number;
    remaining_limit: number;
    percentage_used: number;
    slab_rate: number;
    tax_saved: number;
    potential_additional_saving: number;
    breakdown: Record<string, { amount: number; count: number }>;
    recommendations: Array<{ instrument: string; reason: string; potential_tax_saving: number }>;
}

export interface BudgetRecommendation {
    category: string;
    current_spend: number;
    suggested_budget: number;
    savings_potential: number;
    multiplier?: number;
    change?: 'increase' | 'decrease' | 'maintain';
    reasoning: string;
    confidence?: number;
}

export interface Goal {
    id: string;
    user_id: string;
    name: string;
    icon: string;
    target: number;
    current: number;
    deadline: string;
    priority: 'low' | 'medium' | 'high';
    color: string;
    progress_percentage: number;
    remaining: number;
    on_track: boolean;
    eta_days: number | null;
    projected_completion_date?: string | null;
    shortfall_risk?: string | null;
    ai_verified?: boolean;
    milestones: Array<{ amount: number; reached: boolean; date: string | null }>;
}

export interface GoalCreate {
    user_id: string;
    name: string;
    icon?: string;
    target: number;
    deadline: string;
    priority?: 'low' | 'medium' | 'high';
    color?: string;
}

export interface LevelInfo {
    level: number;
    current_xp: number;
    xp_to_next_level: number;
    title: string;
}

export interface Badge {
    id: string;
    name: string;
    description: string;
    icon: string;
    unlocked: boolean;
    unlocked_at: string | null;
    trigger_description: string;
}

export interface Gamification {
    id: string;
    user_id: string;
    level_info: LevelInfo;
    total_xp: number;
    badges: Badge[];
    challenges_completed: number;
    streak_days: number;
}

type GoogleTranslateResponse = [
    Array<[string, string?, unknown?, unknown?]>,
    unknown,
    string?,
];

function getMockTransactions(userId: string): Transaction[] {
    return mockData.transactions.map((transaction) => ({
        id: transaction.id,
        user_id: userId,
        date: transaction.date,
        amount: transaction.amount,
        description: transaction.merchant,
        type: transaction.type,
        category: transaction.category,
        category_confidence: 1,
        is_anomaly: transaction.isAnomaly,
        anomaly_severity: transaction.isAnomaly ? 'HIGH' : 'NORMAL',
        anomaly_type: transaction.isAnomaly ? 'Unusual Spending' : undefined,
        notes: transaction.notes,
        created_at: transaction.date,
    }));
}

function getMockDashboardData(userId: string): DashboardData {
    return {
        user: {
            id: userId,
            name: mockData.user.name,
            income: mockData.user.monthlyIncome,
        },
        stats: {
            current_balance: mockData.dashboardSummary.currentBalance,
            month_spent: mockData.dashboardSummary.monthSpent,
            month_saved: mockData.dashboardSummary.monthSaved,
            savings_rate: mockData.dashboardSummary.savingsRate * 100,
            financial_score: mockData.dashboardSummary.financialScore,
            total_transactions: mockData.transactions.length,
        },
        category_breakdown: mockData.budget.allocations.reduce<Record<string, { total: number; count: number }>>(
            (accumulator, allocation) => ({
                ...accumulator,
                [allocation.category]: { total: allocation.spent, count: 1 },
            }),
            {}
        ),
        anomalies: {
            count: mockData.anomalies.length,
            rate: (mockData.anomalies.length / Math.max(mockData.transactions.length, 1)) * 100,
        },
        insights: mockData.insights.map((insight) => ({
            type: insight.type,
            title: insight.title,
            description: insight.description,
            severity: insight.severity as DashboardData['insights'][number]['severity'],
            icon: insight.icon,
        })),
        forecast: {
            predicted_spending: 32000,
            predicted_savings: mockData.savingsForecast['30day'].predicted,
            confidence: mockData.savingsForecast['30day'].confidence,
            forecast_7d: [{ date: '2026-03-29', predicted_amount: 4200 }],
            monthly_summary: { projected_total: 45000, vs_last_month: 5.2, top_category: 'Shopping' }
        },
        budget_summary: {
            total_allocated: mockData.budget.allocations.reduce((sum, item) => sum + item.allocated, 0),
            total_spent: mockData.budget.allocations.reduce((sum, item) => sum + item.spent, 0),
        },
        goals_summary: {
            total: mockData.goals.length,
            total_saved: mockData.goals.reduce((sum, goal) => sum + goal.current, 0),
            total_target: mockData.goals.reduce((sum, goal) => sum + goal.target, 0),
        },
    };
}

export const mlApi = {
    user: {
        register: async (data: UserCreateData): Promise<User> => {
            const payload = {
                name: data.name,
                password: data.password,
                mobile: data.mobile_number,
                income: data.income ?? 50000,
            };

            return ragCallApi<User>(
                '/api/v1/user/register',
                {
                    id: data.mobile_number,
                    mobile_number: data.mobile_number,
                    name: data.name,
                    email: mockData.user.email,
                    income: data.income ?? mockData.user.monthlyIncome,
                    currency: 'INR',
                    created_at: new Date().toISOString(),
                },
                { method: 'POST', body: JSON.stringify(payload) }
            );
        },

        login: async (mobile_number: string, password: string): Promise<{ message: string; user: User }> => {
            return ragCallApi(
                '/api/v1/user/login',
                {
                    message: 'Logged in (Mock)',
                    user: {
                        id: mobile_number,
                        mobile_number,
                        name: mockData.user.name,
                        email: mockData.user.email,
                        income: mockData.user.monthlyIncome,
                        currency: 'INR',
                        created_at: new Date().toISOString(),
                    },
                },
                { method: 'POST', body: JSON.stringify({ mobile: mobile_number, password }) }
            );
        },

        getProfile: async (userId: string): Promise<User> => {
            return ragCallApi(
                `/api/v1/user/${userId}`,
                {
                    id: userId,
                    mobile_number: userId,
                    name: mockData.user.name,
                    email: mockData.user.email,
                    income: mockData.user.monthlyIncome,
                    currency: 'INR',
                    created_at: new Date().toISOString(),
                }
            );
        },

        updateIncome: async (userId: string, income: number): Promise<{ message: string }> => {
            return ragCallApi(
                `/api/v1/user/${userId}/income?income=${income}`,
                { message: 'Income updated (Mock)' },
                { method: 'PUT' }
            );
        },
    },

    transactions: {
        add: async (userId: string, transaction: TransactionUpload) => {
            return ragCallApi(
                `/api/v1/transactions?user_id=${encodeURIComponent(userId)}`,
                {
                    transaction_id: `txn_mock_${Date.now()}`,
                    category: transaction.category || 'Others',
                    is_anomaly: false,
                    anomaly_severity: 'normal',
                },
                { method: 'POST', body: JSON.stringify(transaction) }
            );
        },

        addBulk: async (userId: string, transactions: TransactionUpload[]) => {
            return ragCallApi(
                '/api/v1/transactions/bulk',
                {
                    inserted_count: transactions.length,
                    categorization_stats: {},
                    anomaly_stats: {},
                },
                { method: 'POST', body: JSON.stringify({ user_id: userId, transactions }) }
            );
        },

        uploadCsv: async (userId: string, file: File) => {
            const formData = new FormData();
            formData.append('file', file);

            return ragCallApi(
                `/api/v1/transactions/upload-csv?user_id=${encodeURIComponent(userId)}`,
                {
                    inserted_count: 24,
                    categorization_stats: {},
                    anomaly_stats: {},
                    message: 'CSV processed (Mock)',
                },
                { method: 'POST', body: formData }
            );
        },

        getAll: async (userId: string, options?: { limit?: number; skip?: number; category?: string; anomaliesOnly?: boolean }): Promise<Transaction[]> => {
            let mockFallback = getMockTransactions(userId);

            if (options?.category) {
                mockFallback = mockFallback.filter((transaction) => transaction.category === options.category);
            }

            if (options?.anomaliesOnly) {
                mockFallback = mockFallback.filter((transaction) => transaction.is_anomaly);
            }

            if (options?.limit) {
                mockFallback = mockFallback.slice(0, options.limit);
            }

            const params = new URLSearchParams();
            if (options?.limit) params.set('limit', String(options.limit));
            if (options?.skip) params.set('skip', String(options.skip));
            if (options?.category) params.set('category', options.category);
            if (options?.anomaliesOnly) params.set('anomalies_only', 'true');

            return ragCallApi(`/api/v1/transactions/${userId}?${params.toString()}`, mockFallback);
        },

        getStats: async (userId: string): Promise<TransactionStats> => {
            return ragCallApi(
                `/api/v1/transactions/${userId}/stats`,
                {
                    total_transactions: mockData.transactions.length,
                    total_anomalies: mockData.anomalies.length,
                    anomaly_rate: (mockData.anomalies.length / Math.max(mockData.transactions.length, 1)) * 100,
                    category_breakdown: mockData.budget.allocations.reduce<Record<string, { total: number; count: number }>>(
                        (accumulator, allocation) => ({
                            ...accumulator,
                            [allocation.category]: { total: allocation.spent, count: 1 },
                        }),
                        {}
                    ),
                }
            );
        },

        getAnomalies: async (userId: string): Promise<Transaction[]> => {
            return ragCallApi(
                `/api/v1/transactions/${userId}/anomalies`,
                getMockTransactions(userId).filter((transaction) => transaction.is_anomaly)
            );
        },
    },

    dashboard: {
        get: async (userId: string): Promise<DashboardData> => {
            return ragCallApi(`/api/v1/dashboard/${userId}`, getMockDashboardData(userId));
        },

        getSpendingTrend: async (userId: string, days: number = 30): Promise<Array<{ date: string; amount: number }>> => {
            return ragCallApi(`/api/v1/dashboard/${userId}/spending-trend?days=${days}`, mockData.spendingTrend);
        },
    },

    budget: {
        get: async (userId: string): Promise<Budget> => {
            return ragCallApi(
                `/api/v1/budget/${userId}`,
                {
                    id: 'budget_mock',
                    user_id: userId,
                    total_income: mockData.budget.totalIncome,
                    allocations: mockData.budget.allocations.map((allocation) => ({
                        category: allocation.category,
                        allocated: allocation.allocated,
                        spent: allocation.spent,
                    })),
                    savings_target: mockData.budget.savingsTarget,
                    current_savings: mockData.budget.currentSavings,
                }
            );
        },

        update: async (userId: string, budget: { total_income: number; allocations: Array<{ category: string; allocated: number; spent?: number }> }) => {
            return ragCallApi(
                `/api/v1/budget/${userId}`,
                {
                    message: 'Budget updated (Mock)',
                    total_allocated: budget.allocations.reduce((sum, allocation) => sum + allocation.allocated, 0),
                },
                { method: 'PUT', body: JSON.stringify({ ...budget, user_id: userId }) }
            );
        },

        getRecommendations: async (userId: string) => {
            return ragCallApi(
                `/api/v1/budget/${userId}/recommend`,
                {
                    user_id: userId,
                    recommendations: [
                        {
                            category: 'Shopping',
                            current_spend: 5420,
                            suggested_budget: 4200,
                            savings_potential: 1220,
                            multiplier: 0.84,
                            change: 'decrease' as const,
                            reasoning: 'Recent shopping spend is above target and can be trimmed safely.',
                        },
                    ],
                    total_savings_potential: 800,
                    method: 'mock-analysis',
                }
            );
        },

        submitFeedback: async (userId: string, category: string, feedback: 'accepted' | 'rejected') => {
            return ragCallApi(
                `/api/v1/budget/${userId}/feedback?category=${encodeURIComponent(category)}&feedback=${feedback}`,
                { message: 'Feedback submitted (Mock)' },
                { method: 'POST' }
            );
        },

        reset: async (userId: string) => {
            return ragCallApi(
                `/api/v1/budget/${userId}/reset`,
                {
                    message: 'Budget reset (Mock)',
                    allocations: mockData.budget.allocations.map((allocation) => ({
                        category: allocation.category,
                        allocated: allocation.allocated,
                        spent: allocation.spent,
                    })),
                },
                { method: 'POST' }
            );
        },
    },

    goals: {
        getAll: async (userId: string): Promise<Goal[]> => {
            return ragCallApi(
                `/api/v1/goals/${userId}`,
                mockData.goals.map((goal) => ({
                    id: goal.id,
                    user_id: userId,
                    name: goal.name,
                    icon: goal.icon,
                    target: goal.target,
                    current: goal.current,
                    deadline: goal.deadline,
                    priority: goal.priority as Goal['priority'],
                    color: goal.color,
                    progress_percentage: (goal.current / goal.target) * 100,
                    remaining: goal.target - goal.current,
                    on_track: goal.priority !== 'high' || goal.current / goal.target > 0.35,
                    eta_days: goal.priority === 'high' ? 95 : 140,
                    projected_completion_date: '2026-07-01',
                    shortfall_risk: 'LOW',
                    ai_verified: true,
                    milestones: goal.milestones,
                }))
            );
        },

        create: async (goal: GoalCreate) => {
            return ragCallApi(
                '/api/v1/goals',
                { goal_id: `goal_mock_${Date.now()}`, name: goal.name, target: goal.target },
                { method: 'POST', body: JSON.stringify(goal) }
            );
        },

        contribute: async (goalId: string, amount: number) => {
            const goal = mockData.goals.find((item) => item.id === goalId) || mockData.goals[0];
            const newCurrent = Math.min(goal.current + amount, goal.target);
            return ragCallApi(
                `/api/v1/goals/${goalId}/contribute`,
                {
                    new_current: newCurrent,
                    progress_percentage: (newCurrent / goal.target) * 100,
                    milestones_reached: [],
                    is_complete: newCurrent >= goal.target,
                    xp_earned: Math.min(Math.floor(amount / 1000), 50),
                },
                { method: 'PUT', body: JSON.stringify({ amount }) }
            );
        },

        getEta: async (goalId: string) => {
            return ragCallApi(
                `/api/v1/goals/${goalId}/eta`,
                { eta_days: 60, days_until_deadline: 120, on_track: true, message: 'On track!' }
            );
        },

        delete: async (goalId: string) => {
            return ragCallApi(
                `/api/v1/goals/${goalId}`,
                { message: 'Goal deleted (Mock)' },
                { method: 'DELETE' }
            );
        },
    },

    gamification: {
        get: async (userId: string): Promise<Gamification> => {
            return ragCallApi(
                `/api/v1/gamification/${userId}`,
                {
                    id: 'gamify_mock',
                    user_id: userId,
                    level_info: {
                        level: 5,
                        current_xp: 450,
                        xp_to_next_level: 1000,
                        title: 'Budget Ninja',
                    },
                    total_xp: 4450,
                    badges: [],
                    challenges_completed: 2,
                    streak_days: 15,
                }
            );
        },

        addXp: async (userId: string, amount: number, reason: string) => {
            return ragCallApi(
                `/api/v1/gamification/${userId}/xp?amount=${amount}&reason=${encodeURIComponent(reason)}`,
                {
                    new_total_xp: 4450 + amount,
                    level_info: { level: 5, current_xp: 450 + amount, xp_to_next_level: 1000, title: 'Budget Ninja' },
                    leveled_up: false,
                    new_level: null,
                },
                { method: 'POST' }
            );
        },

        checkBadges: async (userId: string) => {
            return ragCallApi(
                `/api/v1/gamification/${userId}/check-badges`,
                { checked: 10, newly_unlocked: [], xp_earned: 0 },
                { method: 'POST' }
            );
        },

        getLeaderboard: async (userId: string, limit: number = 10) => {
            return ragCallApi(
                `/api/v1/gamification/leaderboard/${userId}?limit=${limit}`,
                {
                    leaderboard: [
                        { rank: 1, user_id: 'user_2', name: 'Aarav', total_xp: 6200, level: 7, is_current_user: false },
                        { rank: 2, user_id: 'user_3', name: 'Diya', total_xp: 5720, level: 6, is_current_user: false },
                        { rank: 3, user_id: userId, name: mockData.user.name, total_xp: 4450, level: 5, is_current_user: true },
                    ],
                    user_rank: { rank: 3, total_xp: 4450, level: 5 },
                }
            );
        },
    },

    health: async () => {
        return ragCallApi('/health', {
            status: 'healthy',
            version: '1.0.0-mock',
            database: 'mock',
            agent_available: true,
            ml_components: {},
        });
    },

    chat: {
        send: async (
            userId: string,
            query: string | { original_text: string; translated_text: string; language: string },
            sessionId?: string
        ): Promise<{
            response: string;
            session_id: string;
            confidence: number;
            context_used?: { episodic_count: number; semantic_count: number };
            memory_used?: Record<string, number>;
        }> => {
            const payload = typeof query === 'string'
                ? { user_id: userId, query, session_id: sessionId }
                : { user_id: userId, ...query, query: query.translated_text, session_id: sessionId };

            return ragCallApi(
                '/api/v1/chat',
                {
                    response: 'I am in mock mode. Please start the backend for real AI responses!',
                    session_id: 'mock_session',
                    confidence: 1,
                    context_used: { episodic_count: 0, semantic_count: 0 },
                    memory_used: {},
                },
                { method: 'POST', body: JSON.stringify(payload) }
            );
        },

        getHistory: async (userId: string): Promise<ChatMessage[]> => {
            return ragCallApi(
                `/api/v1/chat/history/${userId}`,
                mockData.chatHistory.map((message) => ({
                    id: message.id,
                    role: message.role as ChatMessage['role'],
                    content: message.content,
                    timestamp: message.timestamp,
                }))
            );
        },
    },

    translate: {
        text: async (text: string, targetLang: string = 'hi', sourceLang: string = 'auto'): Promise<TranslationResult> => {
            try {
                const encodedText = encodeURIComponent(text);
                const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=${sourceLang}&tl=${targetLang}&dt=t&q=${encodedText}`;
                const response = await fetch(url);
                if (!response.ok) throw new Error('Translation failed');
                const data = await response.json() as GoogleTranslateResponse;
                const translatedText = data[0]?.map((item) => item[0]).join('') || text;
                const detectedLanguage = data[2] || sourceLang;
                return { translatedText, detectedLanguage };
            } catch {
                return { translatedText: text, detectedLanguage: 'unknown' };
            }
        },

        languages: [
            { code: 'hi', name: 'Hindi' },
            { code: 'mr', name: 'Marathi' },
            { code: 'ta', name: 'Tamil' },
            { code: 'te', name: 'Telugu' },
            { code: 'bn', name: 'Bengali' },
            { code: 'gu', name: 'Gujarati' },
            { code: 'kn', name: 'Kannada' },
            { code: 'ml', name: 'Malayalam' },
            { code: 'pa', name: 'Punjabi' },
            { code: 'en', name: 'English' },
        ],
    },

    literacy: {
        getLesson: async (userId: string, topic: string, difficulty: 'beginner' | 'intermediate' | 'advanced' = 'beginner', sessionId: string) => {
            return callApi(
                '/api/v1/literacy/lesson',
                {
                    lesson: {
                        title: `${topic} Lesson`,
                        content: `This is a fallback lesson on ${topic}. Please connect to backend to get your personalized Phi-3 lesson.`,
                        key_points: ['Understand the basics', 'Apply to your life', 'Track your progress'],
                        personalized_example: "Based on data, you are doing well.",
                        estimated_minutes: 5,
                    },
                    quiz: {
                        questions: []
                    }
                },
                { method: 'POST', body: JSON.stringify({ user_id: userId, topic, difficulty, session_id: sessionId }) }
            );
        },
        saveQuizResult: async (userId: string, sessionId: string, score: number, total: number) => {
            return callApi(
                '/api/v1/literacy/quiz-result',
                { status: 'ok' },
                { method: 'POST', body: JSON.stringify({ user_id: userId, session_id: sessionId, score, total }) }
            );
        }
    },

    bills: {
        getAll: async (userId: string): Promise<Bill[]> =>
            ragCallApi<Bill[]>(`/api/v1/bills/${userId}`, []),

        create: async (userId: string, bill: Omit<Bill, 'id' | 'status' | 'days_until_due'>): Promise<{ status: string; bill: Bill }> =>
            ragCallApi(
                `/api/v1/bills/${userId}`,
                { status: 'created', bill: { ...bill, id: 'mock', status: 'upcoming', days_until_due: 7 } },
                { method: 'POST', body: JSON.stringify(bill) }
            ),

        delete: async (userId: string, billId: string): Promise<{ status: string }> =>
            ragCallApi(
                `/api/v1/bills/${userId}/${billId}`,
                { status: 'deleted' },
                { method: 'DELETE' }
            ),
    },

    tax: {
        get80C: async (userId: string): Promise<Tax80CData> =>
            ragCallApi<Tax80CData>(
                `/api/v1/tax/${userId}/80c`,
                {
                    fy: 'FY 2025-2026',
                    user_id: userId,
                    total_invested: 0,
                    eligible_amount: 0,
                    limit_80c: 150000,
                    remaining_limit: 150000,
                    percentage_used: 0,
                    slab_rate: 0.1,
                    tax_saved: 0,
                    potential_additional_saving: 15000,
                    breakdown: {},
                    recommendations: [
                        { instrument: 'ELSS', reason: 'Shortest lock-in, market-linked returns', potential_tax_saving: 15000 }
                    ]
                }
            ),
    },

    ocr: {
        scanReceipt: async (imageFile: File): Promise<OCRResult> => {
            const formData = new FormData();
            formData.append('image', imageFile);

            return callApi(
                '/api/v1/ocr/scan-receipt',
                { rawText: 'OCR service unavailable (Mock Mode)' },
                { method: 'POST', body: formData }
            );
        },

        extractAmount: (text: string): number | null => {
            const patterns = [
                /₹\s*([\d,]+(?:\.\d{2})?)/,
                /Rs\.?\s*([\d,]+(?:\.\d{2})?)/i,
                /INR\s*([\d,]+(?:\.\d{2})?)/i,
                /Total[:\s]*([\d,]+(?:\.\d{2})?)/i,
                /Amount[:\s]*([\d,]+(?:\.\d{2})?)/i,
            ];

            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match) {
                    return parseFloat(match[1].replace(/,/g, ''));
                }
            }

            return null;
        },
    },
};
