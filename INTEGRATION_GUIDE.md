# BudgetBandhu: Complete Frontend-Backend Integration Guide

## Project Structure
```
BudgetBandhu/
├── budget-bandhu-frontend/    # Next.js 14 Frontend (React + TypeScript)
│   ├── src/
│   │   ├── app/              # App Router Pages
│   │   ├── components/       # UI Components
│   │   └── lib/              # API, Hooks, Store, Utils
│   
└── budget-bandhu-ml/          # FastAPI Backend (Python)
    ├── api/                   # Unified API (main.py, routes/)
    ├── core/                  # Agent Controller, Gating
    ├── intelligence/          # ML Models (Phi-3, Categorizer, Anomaly)
    ├── memory/                # Memory & Conversation Managers
    └── database/              # MongoDB Manager
```

---

## Backend API (Unified - `api/main.py`)
**Base URL**: `http://localhost:8000` (or Ngrok URL)
**Database**: MongoDB → `budget_bandhu`

### Endpoints Summary

| Feature | Endpoint | Method | Status |
|---------|----------|--------|--------|
| **AUTH** |
| Register | `/api/v1/user/register` | POST | ✅ Working |
| Login | `/api/v1/user/login` | POST | ✅ Working |
| Get Profile | `/api/v1/user/{mobile_number}` | GET | ✅ Working |
| **TRANSACTIONS** |
| Add Single | `/api/v1/transactions?user_id={id}` | POST | ✅ ML Categorization + Anomaly |
| Add Bulk | `/api/v1/transactions/bulk` | POST | ✅ ML Pipeline |
| Get All | `/api/v1/transactions/{user_id}` | GET | ✅ Working |
| **AI CHAT** |
| Chat | `/api/v1/chat` | POST | ✅ RAG + Memory |
| **ANALYTICS** |
| Insights | `/api/v1/analytics/{user_id}` | GET | ✅ Working |
| Forecast | `/api/v1/forecast` | POST | ✅ LSTM (needs 30+ txns) |
| **HEALTH** |
| Health | `/health` | GET | ✅ Working |

---

## Frontend Features & Components

### Authentication (`/auth/*`)
- **Login Page**: `/auth/login` - Email/Password (needs Mobile integration)
- **Signup Page**: `/auth/signup` - Name, Email, Phone, Password
- **Verify Page**: `/auth/verify` - OTP Verification

### Main Dashboard (`/`)
- **BalanceCard**: Current balance, income, expenses
- **SpendingChart**: 30-day trend visualization
- **CategoryBreakdown**: Pie chart by category
- **InsightsPanel**: AI-generated insights
- **QuickActions**: Add transaction, Chat, Goals

### Transactions (`/transactions`)
- **TransactionList**: All transactions with filters
- **AddTransactionModal**: Manual entry
- **CSVUpload**: Bulk import
- **AnomalyBadge**: Visual anomaly indicators

### AI Chat (`/chat`)
- **ChatInterface**: Full conversation UI
- **MessageBubbles**: User/AI messages
- **QuickSuggestions**: Common queries

### Budget (`/budget`)
- **BudgetAllocations**: Category-wise budgets
- **Recommendations**: AI budget suggestions
- **SpentVsAllocated**: Visual comparison

### Goals (`/goals`)
- **GoalCards**: Individual goal progress
- **CreateGoal**: New goal form
- **Contribute**: Add to goal

### Gamification (`/gamification`)
- **LevelProgress**: XP and level display
- **BadgeGallery**: Earned badges
- **Leaderboard**: Peer comparison

---

## Primary User ID Strategy
**IMPORTANT**: The backend now uses **12-digit Mobile Number** as the primary key.
Format: `91XXXXXXXXXX` (91 + 10 digits)

---

## Environment Configuration

### Frontend `.env.local`
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_ML_API_URL=http://localhost:8000
```

For production/Ngrok:
```env
NEXT_PUBLIC_API_URL=https://your-ngrok-url.ngrok-free.dev
NEXT_PUBLIC_ML_API_URL=https://your-ngrok-url.ngrok-free.dev
```

---

## Authentication Flow (Mobile-First)

1. **Registration**:
   - User provides: name, mobile (12 digits), password
   - Backend creates user with Mobile as `_id`
   - Default budgets & gamification initialized

2. **Login**:
   - User provides: mobile, password
   - Backend verifies & returns user object
   - Frontend stores `user_id` (mobile) in localStorage/context

3. **All Requests**:
   - Pass `user_id` (mobile number) to all endpoints
   - No JWT for now (can add later)

---

## ML Features (Active)

1. **Transaction Categorization**
   - Rule-based (80% coverage)
   - Phi-3.5 fallback via Ollama
   - 15 Indian financial categories

2. **Anomaly Detection**
   - Isolation Forest model
   - User-personalized detection
   - Severity levels: low, medium, high

3. **AI Chat (RAG)**
   - Budget Bandhu persona
   - Context from transactions + memory
   - Gating for scope & safety

4. **Analytics & Insights**
   - Category breakdown
   - Overspending alerts
   - Personalized tips

5. **Forecasting**
   - LSTM-based (needs 30+ transactions)
   - Fallback to average

---

## Integration Checklist

### Phase 1: Environment Setup ✅
- [x] Create `.env.local` in frontend
- [x] Set API URLs to backend

### Phase 2: Auth Integration
- [ ] Update login to use mobile + password
- [ ] Update signup to send mobile in correct format
- [ ] Store user_id in context after login

### Phase 3: Transaction Integration
- [ ] Wire AddTransaction form to API
- [ ] Display ML categories from response
- [ ] Show anomaly warnings

### Phase 4: Chat Integration
- [ ] Send messages to `/api/v1/chat`
- [ ] Display AI responses

### Phase 5: Analytics Integration
- [ ] Fetch insights from `/api/v1/analytics/{user_id}`
- [ ] Display forecast if available

---

## Running the Full Stack

### Backend
```bash
cd budget-bandhu-ml
.\venv\Scripts\activate
python -m api.main
```
Server runs on `http://localhost:8000`

### Frontend
```bash
cd budget-bandhu-frontend
npm run dev
```
UI runs on `http://localhost:3000`

---

## Current Ngrok URL
Check `budget-bandhu-ml/ngrok_url.txt` for the public URL.
