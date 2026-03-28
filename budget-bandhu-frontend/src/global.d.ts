/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * Global type declarations for Budget Bandhu.
 * Extends Window with MetaMask's ethereum provider.
 */

interface Window {
  ethereum?: {
    request: (args: { method: string; params?: any[] }) => Promise<any>;
    on?: (event: string, handler: (...args: any[]) => void) => void;
    removeListener?: (event: string, handler: (...args: any[]) => void) => void;
    isMetaMask?: boolean;
  };
}
