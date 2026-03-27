import { format, subDays } from 'date-fns';

const baseTransactions = [
    { merchant: 'SWIGGY FOOD ORDER', amount: 450, category: 'Food & Dining', type: 'debit' as const },
    { merchant: 'OLA CABS RIDE', amount: 180, category: 'Transport', type: 'debit' as const },
    { merchant: 'SALARY CREDIT', amount: 50000, category: 'Income', type: 'credit' as const },
    { merchant: 'AMAZON SHOPPING', amount: 2340, category: 'Shopping', type: 'debit' as const },
    { merchant: 'NETFLIX SUBSCRIPTION', amount: 649, category: 'Entertainment', type: 'debit' as const },
    { merchant: 'BIGBASKET ORDER', amount: 1280, category: 'Groceries', type: 'debit' as const },
    { merchant: 'ELECTRICITY BILL', amount: 2140, category: 'Bills & Utilities', type: 'debit' as const },
    { merchant: 'PHARMACY', amount: 780, category: 'Healthcare', type: 'debit' as const },
    { merchant: 'ZERODHA SIP', amount: 5000, category: 'Investments', type: 'debit' as const },
    { merchant: 'UNKNOWN CHARGE', amount: 15000, category: 'Others', type: 'debit' as const },
];

const transactions = Array.from({ length: 24 }, (_, index) => {
    const template = baseTransactions[index % baseTransactions.length];
    return {
        id: `txn_${String(index + 1).padStart(3, '0')}`,
        date: format(subDays(new Date(), index), 'yyyy-MM-dd'),
        merchant: template.merchant,
        amount: template.amount + (index % 3) * 75,
        category: template.category,
        type: template.type,
        balance: 65000 - index * 1100,
        notes: '',
        isAnomaly: template.merchant === 'UNKNOWN CHARGE',
        receipt: null,
    };
});

export const mockData = {
    user: {
        id: 'user_1',
        name: 'Aryan Lomte',
        email: 'aryan@example.com',
        avatar: '/avatars/aryan.jpg',
        monthlyIncome: 50000,
        createdAt: '2026-01-15T00:00:00Z',
        preferences: {
            currency: 'INR',
            language: 'en',
            notifications: true,
        },
    },

    dashboardSummary: {
        currentBalance: 42340,
        monthSpent: 28650,
        monthSaved: 21350,
        savingsRate: 0.427,
        budgetAdherence: 0.89,
        financialScore: 782,
        trend: {
            balance: '+12%',
            spending: '-8%',
            savings: '+15%',
        },
    },

    spendingTrend: Array.from({ length: 30 }, (_, index) => ({
        date: format(subDays(new Date(), 29 - index), 'dd MMM'),
        amount: 2200 + ((index * 431) % 4200),
    })),

    transactions,

    anomalies: transactions.filter((transaction) => transaction.isAnomaly),

    budget: {
        totalIncome: 50000,
        allocations: [
            { category: 'Food & Dining', allocated: 8000, spent: 6540, percentage: 16 },
            { category: 'Transport', allocated: 3000, spent: 2890, percentage: 6 },
            { category: 'Shopping', allocated: 5000, spent: 5420, percentage: 10 },
            { category: 'Bills & Utilities', allocated: 6000, spent: 5800, percentage: 12 },
            { category: 'Entertainment', allocated: 2000, spent: 1650, percentage: 4 },
            { category: 'Groceries', allocated: 4000, spent: 3780, percentage: 8 },
            { category: 'Healthcare', allocated: 2000, spent: 890, percentage: 4 },
            { category: 'Investments', allocated: 5000, spent: 5000, percentage: 10 },
            { category: 'Others', allocated: 2000, spent: 680, percentage: 4 },
        ],
        savingsTarget: 10000,
        currentSavings: 21350,
    },

    goals: [
        {
            id: 'goal_001',
            name: 'Emergency Fund',
            icon: '🛡️',
            target: 150000,
            current: 67500,
            deadline: '2026-12-31',
            priority: 'high',
            color: '#10B981',
            milestones: [
                { amount: 50000, reached: true, date: '2026-02-15' },
                { amount: 100000, reached: false, date: null },
                { amount: 150000, reached: false, date: null },
            ],
        },
        {
            id: 'goal_002',
            name: 'Europe Trip',
            icon: '✈️',
            target: 200000,
            current: 45000,
            deadline: '2027-06-30',
            priority: 'medium',
            color: '#3B82F6',
            milestones: [],
        },
        {
            id: 'goal_003',
            name: 'New Laptop',
            icon: '💻',
            target: 120000,
            current: 92000,
            deadline: '2026-09-30',
            priority: 'high',
            color: '#8B5CF6',
            milestones: [],
        },
    ],

    savingsForecast: {
        '7day': { predicted: 22450, confidence: 0.91, trend: 'up', change: 1100 },
        '30day': { predicted: 28900, confidence: 0.87, trend: 'up', change: 7550 },
        '90day': { predicted: 45600, confidence: 0.74, trend: 'up', change: 24250 },
    },

    insights: [
        {
            id: 'insight_001',
            type: 'spending_spike',
            title: 'Shopping increased 40% this week',
            description: 'You spent more on shopping than usual. Consider delaying non-essential purchases.',
            severity: 'warning',
            icon: '⚠️',
            date: format(new Date(), 'yyyy-MM-dd'),
        },
        {
            id: 'insight_002',
            type: 'savings_up',
            title: 'Savings are trending up',
            description: 'You saved 15% more this month than last month.',
            severity: 'success',
            icon: '✨',
            date: format(subDays(new Date(), 1), 'yyyy-MM-dd'),
        },
        {
            id: 'insight_003',
            type: 'anomaly_detected',
            title: 'Unusual transaction detected',
            description: 'One large transaction looks different from your usual pattern.',
            severity: 'error',
            icon: '🚨',
            date: format(subDays(new Date(), 2), 'yyyy-MM-dd'),
        },
    ],

    financialHistory: {
        month: {
            period: 'This Month',
            label: 'Last Month',
            current: { income: 50000, expenses: 28650, savings: 21350, balance: 42340 },
            past: { income: 50000, expenses: 31400, savings: 18600, balance: 37210 },
        },
        quarter: {
            period: 'This Quarter',
            label: 'Previous Quarter',
            current: { income: 150000, expenses: 82200, savings: 67800, balance: 126500 },
            past: { income: 150000, expenses: 90150, savings: 59850, balance: 110400 },
        },
        year: {
            period: 'This Year',
            label: 'Last Year',
            current: { income: 600000, expenses: 336000, savings: 264000, balance: 423400 },
            past: { income: 540000, expenses: 348000, savings: 192000, balance: 367900 },
        },
    },

    tax: {
        maxLimit80C: 150000,
        investments: [
            {
                id: 'tax_001',
                category: 'PPF',
                amount: 45000,
                limit: 150000,
                description: 'Public Provident Fund contribution',
            },
            {
                id: 'tax_002',
                category: 'ELSS',
                amount: 30000,
                limit: 150000,
                description: 'ELSS mutual fund contribution',
            },
            {
                id: 'tax_003',
                category: 'Life Insurance',
                amount: 25000,
                limit: 150000,
                description: 'Annual life insurance premium',
            },
        ],
    },

    chatHistory: [
        {
            id: 'chat_001',
            role: 'assistant',
            content: 'Hi! I can help you understand your budget, goals, and spending patterns.',
            timestamp: new Date().toISOString(),
        },
    ],
};
