# Budget-Bandhu Goals 2.0 — Full Technical Context

> **Last updated:** 2026-03-28 23:52 IST
> **Purpose:** Complete context of the Web3 Goals 2.0 implementation. Use this file to onboard into a new chat session. Covers architecture, all deployed contracts, backend/frontend changes, tested flows, and remaining work.

---

## 🔥 CORE ARCHITECTURE

- **Backend (`budget-bandhu-rag/`)** = brain (all logic, ML forecasting, CSV processing, IPFS badge generation, SBT minting orchestration)
- **Blockchain** = proof + money only (SBT badges for achievement proof, GroupEscrow for crypto pooling)
- **Frontend (`budget-bandhu-frontend/`)** = Next.js 16.1 with MetaMask wallet integration
- **Smart Contracts (`budget-bandhu-web3/`)** = Hardhat, OpenZeppelin v5, Polygon Amoy testnet

---

## ✅ DEPLOYED CONTRACTS

### GoalBadgeSBT (ERC-721 SBT)

- **Address:** `0xB9b2550d61deB460168182fC68F99c6636727788`
- **Network:** Polygon Amoy Testnet
- **Deployer:** `0x0C811D28046a77FA27A3CaF089E79DC664CF8178`
- **Verifier (backend wallet):** `0x35C98a0033e5DB26d9E31adb0e04bBc3bC74D0dc` (granted VERIFIER_ROLE)
- **Features:** Soulbound (non-transferable), verifier-only minting, batch mint (up to 20)
- **Tests:** 17/17 passing

### GroupEscrow

- **Address:** `0x88BE64988359fFfA919D72d0512550B65b11f74b`
- **Network:** Polygon Amoy Testnet
- **Deployer:** `0x61695C2be63f5143360c36dD1691315Ca701A099`
- **Features:** Multi-party escrow pool, create/contribute/complete/refund, ReentrancyGuard, max 50 members
- **Tests:** 24/24 passing (total 41 tests across both contracts)

---

## 📊 GOAL TYPES & TRACKING

| Type | How Progress Tracked | Badge Minting |
|------|---------------------|---------------|
| `personal_csv` | Upload CSV + salary = savings (salary - spend) | Backend mints SBT on completion |
| `personal_crypto` | **Sync Wallet** reads POL balance from MetaMask on Polygon Amoy | Backend mints SBT on completion |
| `group_escrow` | On-chain pooling via GroupEscrow contract | Contract releases + backend batch mints SBT |

> **Note:** `group_csv` was removed from the create modal. Only 3 types remain in the UI.

---

## 🧩 BACKEND CHANGES (api/routes/)

### `goals.py` — Goals 2.0 CRUD + Minting

**Key endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/{user_id}` | List all goals with progress, chain_status, badge_image_url |
| `POST` | `/` | Create goal (personal_csv, personal_crypto, group_escrow) |
| `POST` | `/{goal_id}/progress` | Upload CSV → calculate savings (salary mode or forecast mode) |
| `PUT` | `/{goal_id}/progress/manual` | Set progress manually (used by Sync Wallet for crypto goals) |
| `POST` | `/{goal_id}/complete` | Mark complete → generate PIL badge → IPFS upload → mint SBT |

**Important fixes made:**

1. **Forecast bug fix:** `_parse_csv_savings()` in forecast mode now correctly sets savings = 0 (was incorrectly set to total_spend)
2. **`_compute_gross_savings()` helper:** Shared logic for Stream A (forecast) + Stream B (hard savings)
3. **`_ipfs_to_image_url()` helper:** Converts `ipfs://` token URIs to Pinata gateway HTTP URLs for badge display
4. **`token_uri` stored in MongoDB** on mint — enables badge image display in frontend
5. **`ManualProgressUpdate` model:** Supports `mode: "set"` (absolute) and `mode: "add"` (incremental)
6. **`Field` imported from pydantic** — was missing initially, caused backend crash

### `savings.py` — NEW Savings Panel Route

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/savings/{user_id}` | Returns gross_savings = forecast_savings + hard_savings |

- **Stream A (Forecast):** Calls ML microservice (:8001), falls back to average of past CSV savings
- **Stream B (Hard):** salary - spend from all CSV uploads
- Uses shared `_compute_gross_savings()` helper (same logic as escrow enrichment)

### `escrow.py` — Group Escrow Routes (Updated)

- **`pledge_amount`** added to member join schema
- **Enriched `GET /{pool_id}`** response with: `saved_amount` (from `_compute_gross_savings`), `status` (fulfilled/on_track/behind), `avatar_initials`, `completion_pct`, `is_complete`
- **Pace detection:** Member is "behind" if saved_amount is >20% below linear pace from joined_at to target_date

### `main.py`

- Registered `savings.router` at `/api/v1/savings`

---

## 🎨 FRONTEND CHANGES

### `page.tsx` — Goals Page (Complete Rewrite)

**Three tabs:** My Goals | Group Pools | Achievements

**Key features:**

1. **Wallet Identity:** MetaMask-based (`window.ethereum`), falls back to `demo_user_001`
2. **SavingsPanel** at top of Goals tab (collapsible, shows Stream A + B + gross)
3. **Goal Cards** with conditional action buttons:
   - `personal_csv` → **CSV Upload** button (file picker → POST /progress)
   - `personal_crypto` → **Sync Wallet** button (reads POL balance from MetaMask on Polygon Amoy via `eth_getBalance`, auto-switches to Amoy chain)
4. **Mint Badge** button appears when goal is complete → calls `/complete` → shows badge popup
5. **Badge Popup** after minting: shows IPFS badge image, download link, Polygonscan link
6. **Achievements tab:** Shows actual IPFS badge images (not just emojis), with "Soulbound Badge" label and verify-on-chain link

**New/modified files:**

| File | Status |
|------|--------|
| `src/app/goals/page.tsx` | **Modified** — complete rewrite with wallet identity, 3 tabs, SyncWalletButton, badge popup |
| `src/components/goals/SavingsPanel.tsx` | **NEW** — collapsible gross savings hero component |
| `src/components/goals/GroupGoalPanel.tsx` | **NEW** — group pool card with member rows, contribute/mint buttons |
| `src/global.d.ts` | **NEW** — `window.ethereum` TypeScript declaration |
| `src/lib/types/goal.ts` | **NEW** — shared `Goal` interface |
| `src/components/goals/AddGoalModal.tsx` | **Modified** — imports Goal from shared types |

### SyncWalletButton (Crypto Goal Tracking)

The crypto goal's "Sync Wallet" button does:
1. Connects MetaMask (`eth_requestAccounts`)
2. Switches to Polygon Amoy (chain ID `0x13882`) via `wallet_switchEthereumChain` (auto-adds chain if missing)
3. Reads wallet balance via `eth_getBalance` RPC
4. Converts hex wei → POL (÷ 1e18)
5. Sends to backend `PUT /progress/manual` with `mode: "set"`
6. If balance ≥ target → goal auto-completes → "Mint Badge" button appears

---

## 🏗️ NFT BADGE / CERTIFICATE PIPELINE

```
Goal Complete → PIL generates image (400×400 badge or 800×560 certificate) →
Pinata uploads image → gets imageCID →
Pinata uploads metadata JSON (with ipfs://imageCID) → gets metadataCID →
Backend signs mintBadge(wallet, tokenURI) tx → SBT minted on Amoy →
token_uri stored in MongoDB → frontend shows badge image via Pinata gateway
```

- **Image display:** `https://gateway.pinata.cloud/ipfs/{CID}` (gateway URL from `_ipfs_to_image_url()`)
- **Badge popup:** Fetches metadata JSON from IPFS → extracts `image` field → displays in popup
- **Achievements tab:** Shows badge image from `badge_image_url` field in goal (gateway URL)

---

## 🔑 ENVIRONMENT VARIABLES

### `budget-bandhu-web3/.env`

```
DEPLOYER_PRIVATE_KEY=<deployer wallet private key>
AMOY_RPC_URL=https://rpc-amoy.polygon.technology/
VERIFIER_WALLET=0x35C98a0033e5DB26d9E31adb0e04bBc3bC74D0dc
POLYGONSCAN_API_KEY=<for contract verification>
```

### `budget-bandhu-rag/.env`

```
PINATA_JWT=<Pinata JWT token>
VERIFIER_PRIVATE_KEY=<backend verifier wallet private key>
SBT_CONTRACT_ADDRESS=0xB9b2550d61deB460168182fC68F99c6636727788
AMOY_RPC_URL=https://rpc-amoy.polygon.technology/
```

### `budget-bandhu-frontend/.env`

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SBT_ADDRESS=0xB9b2550d61deB460168182fC68F99c6636727788
NEXT_PUBLIC_ESCROW_ADDRESS=0x88BE64988359fFfA919D72d0512550B65b11f74b
```

---

## 🧪 TESTED E2E FLOWS

### ✅ Personal CSV Goal (Tested on Frontend)

1. Create personal_csv goal (₹20k target, ₹40k salary)
2. Upload CSV with ₹19,049 spend → savings = ₹20,951 (salary - spend)
3. Goal auto-completes (₹20,951 ≥ ₹20,000)
4. Click "Mint Badge" → PIL badge → IPFS → SBT minted on Amoy
5. Badge popup shows with IPFS image, download, Polygonscan link
6. Achievements tab shows badge image

### ✅ Personal Crypto Goal (Tested on Frontend)

1. Create personal_crypto goal (target = 0.007 POL)
2. Click "Sync Wallet" → MetaMask switches to Amoy → reads balance
3. If balance ≥ target → complete → Mint Badge
4. (Currently syncing shows 0.0000 if on wrong network — fixed with auto chain switch to Amoy)

### ✅ SBT Minting (Tested via Script + Frontend)

- Multiple successful mints on Polygon Amoy
- Example tx: `0xcd287f12ab503dd0f189090f7e18f1a03c3b46ec91acc3a859376c4c199afa78`
- Token #2 minted: BudgetBandhu Goal Badge (BBGOAL) to `0x61695C2b...Ca701A099`

### ✅ GroupEscrow On-chain (Tested via Script)

- Pool created, contribution sent, pool completed, funds released
- All on Polygon Amoy testnet

---

## ⚙️ TECHNICAL DECISIONS & GOTCHAS

1. **OpenZeppelin v5 + mcopy:** Requires `evmVersion: "cancun"` in hardhat.config.js
2. **Gas spikes on Amoy:** Deploy scripts cap gas (initially 35 gwei, later removed cap when needed)
3. **web3.py v6:** Uses `ExtraDataToPOAMiddleware` for POA chains
4. **Soulbound enforcement:** `require(from == address(0))` in `_update()` override
5. **MetaMask chain switch:** Sync Wallet auto-switches to Polygon Amoy (`0x13882`) before reading balance
6. **THREE.js WebGL crash:** The 3D background animation on the goals page occasionally crashes WebGL context — this is pre-existing and unrelated to Goals 2.0 changes
7. **Fallback user identity:** If no MetaMask wallet saved in localStorage, falls back to `demo_user_001`
8. **`Field` import:** Must be imported from pydantic for `ManualProgressUpdate` model (caused backend crash when missing)

---

## ❌ REMAINING WORK

### P0 — Must Fix
- [ ] Sync Wallet on crypto goals — verify it reads correct Amoy balance after chain switch (was showing 0.0000)
- [ ] Delete old test goals from MongoDB if needed (from debugging sessions)

### P1 — Should Do
- [ ] Full E2E group escrow test on frontend (create pool → join → contribute → complete → batch mint)
- [ ] Verify contracts on Polygonscan (`npx hardhat verify`)
- [ ] Wire the escrow contribute/complete buttons in GroupGoalPanel to the actual contract via useEscrowPool hook
- [ ] Show badge image in badge popup for previously minted goals (need to backfill `token_uri` in MongoDB for old goals)

### P2 — Polish
- [ ] "Behind" pace detection UI polish on group member rows
- [ ] Auto-refresh goals after Sync Wallet without manual page reload
- [ ] Handle ML microservice integration for forecast savings (currently falls back to averages)
- [ ] Mobile responsiveness of goal cards and badge popup

---

## 🧭 HOW TO RUN

### Backend:
```bash
cd budget-bandhu-rag
source ~/venv/bin/activate
python -m uvicorn api.main:app --reload --port 8000
```

### Frontend:
```bash
cd budget-bandhu-frontend
npm run dev
# Opens at http://localhost:3000
```

### Smart Contract Tests:
```bash
cd budget-bandhu-web3
npm test  # 41 tests passing
```

### Quick CSV Test (Frontend):
1. Create personal_csv goal (target ₹20k, salary ₹40k)
2. Upload `/tmp/sample_transactions.csv` (₹19,049 spend → ₹20,951 savings)
3. Goal completes → Mint Badge

### Quick Crypto Test (Frontend):
1. Create personal_crypto goal (target 0.05 POL)
2. Click Sync Wallet → MetaMask reads Amoy balance (~0.07 POL)
3. Goal completes → Mint Badge
