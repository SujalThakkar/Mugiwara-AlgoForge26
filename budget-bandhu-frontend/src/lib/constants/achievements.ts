export interface Badge {
    id: string;
    title: string;
    description: string;
    icon: string;
    color: string;
    xp: number;
    rarity: 'common' | 'rare' | 'epic' | 'legendary';
    category: 'budget' | 'savings' | 'investment' | 'subscription' | 'streak' | 'social';
    requirement: string;
    unlocked: boolean;
    unlockedAt?: string;
}

export const achievements: Badge[] = [
    {
        id: 'first_transaction',
        title: 'First Step',
        description: 'Added your first transaction',
        icon: '👣',
        color: '#10B981',
        xp: 50,
        rarity: 'common',
        category: 'budget',
        requirement: 'Add your first transaction',
        unlocked: true,
        unlockedAt: '2026-01-05',
    },
    {
        id: 'budget_ninja',
        title: 'Budget Ninja',
        description: 'Stayed under budget for one full month',
        icon: '🥷',
        color: '#3B82F6',
        xp: 150,
        rarity: 'rare',
        category: 'budget',
        requirement: 'Stay under budget for one month',
        unlocked: true,
        unlockedAt: '2026-02-01',
    },
    {
        id: 'savings_starter',
        title: 'Savings Starter',
        description: 'Saved money for 7 straight days',
        icon: '💰',
        color: '#10B981',
        xp: 150,
        rarity: 'common',
        category: 'savings',
        requirement: 'Save money daily for 7 days',
        unlocked: true,
        unlockedAt: '2026-02-10',
    },
    {
        id: 'goal_crusher',
        title: 'Goal Crusher',
        description: 'Completed your first financial goal',
        icon: '🎯',
        color: '#8B5CF6',
        xp: 500,
        rarity: 'epic',
        category: 'savings',
        requirement: 'Complete a goal',
        unlocked: false,
    },
    {
        id: 'investment_explorer',
        title: 'Investment Explorer',
        description: 'Made your first SIP investment',
        icon: '📈',
        color: '#F59E0B',
        xp: 200,
        rarity: 'rare',
        category: 'investment',
        requirement: 'Make your first SIP',
        unlocked: false,
    },
    {
        id: 'streak_master',
        title: 'Consistency King',
        description: 'Logged in 30 days in a row',
        icon: '🔥',
        color: '#EF4444',
        xp: 750,
        rarity: 'epic',
        category: 'streak',
        requirement: 'Maintain a 30 day streak',
        unlocked: false,
    },
];

export function getRarityColor(rarity: Badge['rarity']): string {
    switch (rarity) {
        case 'common':
            return '#64748B';
        case 'rare':
            return '#2563EB';
        case 'epic':
            return '#7C3AED';
        case 'legendary':
            return '#D97706';
        default:
            return '#64748B';
    }
}
