"use client";
/**
 * lib/hooks/useEscrowPool.ts
 * React hook for interacting with GroupEscrow.sol via ethers.js + MetaMask.
 */

import { useState, useCallback } from "react";
import { ethers } from "ethers";
import { CONTRACT_ADDRESSES, AMOY_CHAIN_CONFIG, AMOY_CHAIN_ID, POLYGONSCAN_BASE } from "@/lib/contracts/config";
import { GROUP_ESCROW_ABI } from "@/lib/contracts/abis";

export interface PoolInfo {
  creator:     string;
  target:      bigint;
  deadline:    bigint;
  totalFunded: bigint;
  maxMembers:  number;
  memberCount: number;
  completed:   boolean;
}

export function useEscrowPool() {
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [txHash,   setTxHash]   = useState<string | null>(null);

  const _getSigner = async () => {
    if (typeof window === "undefined" || !window.ethereum)
      throw new Error("MetaMask not found");

    const provider = new ethers.BrowserProvider(window.ethereum);

    // Switch to Amoy if needed
    const network = await provider.getNetwork();
    if (Number(network.chainId) !== AMOY_CHAIN_ID) {
      try {
        await window.ethereum.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: AMOY_CHAIN_CONFIG.chainId }],
        });
      } catch (switchErr: any) {
        // Chain not added yet — add it
        if (switchErr.code === 4902) {
          await window.ethereum.request({
            method: "wallet_addEthereumChain",
            params: [AMOY_CHAIN_CONFIG],
          });
        } else {
          throw switchErr;
        }
      }
    }

    await provider.send("eth_requestAccounts", []);
    return provider.getSigner();
  };

  const _getContract = async (readOnly = false) => {
    const address = CONTRACT_ADDRESSES.GroupEscrow;
    if (!address) throw new Error("GroupEscrow address not configured");

    if (readOnly) {
      const provider = new ethers.JsonRpcProvider(AMOY_CHAIN_CONFIG.rpcUrls[0]);
      return new ethers.Contract(address, GROUP_ESCROW_ABI, provider);
    }
    const signer = await _getSigner();
    return new ethers.Contract(address, GROUP_ESCROW_ABI, signer);
  };

  /**
   * Create a new escrow pool on-chain.
   * Returns the on-chain poolId (uint256) for linking to backend.
   */
  const createPool = useCallback(async (
    targetPOL:  string,   // e.g. "5.0"
    deadline:   number,   // unix timestamp
    maxMembers: number,
  ): Promise<bigint | null> => {
    setLoading(true); setError(null); setTxHash(null);
    try {
      const contract  = await _getContract();
      const targetWei = ethers.parseEther(targetPOL);
      const tx        = await (contract as any).createPool(targetWei, deadline, maxMembers);
      setTxHash(tx.hash);
      const receipt = await tx.wait();
      // Parse PoolCreated event to get poolId
      const event = receipt.logs
        .map((log: any) => { try { return contract.interface.parseLog(log); } catch { return null; } })
        .find((e: any) => e?.name === "PoolCreated");
      return event ? event.args.poolId as bigint : null;
    } catch (e: any) {
      setError(e.message || "createPool failed");
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Contribute POL to a pool (auto-joins on first contribution).
   */
  const contribute = useCallback(async (poolId: bigint, amountPOL: string): Promise<boolean> => {
    setLoading(true); setError(null); setTxHash(null);
    try {
      const contract = await _getContract();
      const tx = await (contract as any).contribute(poolId, {
        value: ethers.parseEther(amountPOL),
      });
      setTxHash(tx.hash);
      await tx.wait();
      return true;
    } catch (e: any) {
      setError(e.message || "contribute failed");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Creator calls completePool when total >= target.
   * After this succeeds, call backend /api/v1/escrow/{id}/complete to mint SBTs.
   */
  const completePool = useCallback(async (poolId: bigint): Promise<boolean> => {
    setLoading(true); setError(null); setTxHash(null);
    try {
      const contract = await _getContract();
      const tx = await (contract as any).completePool(poolId);
      setTxHash(tx.hash);
      await tx.wait();
      return true;
    } catch (e: any) {
      setError(e.message || "completePool failed");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * User refunds their contribution after deadline (if pool incomplete).
   */
  const refund = useCallback(async (poolId: bigint): Promise<boolean> => {
    setLoading(true); setError(null); setTxHash(null);
    try {
      const contract = await _getContract();
      const tx = await (contract as any).refund(poolId);
      setTxHash(tx.hash);
      await tx.wait();
      return true;
    } catch (e: any) {
      setError(e.message || "refund failed");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Read pool state from chain.
   */
  const getPoolOnChain = useCallback(async (poolId: bigint): Promise<PoolInfo | null> => {
    try {
      const contract = await _getContract(true);
      const [creator, target, deadline, totalFunded, maxMembers, memberCount, completed]
        = await (contract as any).getPool(poolId);
      return { creator, target, deadline, totalFunded, maxMembers, memberCount, completed };
    } catch (e: any) {
      return null;
    }
  }, []);

  const polygonscanTx = (hash: string) => `${POLYGONSCAN_BASE}/tx/${hash}`;

  return {
    loading, error, txHash,
    createPool, contribute, completePool, refund, getPoolOnChain,
    polygonscanTx,
  };
}
