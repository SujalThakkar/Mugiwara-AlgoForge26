/**
 * lib/contracts/abis.ts
 * Minimal ABIs for GoalBadgeSBT and GroupEscrow — only functions used by frontend.
 */

export const GOAL_BADGE_SBT_ABI = [
  // Read
  {
    inputs:  [{ internalType: "uint256", name: "tokenId", type: "uint256" }],
    name:    "tokenURI",
    outputs: [{ internalType: "string", name: "", type: "string" }],
    stateMutability: "view",
    type:    "function",
  },
  {
    inputs:  [{ internalType: "uint256", name: "tokenId", type: "uint256" }],
    name:    "ownerOf",
    outputs: [{ internalType: "address", name: "", type: "address" }],
    stateMutability: "view",
    type:    "function",
  },
  {
    inputs:  [],
    name:    "nextTokenId",
    outputs: [{ internalType: "uint256", name: "", type: "uint256" }],
    stateMutability: "view",
    type:    "function",
  },
  {
    inputs:  [{ internalType: "address", name: "owner", type: "address" }],
    name:    "balanceOf",
    outputs: [{ internalType: "uint256", name: "", type: "uint256" }],
    stateMutability: "view",
    type:    "function",
  },
  // Events
  {
    anonymous: false,
    inputs: [
      { indexed: true,  internalType: "address", name: "recipient",  type: "address" },
      { indexed: true,  internalType: "uint256", name: "tokenId",    type: "uint256" },
      { indexed: false, internalType: "string",  name: "goalTitle",  type: "string"  },
    ],
    name: "BadgeMinted",
    type: "event",
  },
] as const;

export const GROUP_ESCROW_ABI = [
  // Write
  {
    inputs: [
      { internalType: "uint256", name: "target",     type: "uint256" },
      { internalType: "uint256", name: "deadline",   type: "uint256" },
      { internalType: "uint8",   name: "maxMembers", type: "uint8"   },
    ],
    name:    "createPool",
    outputs: [{ internalType: "uint256", name: "poolId", type: "uint256" }],
    stateMutability: "nonpayable",
    type:    "function",
  },
  {
    inputs:  [{ internalType: "uint256", name: "poolId", type: "uint256" }],
    name:    "contribute",
    outputs: [],
    stateMutability: "payable",
    type:    "function",
  },
  {
    inputs:  [{ internalType: "uint256", name: "poolId", type: "uint256" }],
    name:    "completePool",
    outputs: [],
    stateMutability: "nonpayable",
    type:    "function",
  },
  {
    inputs:  [{ internalType: "uint256", name: "poolId", type: "uint256" }],
    name:    "refund",
    outputs: [],
    stateMutability: "nonpayable",
    type:    "function",
  },
  // Read
  {
    inputs:  [{ internalType: "uint256", name: "poolId", type: "uint256" }],
    name:    "getPool",
    outputs: [
      { internalType: "address", name: "creator",     type: "address" },
      { internalType: "uint256", name: "target",      type: "uint256" },
      { internalType: "uint256", name: "deadline",    type: "uint256" },
      { internalType: "uint256", name: "totalFunded", type: "uint256" },
      { internalType: "uint8",   name: "maxMembers",  type: "uint8"   },
      { internalType: "uint8",   name: "memberCount", type: "uint8"   },
      { internalType: "bool",    name: "completed",   type: "bool"    },
    ],
    stateMutability: "view",
    type:    "function",
  },
  {
    inputs: [
      { internalType: "uint256", name: "poolId", type: "uint256" },
      { internalType: "address", name: "user",   type: "address" },
    ],
    name:    "getContribution",
    outputs: [{ internalType: "uint256", name: "", type: "uint256" }],
    stateMutability: "view",
    type:    "function",
  },
  {
    inputs: [
      { internalType: "uint256", name: "poolId", type: "uint256" },
      { internalType: "address", name: "user",   type: "address" },
    ],
    name:    "isPoolMember",
    outputs: [{ internalType: "bool", name: "", type: "bool" }],
    stateMutability: "view",
    type:    "function",
  },
  // Events
  {
    anonymous: false,
    inputs: [
      { indexed: true,  internalType: "uint256", name: "poolId",     type: "uint256" },
      { indexed: true,  internalType: "address", name: "contributor", type: "address" },
      { indexed: false, internalType: "uint256", name: "amount",     type: "uint256" },
      { indexed: false, internalType: "uint256", name: "newTotal",   type: "uint256" },
    ],
    name: "Contributed",
    type: "event",
  },
  {
    anonymous: false,
    inputs: [
      { indexed: true,  internalType: "uint256", name: "poolId",   type: "uint256" },
      { indexed: true,  internalType: "address", name: "creator",  type: "address" },
      { indexed: false, internalType: "uint256", name: "totalAmount", type: "uint256" },
    ],
    name: "PoolCompleted",
    type: "event",
  },
] as const;
