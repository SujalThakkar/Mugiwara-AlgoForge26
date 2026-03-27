'use client';

import { toast } from 'react-hot-toast';
import { useGamificationStore } from '@/lib/store/useGamificationStore';

export function useXPTriggers() {
    const { addXP } = useGamificationStore();

    const onGoalContribution = (amount: number) => {
        const xp = Math.min(Math.floor(amount / 1000), 50);
        if (xp > 0) {
            addXP(xp, 'Goal contribution');
            toast.success(`+${xp} XP for contributing to your goal!`);
        }
    };

    const onGoalCompleted = () => {
        const xp = 100;
        addXP(xp, 'Goal completed');
        toast.success(`+${xp} XP for completing a goal!`);
    };

    const onTransactionCreated = () => {
        const xp = 10;
        addXP(xp, 'Transaction logged');
        toast.success(`+${xp} XP for logging a transaction!`);
    };

    return {
        onGoalContribution,
        onGoalCompleted,
        onTransactionCreated,
    };
}
