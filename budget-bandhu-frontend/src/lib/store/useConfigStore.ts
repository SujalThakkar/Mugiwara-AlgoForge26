import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ConfigState {
    isMockMode: boolean;
    toggleMockMode: () => void;
    setMockMode: (enabled: boolean) => void;
}

export const useConfigStore = create<ConfigState>()(
    persist(
        (set) => ({
            isMockMode: true,
            toggleMockMode: () => set((state) => ({ isMockMode: !state.isMockMode })),
            setMockMode: (enabled) => set({ isMockMode: enabled }),
        }),
        {
            name: 'budget-bandhu-config',
        }
    )
);
