export interface Challenge {
    id: string;
    title: string;
    description: string;
    icon: string;
    color: string;
    xp: number;
    progress: number;
    target: number;
    deadline: string;
    active: boolean;
    completed: boolean;
}

export const weeklyChallenges: Challenge[] = [
    {
        id: 'save_500',
        title: 'Save Rs 500 This Week',
        description: 'Add Rs 500 to your savings by Sunday',
        icon: '💰',
        color: '#10B981',
        xp: 200,
        progress: 320,
        target: 500,
        deadline: '2026-04-05',
        active: true,
        completed: false,
    },
    {
        id: 'reduce_food_15',
        title: 'Reduce Food Spending',
        description: 'Spend 15% less on food this week',
        icon: '🍔',
        color: '#F59E0B',
        xp: 250,
        progress: 9,
        target: 15,
        deadline: '2026-04-05',
        active: true,
        completed: false,
    },
    {
        id: 'log_25_transactions',
        title: 'Log 25 Transactions',
        description: 'Keep your spending journal updated',
        icon: '📝',
        color: '#3B82F6',
        xp: 150,
        progress: 12,
        target: 25,
        deadline: '2026-04-05',
        active: true,
        completed: false,
    },
];
