import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { achievements, Badge } from '@/lib/constants/achievements';
import { weeklyChallenges, Challenge } from '@/lib/constants/challenges';
import { calculateLevel, UserLevel } from '@/lib/utils/gamification';

interface GamificationState {
    totalXP: number;
    level: UserLevel;
    badges: Badge[];
    challenges: Challenge[];
    recentUnlocks: Badge[];
    addXP: (amount: number, reason: string) => void;
    unlockBadge: (badgeId: string) => void;
    updateChallengeProgress: (challengeId: string, progress: number) => void;
    clearRecentUnlocks: () => void;
}

export const useGamificationStore = create<GamificationState>()(
    persist(
        (set, get) => ({
            totalXP: 2340,
            level: calculateLevel(2340),
            badges: achievements,
            challenges: weeklyChallenges,
            recentUnlocks: [],

            addXP: (amount) => {
                const totalXP = get().totalXP + amount;
                set({
                    totalXP,
                    level: calculateLevel(totalXP),
                });
            },

            unlockBadge: (badgeId) => {
                const badges = get().badges.map((badge) =>
                    badge.id === badgeId
                        ? { ...badge, unlocked: true, unlockedAt: new Date().toISOString() }
                        : badge
                );
                const unlockedBadge = badges.find((badge) => badge.id === badgeId);

                set({
                    badges,
                    recentUnlocks: unlockedBadge ? [...get().recentUnlocks, unlockedBadge] : get().recentUnlocks,
                });

                if (unlockedBadge) {
                    get().addXP(unlockedBadge.xp, `Unlocked ${unlockedBadge.title}`);
                }
            },

            updateChallengeProgress: (challengeId, progress) => {
                set({
                    challenges: get().challenges.map((challenge) =>
                        challenge.id === challengeId
                            ? { ...challenge, progress, completed: progress >= challenge.target }
                            : challenge
                    ),
                });
            },

            clearRecentUnlocks: () => set({ recentUnlocks: [] }),
        }),
        {
            name: 'budget-bandhu-gamification',
        }
    )
);
