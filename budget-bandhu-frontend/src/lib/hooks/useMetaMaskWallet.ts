'use client';

import { useEffect, useState } from 'react';
import {
    discoverMetaMaskProvider,
    getMetaMaskErrorMessage,
    requestWalletConnection,
    revokeWalletConnection,
    subscribeToMetaMaskEvents,
    type MetaMaskProviderDetail,
    type WalletStatus,
} from '@/lib/wallet/metamask';

interface MetaMaskWalletState {
    address: string | null;
    status: WalletStatus;
    error: string | null;
    walletName: string;
    isAvailable: boolean;
    isConnected: boolean;
    connect: () => Promise<void>;
    disconnect: () => Promise<void>;
}

export const useMetaMaskWallet = (): MetaMaskWalletState => {
    const [providerDetail, setProviderDetail] = useState<MetaMaskProviderDetail | null>(null);
    const [address, setAddress] = useState<string | null>(null);
    const [status, setStatus] = useState<WalletStatus>('checking');
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isActive = true;

        const loadProvider = async () => {
            const detail = await discoverMetaMaskProvider();

            if (!isActive) {
                return;
            }

            if (!detail) {
                setProviderDetail(null);
                setStatus('unavailable');
                return;
            }

            setProviderDetail(detail);
            setStatus('ready');
        };

        void loadProvider();

        return () => {
            isActive = false;
        };
    }, []);

    useEffect(() => {
        if (!providerDetail) {
            return;
        }

        return subscribeToMetaMaskEvents(providerDetail.provider, {
            onAccountsChanged: (accounts) => {
                const nextAddress = accounts[0] ?? null;
                setError(null);

                if (!nextAddress) {
                    setAddress(null);
                    setStatus('ready');
                    return;
                }

                setAddress(nextAddress);
                setStatus('connected');
            },
            onDisconnect: () => {
                setAddress(null);
                setError(null);
                setStatus('ready');
            },
        });
    }, [providerDetail]);

    const connect = async () => {
        setError(null);
        setStatus('connecting');

        try {
            const detail = providerDetail ?? await discoverMetaMaskProvider();

            if (!detail) {
                setProviderDetail(null);
                setStatus('unavailable');
                setError('MetaMask was not detected in this browser.');
                return;
            }

            if (!providerDetail) {
                setProviderDetail(detail);
            }

            const connectedAddress = await requestWalletConnection(detail.provider);

            if (!connectedAddress) {
                setAddress(null);
                setStatus('ready');
                return;
            }

            setAddress(connectedAddress);
            setStatus('connected');
        } catch (nextError) {
            setAddress(null);
            setStatus(providerDetail ? 'ready' : 'error');
            setError(getMetaMaskErrorMessage(nextError));
        }
    };

    const disconnect = async () => {
        setError(null);
        setStatus('disconnecting');

        try {
            if (providerDetail) {
                await revokeWalletConnection(providerDetail.provider);
            }
        } catch (nextError) {
            console.warn('[MetaMask] Could not revoke wallet permissions:', nextError);
        } finally {
            setAddress(null);
            setStatus(providerDetail ? 'ready' : 'unavailable');
        }
    };

    return {
        address,
        status,
        error,
        walletName: providerDetail?.info.name ?? 'MetaMask',
        isAvailable: providerDetail !== null,
        isConnected: address !== null,
        connect,
        disconnect,
    };
};
