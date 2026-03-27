import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { User, mlApi } from '../api/ml-api';

interface UserState {
    userId: string | null;
    user: User | null;
    isLoggedIn: boolean;
    isLoading: boolean;
    setUser: (user: User) => void;
    login: (mobile_number: string, password: string) => Promise<boolean>;
    register: (data: { name: string; mobile_number: string; password: string; income?: number }) => Promise<boolean>;
    logout: () => void;
    refreshUser: () => Promise<void>;
}

type PersistedUserState = Pick<UserState, 'userId' | 'isLoggedIn'>;

export const useUserStore = create<UserState>()(
    persist(
        (set, get) => ({
            userId: null,
            user: null,
            isLoggedIn: false,
            isLoading: false,

            setUser: (user) => set({
                user,
                userId: user.id,
                isLoggedIn: true,
            }),

            login: async (mobile_number, password) => {
                set({ isLoading: true });
                try {
                    const result = await mlApi.user.login(mobile_number, password);
                    set({
                        user: result.user,
                        userId: result.user.id,
                        isLoggedIn: true,
                        isLoading: false,
                    });
                    return true;
                } catch (error) {
                    console.error('[UserStore] Login failed:', error);
                    set({ isLoading: false });
                    return false;
                }
            },

            register: async (data) => {
                set({ isLoading: true });
                try {
                    const user = await mlApi.user.register(data);
                    set({
                        user,
                        userId: user.id,
                        isLoggedIn: true,
                        isLoading: false,
                    });
                    return true;
                } catch (error) {
                    console.error('[UserStore] Register failed:', error);
                    set({ isLoading: false });
                    return false;
                }
            },

            logout: () => set({
                user: null,
                userId: null,
                isLoggedIn: false,
            }),

            refreshUser: async () => {
                const { userId } = get();
                if (!userId) {
                    return;
                }

                try {
                    const user = await mlApi.user.getProfile(userId);
                    set({ user });
                } catch (error) {
                    console.error('[UserStore] Refresh failed:', error);
                }
            },
        }),
        {
            name: 'budgetbandhu-user',
            partialize: (state) => ({
                userId: state.userId,
                isLoggedIn: state.isLoggedIn,
            }),
            version: 2,
            migrate: (persistedState) => {
                if (!persistedState || typeof persistedState !== 'object') {
                    return {
                        userId: null,
                        isLoggedIn: false,
                    } satisfies PersistedUserState;
                }

                const state = persistedState as Partial<PersistedUserState>;

                return {
                    userId: state.userId ?? null,
                    isLoggedIn: state.isLoggedIn ?? false,
                } satisfies PersistedUserState;
            },
        }
    )
);
