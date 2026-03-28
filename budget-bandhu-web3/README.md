# Budget-Bandhu Web3

Smart contracts for BudgetBandhu — deployed on Polygon Amoy testnet.

## Contracts

| Contract | Purpose |
|---|---|
| `GoalBadgeSBT.sol` | Soulbound ERC-721 badge for all goal types |
| `GroupEscrow.sol` | Multi-party escrow pooling with refund |

## Setup

```bash
npm install
cp .env.example .env
# Fill in .env values
```

## Testing

```bash
npm test
```

## Deployment (step-by-step)

**Step 1: Deploy + test GoalBadgeSBT**
```bash
npm run deploy:sbt
```

**Step 2: Deploy GroupEscrow**
```bash
npm run deploy:escrow
```

## .env variables

```
DEPLOYER_PRIVATE_KEY=      # Your deployer wallet private key
AMOY_RPC_URL=              # https://rpc-amoy.polygon.technology (or Alchemy/Infura)
POLYGONSCAN_API_KEY=       # From polygonscan.com
VERIFIER_WALLET=           # Backend wallet address to grant verifier role
```

## After Deployment

Copy the deployed addresses to:
- `budget-bandhu-web3/deployments/amoy.json`
- `budget-bandhu-frontend/src/lib/contracts/config.ts`
- `budget-bandhu-rag/.env` (for backend minting)
