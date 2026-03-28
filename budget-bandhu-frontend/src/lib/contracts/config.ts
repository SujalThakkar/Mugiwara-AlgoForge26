/**
 * lib/contracts/config.ts
 * Contract addresses and chain config for Polygon Amoy.
 * Update addresses after deployment.
 */

export const AMOY_CHAIN_ID = 80002;

export const CONTRACT_ADDRESSES = {
  GoalBadgeSBT: process.env.NEXT_PUBLIC_SBT_ADDRESS || "",
  GroupEscrow:  process.env.NEXT_PUBLIC_ESCROW_ADDRESS || "",
};

export const AMOY_RPC = "https://rpc-amoy.polygon.technology";

export const AMOY_CHAIN_CONFIG = {
  chainId:          `0x${AMOY_CHAIN_ID.toString(16)}`,
  chainName:        "Polygon Amoy Testnet",
  nativeCurrency:   { name: "POL", symbol: "POL", decimals: 18 },
  rpcUrls:          [AMOY_RPC],
  blockExplorerUrls: ["https://amoy.polygonscan.com"],
};

export const POLYGONSCAN_BASE = "https://amoy.polygonscan.com";
