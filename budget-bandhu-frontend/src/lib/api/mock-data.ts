// mock-data.ts
export const mockData = {
    user: { name: '', email: '', monthlyIncome: 0 },
    dashboardSummary: { currentBalance: 0, monthSpent: 0, monthSaved: 0, savingsRate: 0, financialScore: 0 },
    budget: { totalIncome: 0, allocations: [] as any[], savingsTarget: 0, currentSavings: 0 },
    transactions: [] as any[],
    anomalies: [] as any[],
    insights: [] as any[],
    savingsForecast: { '30day': { predicted: 0, confidence: 0 } },
    spendingTrend: [] as any[],
    goals: [] as any[],
    chatHistory: [] as any[],
    tax: { maxLimit80C: 150000, investments: [] as any[] },
    financialHistory: { timelineStart: '2023-01', snapshots: [] as any[] }
};
