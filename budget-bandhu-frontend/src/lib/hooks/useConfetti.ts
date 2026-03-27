import { useCallback } from 'react';
import confetti from 'canvas-confetti';

export function useConfetti() {
    const fireConfetti = useCallback((options?: {
        particleCount?: number;
        spread?: number;
        origin?: { x?: number; y?: number };
        colors?: string[];
    }) => {
        confetti({
            particleCount: 150,
            spread: 70,
            origin: { y: 0.6 },
            colors: ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899'],
            ...options,
        });
    }, []);

    const fireCelebration = useCallback(() => {
        const count = 200;
        const defaults = {
            origin: { y: 0.7 },
            colors: ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899'],
        };

        const fire = (particleRatio: number, options: Record<string, unknown>) => {
            confetti({
                ...defaults,
                ...options,
                particleCount: Math.floor(count * particleRatio),
            });
        };

        fire(0.25, { spread: 26, startVelocity: 55 });
        fire(0.2, { spread: 60 });
        fire(0.35, { spread: 100, decay: 0.91, scalar: 0.8 });
        fire(0.1, { spread: 120, startVelocity: 25, decay: 0.92, scalar: 1.2 });
        fire(0.1, { spread: 120, startVelocity: 45 });
    }, []);

    return { fireConfetti, fireCelebration };
}
