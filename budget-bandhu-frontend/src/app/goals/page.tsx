"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Target, Users, Trophy, Plus, Upload, CheckCircle2, Clock,
  ExternalLink, Coins, Loader2, Wallet
} from "lucide-react";
import { POLYGONSCAN_BASE } from "@/lib/contracts/config";
import SavingsPanel from "@/components/goals/SavingsPanel";
import GroupGoalPanel from "@/components/goals/GroupGoalPanel";

// ── Types ─────────────────────────────────────────────────────────────────────
type GoalType = "personal_csv" | "personal_crypto" | "group_csv" | "group_escrow";

interface Goal {
  id: string;
  name: string;
  icon: string;
  target: number;
  current: number;
  deadline: string;
  priority: string;
  goal_type: GoalType;
  progress_percentage: number;
  remaining: number;
  on_track: boolean;
  eta_days: number | null;
  chain_status: "pending" | "badge_minted";
  badge_tx_hash: string | null;
  wallet_address: string | null;
  token_uri: string | null;
  badge_image_url: string | null;
  // ML ETA fields (upstream)
  projected_completion_date?: string | null;
  shortfall_risk?: string | null;
  ai_verified?: boolean;
}

interface EscrowPoolSummary {
  pool_id: string;
  name: string;
  target_amount: number;
  currency: string;
  deadline: string;
  member_count: number;
  chain_status: "pending" | "funded" | "completed";
  badge_tx_hash: string | null;
  is_creator: boolean;
}

// Full enriched pool (from GET /escrow/{pool_id})
interface EnrichedPool {
  pool_id: string;
  name: string;
  target_amount: number;
  target_currency: string;
  target_date: string;
  max_members: number;
  member_count: number;
  members: {
    user_id: string;
    wallet: string;
    display_name: string;
    avatar_initials: string;
    joined_at: string;
    pledge_amount: number;
    saved_amount: number;
    status: "fulfilled" | "on_track" | "behind";
  }[];
  total_pledged: number;
  total_saved: number;
  completion_pct: number;
  is_complete: boolean;
  invite_code?: string;
  chain_pool_id: number | null;
  chain_status: "pending" | "funded" | "completed";
  badge_tx_hash: string | null;
  creator_user_id: string;
}

const API = process.env.NEXT_PUBLIC_API_URL || "https://babylike-overtimorously-stacey.ngrok-free.dev";

// Wrapper that always includes the header to bypass ngrok's browser interstitial
const apiFetch = (url: string, options?: RequestInit) =>
  fetch(url, {
    ...options,
    headers: {
      'ngrok-skip-browser-warning': '1',
      ...options?.headers,
    },
  });

const GOAL_TYPE_LABELS: Record<GoalType, { label: string; icon: string; color: string }> = {
  personal_csv:    { label: "Personal",        icon: "📊", color: "#6366f1" },
  personal_crypto: { label: "Crypto Goal",     icon: "🔷", color: "#8b5cf6" },
  group_csv:       { label: "Group Savings",   icon: "👥", color: "#10b981" },
  group_escrow:    { label: "Escrow Pool",     icon: "🔒", color: "#f59e0b" },
};

// ── Utility ───────────────────────────────────────────────────────────────────
const fmt = (n: number) =>
  n >= 1e7 ? `₹${(n / 1e7).toFixed(1)}Cr`
  : n >= 1e5 ? `₹${(n / 1e5).toFixed(1)}L`
  : `₹${n.toLocaleString("en-IN")}`;

const daysLeft = (deadline: string) =>
  Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000));

// ── Sub-components ────────────────────────────────────────────────────────────
function ChainBadge({ status }: { status: string }) {
  if (status === "badge_minted" || status === "completed")
    return <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full"><CheckCircle2 size={11} /> On-chain</span>;
  return <span className="flex items-center gap-1 text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full"><Clock size={11} /> Pending</span>;
}

function ProgressBar({ pct, color = "#6366f1" }: { pct: number; color?: string }) {
  return (
    <div className="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
      <motion.div
        className="h-full rounded-full"
        style={{ background: color }}
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(pct, 100)}%` }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      />
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function GoalsPage() {
  const [tab, setTab]               = useState<"goals" | "pools" | "achievements">("goals");
  const [goals, setGoals]           = useState<Goal[]>([]);
  const [poolSummaries, setPoolSummaries] = useState<EscrowPoolSummary[]>([]);
  const [enrichedPools, setEnrichedPools] = useState<EnrichedPool[]>([]);
  const [loading, setLoading]       = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [mintingGoalId, setMintingGoalId]     = useState<string | null>(null);
  const [mintMsg, setMintMsg]       = useState<string | null>(null);

  // Badge popup state
  const [badgePopup, setBadgePopup] = useState<{
    show: boolean; imageUrl: string; goalName: string; txHash: string; tokenUri: string;
  } | null>(null);

  // ── Wallet-based identity ────────────────────────────────────────────────
  const [userId, setUserId]         = useState<string | null>(null);
  const [walletConnecting, setWalletConnecting] = useState(false);

  const connectWallet = async () => {
    if (typeof window === "undefined" || !window.ethereum) {
      alert("MetaMask not found. Please install MetaMask.");
      return;
    }
    setWalletConnecting(true);
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
      if (accounts?.[0]) {
        setUserId(accounts[0].toLowerCase());
        localStorage.setItem("budget_bandhu_user", accounts[0].toLowerCase());
      }
    } catch (e) {
      console.error("Wallet connect failed:", e);
    }
    setWalletConnecting(false);
  };

  // Check for saved wallet on mount
  useEffect(() => {
    const saved = localStorage.getItem("budget_bandhu_user");
    if (saved) {
      setUserId(saved);
    } else {
      // Fallback to demo user for development
      setUserId("917558497556");
    }
  }, []);

  // ── Data fetching ────────────────────────────────────────────────────────
  const fetchGoals = useCallback(async () => {
    if (!userId) return;
    try {
      const [gRes, pRes] = await Promise.all([
        apiFetch(`${API}/api/v1/goals/${userId}`),
        apiFetch(`${API}/api/v1/escrow/user/${userId}`),
      ]);
      if (gRes.ok) setGoals(await gRes.json());
      if (pRes.ok) {
        const summaries: EscrowPoolSummary[] = await pRes.json();
        setPoolSummaries(summaries);

        // Fetch enriched data for each pool
        const enriched = await Promise.all(
          summaries.map(async (s) => {
            try {
              const r = await apiFetch(`${API}/api/v1/escrow/${s.pool_id}`);
              if (r.ok) return await r.json();
            } catch {}
            return null;
          })
        );
        setEnrichedPools(enriched.filter(Boolean));
      }
    } catch {}
    setLoading(false);
  }, [userId]);

  useEffect(() => {
    if (userId) {
      setLoading(true);
      void fetchGoals();
    }
  }, [userId, fetchGoals]);

  const handleMintBadge = async (goal: Goal) => {
    const wallet = window.prompt("Enter your wallet address to receive the SBT badge:");
    if (!wallet) return;
    setMintingGoalId(goal.id);
    setMintMsg(null);
    try {
      const res = await apiFetch(`${API}/api/v1/goals/${goal.id}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet_address: wallet }),
      });
      const data = await res.json();
      if (data.success) {
        setMintMsg(`🎉 Badge minted! TX: ${data.badge_tx_hash?.slice(0, 10)}...`);
        // Show badge popup with IPFS image
        const metadataUrl = data.token_uri?.replace("ipfs://", "https://gateway.pinata.cloud/ipfs/");
        if (metadataUrl) {
          try {
            const metaRes = await fetch(metadataUrl);
            const meta = await metaRes.json();
            const imgUrl = meta.image?.replace("ipfs://", "https://gateway.pinata.cloud/ipfs/");
            setBadgePopup({
              show: true,
              imageUrl: imgUrl || metadataUrl,
              goalName: goal.name,
              txHash: data.badge_tx_hash || "",
              tokenUri: data.token_uri || "",
            });
          } catch {
            // Fallback: use metadata URL directly as image
            setBadgePopup({
              show: true,
              imageUrl: metadataUrl,
              goalName: goal.name,
              txHash: data.badge_tx_hash || "",
              tokenUri: data.token_uri || "",
            });
          }
        }
        fetchGoals();
      } else {
        setMintMsg(`❌ ${data.detail || "Mint failed"}`);
      }
    } catch {
      setMintMsg("❌ Network error");
    }
    setMintingGoalId(null);
  };

  const achievements = goals.filter(g => g.chain_status === "badge_minted");

  const tabs = [
    { key: "goals",        label: "My Goals",     icon: <Target size={15} />,   count: goals.length },
    { key: "pools",        label: "Group Pools",  icon: <Users size={15} />,    count: enrichedPools.length },
    { key: "achievements", label: "Achievements", icon: <Trophy size={15} />,   count: achievements.length },
  ] as const;

  // ── Wallet Connect Prompt ─────────────────────────────────────────────────
  if (!userId) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 via-purple-50 to-indigo-50 flex items-center justify-center">
        <motion.div
          className="bg-white rounded-2xl shadow-lg p-8 text-center max-w-sm"
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
        >
          <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-2xl flex items-center justify-center shadow-lg shadow-indigo-200">
            <Wallet size={28} className="text-white" />
          </div>
          <h2 className="text-xl font-black text-gray-900 mb-2">Connect Wallet</h2>
          <p className="text-sm text-gray-500 mb-6">Connect your MetaMask wallet to access Goals 2.0</p>
          <button
            onClick={connectWallet}
            disabled={walletConnecting}
            className="w-full py-3 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {walletConnecting ? <Loader2 size={16} className="animate-spin" /> : <Wallet size={16} />}
            {walletConnecting ? "Connecting..." : "Connect MetaMask"}
          </button>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-purple-50 to-indigo-50">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-xl border-b border-gray-100 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-black text-gray-900">Goals 2.0</h1>
              <p className="text-sm text-gray-500">On-chain proof of financial discipline</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-400 font-mono bg-gray-50 px-2 py-1 rounded-lg">
                {userId.startsWith("0x") ? `${userId.slice(0, 6)}...${userId.slice(-4)}` : userId}
              </span>
              <button
                onClick={() => setShowCreateModal(true)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl font-semibold text-sm hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-200"
              >
                <Plus size={16} /> New Goal
              </button>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mt-4 bg-gray-100 p-1 rounded-xl w-fit">
            {tabs.map(t => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                  tab === t.key
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {t.icon} {t.label}
                {t.count > 0 && (
                  <span className={`px-1.5 py-0.5 rounded-full text-xs ${tab === t.key ? "bg-indigo-100 text-indigo-700" : "bg-gray-200 text-gray-600"}`}>
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="animate-spin text-indigo-500" size={32} />
          </div>
        ) : (
          <AnimatePresence mode="wait">

            {/* ── MY GOALS TAB ───────────────────────────────────────── */}
            {tab === "goals" && (
              <motion.div key="goals" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                {/* Savings Panel at the top */}
                <SavingsPanel userId={userId} />

                {mintMsg && (
                  <div className={`mb-4 px-4 py-3 rounded-xl text-sm font-medium ${mintMsg.startsWith("🎉") ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                    {mintMsg}
                  </div>
                )}
                {goals.length === 0 ? (
                  <EmptyState message="No goals yet. Create your first goal!" action={() => setShowCreateModal(true)} />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                    {goals.map(goal => {
                      const typeInfo = GOAL_TYPE_LABELS[goal.goal_type] || GOAL_TYPE_LABELS.personal_csv;
                      const isComplete = goal.progress_percentage >= 100;
                      return (
                        <motion.div
                          key={goal.id}
                          className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 hover:shadow-md transition-all"
                          whileHover={{ y: -2 }}
                        >
                          {/* Header */}
                          <div className="flex items-start justify-between mb-4">
                            <div className="flex items-center gap-3">
                              <div className="text-3xl">{goal.icon}</div>
                              <div>
                                <h3 className="font-bold text-gray-900 text-base leading-tight">{goal.name}</h3>
                                <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: typeInfo.color + "18", color: typeInfo.color }}>
                                  {typeInfo.icon} {typeInfo.label}
                                </span>
                              </div>
                            </div>
                            <ChainBadge status={goal.chain_status} />
                          </div>

                          {/* Progress */}
                          <div className="mb-3">
                            <div className="flex justify-between text-sm mb-1.5">
                              <span className="font-bold text-gray-900">{fmt(goal.current)}</span>
                              <span className="text-gray-400">of {fmt(goal.target)}</span>
                            </div>
                            <ProgressBar pct={goal.progress_percentage} color={typeInfo.color} />
                            <div className="flex justify-between mt-1.5">
                              <span className="text-xs font-semibold" style={{ color: isComplete ? "#10b981" : "#6b7280" }}>
                                {isComplete ? "✅ Complete!" : `${goal.progress_percentage.toFixed(1)}%`}
                              </span>
                              <span className="text-xs text-gray-400">
                                {goal.on_track ? "🟢 On track" : "🔴 Behind"}
                              </span>
                            </div>
                          </div>

                          {/* Deadline */}
                          <div className="flex items-center gap-2 text-xs text-gray-500 mb-4">
                            <Clock size={12} />
                            {daysLeft(goal.deadline)} days left · {new Date(goal.deadline).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}
                          </div>

                          {/* Actions */}
                          <div className="flex gap-2">
                            {isComplete && goal.chain_status !== "badge_minted" && (
                              <button
                                onClick={() => handleMintBadge(goal)}
                                disabled={mintingGoalId === goal.id}
                                className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg text-xs font-bold hover:opacity-90 transition disabled:opacity-50"
                              >
                                {mintingGoalId === goal.id ? <Loader2 size={12} className="animate-spin" /> : <Trophy size={12} />}
                                Mint Badge
                              </button>
                            )}
                            {goal.badge_tx_hash && (
                              <a
                                href={`${POLYGONSCAN_BASE}/tx/${goal.badge_tx_hash}`}
                                target="_blank" rel="noreferrer"
                                className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                              >
                                <ExternalLink size={11} /> View on chain
                              </a>
                            )}
                            {goal.goal_type === "personal_csv" && (
                              <UploadCSVButton goalId={goal.id} onDone={fetchGoals} />
                            )}
                            {goal.goal_type === "personal_crypto" && !isComplete && (
                              <SyncWalletButton goalId={goal.id} onDone={fetchGoals} />
                            )}
                          </div>
                        </motion.div>
                      );
                    })}
                  </div>
                )}
              </motion.div>
            )}

            {/* ── GROUP POOLS TAB ────────────────────────────────────── */}
            {tab === "pools" && (
              <motion.div key="pools" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                {enrichedPools.length === 0 ? (
                  <EmptyState message="No group pools yet. Create one and invite friends!" action={() => setShowCreateModal(true)} />
                ) : (
                  <div className="space-y-4">
                    {enrichedPools.map(pool => (
                      <GroupGoalPanel
                        key={pool.pool_id}
                        pool={pool}
                        onRefresh={fetchGoals}
                      />
                    ))}
                  </div>
                )}
              </motion.div>
            )}

            {/* ── ACHIEVEMENTS TAB ───────────────────────────────────── */}
            {tab === "achievements" && (
              <motion.div key="achievements" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                {achievements.length === 0 ? (
                  <EmptyState message="No badges yet. Complete a goal to earn your first SBT!" action={() => setTab("goals")} actionLabel="View Goals" />
                ) : (
                  <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-4">
                    {achievements.map(goal => (
                      <motion.div
                        key={goal.id}
                        className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 text-center"
                        whileHover={{ scale: 1.03 }}
                      >
                        {/* Show IPFS badge image if available, else emoji */}
                        {goal.badge_image_url ? (
                          <div className="w-24 h-24 mx-auto mb-3 rounded-xl overflow-hidden shadow-md">
                            <img
                              src={goal.badge_image_url}
                              alt={`${goal.name} badge`}
                              className="w-full h-full object-cover"
                              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                            />
                          </div>
                        ) : (
                          <div className="text-5xl mb-3">{goal.icon}</div>
                        )}
                        <h4 className="font-bold text-gray-900 text-sm mb-1">{goal.name}</h4>
                        <p className="text-xs text-gray-500 mb-3">{fmt(goal.target)}</p>
                        <div className="flex items-center justify-center gap-1 mb-3">
                          <CheckCircle2 size={14} className="text-emerald-500" />
                          <span className="text-xs font-semibold text-emerald-600">Soulbound Badge</span>
                        </div>
                        {goal.badge_tx_hash && (
                          <a
                            href={`${POLYGONSCAN_BASE}/tx/${goal.badge_tx_hash}`}
                            target="_blank" rel="noreferrer"
                            className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center justify-center gap-1 font-medium"
                          >
                            <ExternalLink size={10} /> Verify on-chain
                          </a>
                        )}
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}

          </AnimatePresence>
        )}
      </div>

      {/* Create Modal */}
      {showCreateModal && <CreateGoalModal userId={userId} onClose={() => setShowCreateModal(false)} onCreated={fetchGoals} />}

      {/* Badge Popup after minting */}
      {badgePopup?.show && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setBadgePopup(null)}>
          <motion.div
            className="bg-white rounded-3xl shadow-2xl w-full max-w-sm p-6 text-center"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-4xl mb-2">🎉</div>
            <h2 className="text-xl font-black text-gray-900 mb-1">Badge Minted!</h2>
            <p className="text-sm text-gray-500 mb-4">{badgePopup.goalName}</p>

            {/* Badge Image */}
            <div className="w-48 h-48 mx-auto mb-4 rounded-2xl overflow-hidden shadow-lg border-4 border-indigo-100">
              <img
                src={badgePopup.imageUrl}
                alt="Your SBT Badge"
                className="w-full h-full object-cover"
              />
            </div>

            {/* Actions */}
            <div className="space-y-2">
              <a
                href={badgePopup.imageUrl}
                download={`${badgePopup.goalName.replace(/\s+/g, '_')}_badge.png`}
                target="_blank" rel="noreferrer"
                className="w-full block py-2.5 bg-indigo-600 text-white rounded-xl font-bold text-sm hover:bg-indigo-700 transition"
              >
                ⬇️ Download Badge
              </a>
              <a
                href={`${POLYGONSCAN_BASE}/tx/${badgePopup.txHash}`}
                target="_blank" rel="noreferrer"
                className="w-full block py-2.5 border border-gray-200 text-gray-700 rounded-xl font-medium text-sm hover:bg-gray-50 transition"
              >
                🔗 View on Polygonscan
              </a>
              <button
                onClick={() => setBadgePopup(null)}
                className="w-full py-2 text-sm text-gray-400 hover:text-gray-600 transition"
              >
                Close
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}

// ── CSV Upload Button ─────────────────────────────────────────────────────────
function UploadCSVButton({ goalId, onDone }: { goalId: string; onDone: () => void }) {
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("file", file);
    try {
      await apiFetch(`${API}/api/v1/goals/${goalId}/progress`, { method: "POST", body: form });
      onDone();
    } catch {}
    setUploading(false);
  };

  return (
    <>
      <input ref={inputRef} type="file" accept=".csv" className="hidden" onChange={handleFile} />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="flex items-center gap-1 px-2.5 py-2 bg-gray-50 text-gray-600 rounded-lg text-xs font-medium hover:bg-gray-100 transition disabled:opacity-50"
      >
        {uploading ? <Loader2 size={11} className="animate-spin" /> : <Upload size={11} />} CSV
      </button>
    </>
  );
}

// ── Sync Wallet Button (for crypto goals — reads on-chain balance) ──────────
function SyncWalletButton({ goalId, onDone }: { goalId: string; onDone: () => void }) {
  const [syncing, setSyncing] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const handleSync = async () => {
    setMsg(null);
    if (!window.ethereum) {
      setMsg("Install MetaMask");
      return;
    }

    setSyncing(true);
    try {
      // 1. Connect to MetaMask
      const accounts: string[] = await window.ethereum.request({ method: "eth_requestAccounts" });
      const wallet = accounts[0];
      if (!wallet) { setMsg("No wallet connected"); setSyncing(false); return; }

      // 2. Switch to Polygon Amoy (chain ID 80002 = 0x13882)
      const AMOY_CHAIN_ID = "0x13882";
      try {
        await window.ethereum.request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: AMOY_CHAIN_ID }],
        });
      } catch {
        // Chain not added yet — add it
        await window.ethereum.request({
          method: "wallet_addEthereumChain",
          params: [{
            chainId: AMOY_CHAIN_ID,
            chainName: "Polygon Amoy Testnet",
            nativeCurrency: { name: "POL", symbol: "POL", decimals: 18 },
            rpcUrls: ["https://rpc-amoy.polygon.technology"],
            blockExplorerUrls: ["https://amoy.polygonscan.com"],
          }],
        });
      }

      // 3. Read raw balance (hex wei) via MetaMask RPC
      const balanceHex: string = await window.ethereum.request({
        method: "eth_getBalance",
        params: [wallet, "latest"],
      });
      // Convert hex wei → POL (18 decimals)
      const balanceWei = BigInt(balanceHex);
      const balancePOL = Number(balanceWei) / 1e18;

      // 3. Send to backend
      const res = await apiFetch(`${API}/api/v1/goals/${goalId}/progress/manual`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: parseFloat(balancePOL.toFixed(6)), mode: "set" }),
      });
      const data = await res.json();

      if (data.is_complete) {
        setMsg(`✅ ${balancePOL.toFixed(4)} POL — Goal complete!`);
      } else {
        setMsg(`${balancePOL.toFixed(4)} POL synced`);
      }
      onDone();
    } catch (e) {
      setMsg("Sync failed");
      console.error(e);
    }
    setSyncing(false);
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleSync}
        disabled={syncing}
        className="flex items-center gap-1 px-3 py-2 bg-purple-50 text-purple-700 rounded-lg text-xs font-semibold hover:bg-purple-100 transition disabled:opacity-50"
      >
        {syncing ? <Loader2 size={11} className="animate-spin" /> : <Wallet size={11} />} Sync Wallet
      </button>
      {msg && <span className="text-[10px] text-gray-500">{msg}</span>}
    </div>
  );
}

// ── Empty State ───────────────────────────────────────────────────────────────
function EmptyState({ message, action, actionLabel = "Create Now" }: { message: string; action: () => void; actionLabel?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <div className="text-5xl mb-4">🎯</div>
      <p className="text-gray-600 mb-4 max-w-xs">{message}</p>
      <button onClick={action} className="px-5 py-2 bg-indigo-600 text-white rounded-xl font-semibold text-sm hover:bg-indigo-700 transition">
        {actionLabel}
      </button>
    </div>
  );
}

// ── Create Goal Modal ─────────────────────────────────────────────────────────
function CreateGoalModal({ userId, onClose, onCreated }: { userId: string; onClose: () => void; onCreated: () => void }) {
  const [goalType, setGoalType] = useState<GoalType>("personal_csv");
  const [name, setName]         = useState("");
  const [target, setTarget]     = useState("");
  const [deadline, setDeadline] = useState("");
  const [wallet, setWallet]     = useState("");
  const [salary, setSalary]     = useState("");
  const [loading, setLoading]   = useState(false);

  const submit = async () => {
    if (!name || !target || !deadline) return;
    setLoading(true);
    try {
      const endpoint = goalType === "group_escrow"
        ? `${API}/api/v1/escrow`
        : `${API}/api/v1/goals`;

      const body = goalType === "group_escrow"
        ? {
            creator_user_id:  userId,
            creator_wallet:   wallet,
            name, target_amount: parseFloat(target),
            target_currency: "POL",
            deadline,
            max_members: 10,
          }
        : {
            user_id: userId, name,
            target: parseFloat(target),
            deadline, goal_type: goalType,
            wallet_address: wallet || null,
            salary: salary ? parseFloat(salary) : null,
          };

      await apiFetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      onCreated();
      onClose();
    } catch {}
    setLoading(false);
  };

  const types: { key: GoalType; label: string; icon: string; desc: string }[] = [
    { key: "personal_csv",    icon: "📊", label: "Personal",     desc: "Upload CSV to track savings" },
    { key: "personal_crypto", icon: "🔷", label: "Crypto Goal",  desc: "Track via wallet / manual confirm" },
    { key: "group_escrow",    icon: "🔒", label: "Group Pool",   desc: "Lock POL on-chain together" },
  ];

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <motion.div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md"
        initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
      >
        <div className="p-6 border-b border-gray-100">
          <h2 className="text-xl font-black text-gray-900">New Goal</h2>
          <p className="text-sm text-gray-500 mt-1">Choose your goal type</p>
        </div>

        <div className="p-6 space-y-5">
          {/* Goal type selector — 3 types (dropped group_csv) */}
          <div className="grid grid-cols-3 gap-2">
            {types.map(t => (
              <button
                key={t.key}
                onClick={() => setGoalType(t.key)}
                className={`text-left p-3 rounded-xl border-2 transition-all ${goalType === t.key ? "border-indigo-500 bg-indigo-50" : "border-gray-200 hover:border-gray-300"}`}
              >
                <div className="text-xl mb-1">{t.icon}</div>
                <div className="text-xs font-bold text-gray-900">{t.label}</div>
                <div className="text-xs text-gray-500 mt-0.5">{t.desc}</div>
              </button>
            ))}
          </div>

          {/* Fields */}
          <div className="space-y-3">
            <input
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
              placeholder="Goal name (e.g. Goa Trip)"
              value={name} onChange={e => setName(e.target.value)}
            />
            <div className="flex gap-2">
              <input
                className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
                placeholder={goalType === "group_escrow" ? "Target (POL)" : "Target (₹)"}
                type="number" value={target} onChange={e => setTarget(e.target.value)}
              />
              <input
                className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
                type="date" value={deadline} onChange={e => setDeadline(e.target.value)}
              />
            </div>

            {(goalType === "personal_csv" || goalType === "personal_crypto") && (
              <input
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
                placeholder="Monthly salary (optional, for long-term mode)"
                type="number" value={salary} onChange={e => setSalary(e.target.value)}
              />
            )}

            <input
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
              placeholder={goalType === "group_escrow" ? "Your wallet address (required)" : "Wallet address (for SBT badge)"}
              value={wallet} onChange={e => setWallet(e.target.value)}
            />
          </div>
        </div>

        <div className="p-6 border-t border-gray-100 flex gap-3">
          <button onClick={onClose} className="flex-1 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition">Cancel</button>
          <button
            onClick={submit} disabled={loading}
            className="flex-1 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-bold hover:bg-indigo-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            Create Goal
          </button>
        </div>
      </motion.div>
    </div>
  );
}
