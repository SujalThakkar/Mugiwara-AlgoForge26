import { ethers } from 'ethers';

export type WalletStatus =
    | 'checking'
    | 'ready'
    | 'connecting'
    | 'connected'
    | 'disconnecting'
    | 'unavailable'
    | 'error';

export interface WalletProviderInfo {
    uuid: string;
    name: string;
    icon: string;
    rdns: string;
}

export interface MetaMaskProvider extends ethers.Eip1193Provider {
    isMetaMask?: boolean;
    providers?: MetaMaskProvider[];
    request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
    on?: (event: string, listener: (...args: unknown[]) => void) => void;
    removeListener?: (event: string, listener: (...args: unknown[]) => void) => void;
}

export interface MetaMaskProviderDetail {
    info: WalletProviderInfo;
    provider: MetaMaskProvider;
}

interface ProviderRpcError extends Error {
    code?: number;
}

interface AnnounceProviderEvent extends CustomEvent<MetaMaskProviderDetail> {
    type: 'eip6963:announceProvider';
}

type EthereumWindow = Window & {
    ethereum?: MetaMaskProvider;
};

const REQUEST_PROVIDER_EVENT = 'eip6963:requestProvider';
const ANNOUNCE_PROVIDER_EVENT = 'eip6963:announceProvider';

const META_MASK_FALLBACK_INFO: WalletProviderInfo = {
    uuid: 'legacy-metamask',
    name: 'MetaMask',
    icon: '',
    rdns: 'io.metamask',
};

const ACCOUNT_PERMISSION = { eth_accounts: {} };

const getBrowserWindow = (): EthereumWindow | null => (
    typeof window === 'undefined' ? null : (window as EthereumWindow)
);

const isMetaMaskProvider = (provider: MetaMaskProvider | null | undefined): provider is MetaMaskProvider => {
    if (!provider) {
        return false;
    }

    return provider.isMetaMask === true;
};

const isMetaMaskDetail = (detail: MetaMaskProviderDetail | null | undefined): detail is MetaMaskProviderDetail => {
    if (!detail) {
        return false;
    }

    return (
        isMetaMaskProvider(detail.provider) ||
        detail.info.rdns.toLowerCase().includes('metamask') ||
        detail.info.name.toLowerCase().includes('metamask')
    );
};

const getLegacyMetaMaskProvider = (): MetaMaskProviderDetail | null => {
    const browserWindow = getBrowserWindow();
    const injectedProvider = browserWindow?.ethereum;

    if (!injectedProvider) {
        return null;
    }

    if (Array.isArray(injectedProvider.providers)) {
        const nestedProvider = injectedProvider.providers.find((provider) => provider.isMetaMask);
        if (nestedProvider) {
            return {
                info: META_MASK_FALLBACK_INFO,
                provider: nestedProvider,
            };
        }
    }

    if (!isMetaMaskProvider(injectedProvider)) {
        return null;
    }

    return {
        info: META_MASK_FALLBACK_INFO,
        provider: injectedProvider,
    };
};

const normalizeAddress = (value: unknown): string | null => {
    if (typeof value !== 'string' || value.length === 0) {
        return null;
    }

    try {
        return ethers.getAddress(value);
    } catch {
        return value;
    }
};

const normalizeAccounts = (value: unknown): string[] => {
    if (!Array.isArray(value)) {
        return [];
    }

    return value
        .map((account) => normalizeAddress(account))
        .filter((account): account is string => account !== null);
};

const getProviderErrorMessage = (error: unknown): string => {
    const providerError = error as ProviderRpcError | undefined;

    switch (providerError?.code) {
        case 4001:
            return 'MetaMask connection request was rejected.';
        case -32002:
            return 'A MetaMask connection request is already pending.';
        default:
            return 'Could not complete the MetaMask request.';
    }
};

export const discoverMetaMaskProvider = async (): Promise<MetaMaskProviderDetail | null> => {
    const browserWindow = getBrowserWindow();

    if (!browserWindow) {
        return null;
    }

    return new Promise((resolve) => {
        const providers = new Map<string, MetaMaskProviderDetail>();
        let settled = false;

        const settle = (detail: MetaMaskProviderDetail | null) => {
            if (settled) {
                return;
            }

            settled = true;
            browserWindow.removeEventListener(ANNOUNCE_PROVIDER_EVENT, handleAnnouncement as EventListener);
            resolve(detail);
        };

        const selectProvider = () => {
            const discoveredProvider = Array.from(providers.values()).find((detail) => isMetaMaskDetail(detail));
            return discoveredProvider ?? getLegacyMetaMaskProvider();
        };

        const handleAnnouncement = (event: Event) => {
            const providerEvent = event as AnnounceProviderEvent;
            if (!providerEvent.detail?.provider || !providerEvent.detail?.info) {
                return;
            }

            providers.set(providerEvent.detail.info.uuid, providerEvent.detail);

            const detail = selectProvider();
            if (detail) {
                settle(detail);
            }
        };

        browserWindow.addEventListener(ANNOUNCE_PROVIDER_EVENT, handleAnnouncement as EventListener);
        browserWindow.dispatchEvent(new Event(REQUEST_PROVIDER_EVENT));

        browserWindow.setTimeout(() => {
            settle(selectProvider());
        }, 250);
    });
};

export const requestWalletConnection = async (provider: MetaMaskProvider): Promise<string | null> => {
    const accounts = await provider.request({ method: 'eth_requestAccounts' });
    return normalizeAccounts(accounts)[0] ?? null;
};

export const revokeWalletConnection = async (provider: MetaMaskProvider): Promise<void> => {
    await provider.request({
        method: 'wallet_revokePermissions',
        params: [ACCOUNT_PERMISSION],
    });
};

export const getWalletBalance = async (provider: MetaMaskProvider, address: string): Promise<string> => {
    const browserProvider = new ethers.BrowserProvider(provider);
    const balance = await browserProvider.getBalance(address);
    return ethers.formatEther(balance);
};

export const subscribeToMetaMaskEvents = (
    provider: MetaMaskProvider,
    callbacks: {
        onAccountsChanged?: (accounts: string[]) => void;
        onDisconnect?: () => void;
    }
): (() => void) => {
    const handleAccountsChanged = (accounts: unknown) => {
        callbacks.onAccountsChanged?.(normalizeAccounts(accounts));
    };

    const handleDisconnect = () => {
        callbacks.onDisconnect?.();
    };

    provider.on?.('accountsChanged', handleAccountsChanged);
    provider.on?.('disconnect', handleDisconnect);

    return () => {
        provider.removeListener?.('accountsChanged', handleAccountsChanged);
        provider.removeListener?.('disconnect', handleDisconnect);
    };
};

export const formatCryptoBalance = (balance: string | number): string => {
    const numericBalance = typeof balance === 'string' ? parseFloat(balance) : balance;
    return Number.isFinite(numericBalance) ? numericBalance.toFixed(4) : '0.0000';
};

export const getMetaMaskErrorMessage = (error: unknown): string => getProviderErrorMessage(error);
