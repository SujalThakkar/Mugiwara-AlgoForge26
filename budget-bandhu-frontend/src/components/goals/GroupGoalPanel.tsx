"use client";

/**
 * GroupGoalPanel — Shows group escrow pool with member pledge rows,
 * progress tracking, and on-chain actions (Contribute / Complete & Mint).
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users, CheckCircle2, Clock, AlertTriangle, ExternalLink,
  Copy, Coins, Loader2, ChevronDown, ChevronUp
} from "lucide-react";
import { useEscrowPool } from "@/lib/hooks/useEscrowPool";
import { POLYGONSCAN_BASE } from "@/lib/contracts/config";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Formatting ────────────────────────────────────────────────────────────────
const fmtINR = (n: number) =>
  n >= 1e7 ? `₹${(n / 1e7).toFixed(1)}Cr`
  : n >= 1e5 ? `₹${(n / 1e5).toFixed(1)}L`
  : `₹${n.toLocaleString("en-IN")}`;

const fmtPOL = (n: number) => `${n.toFixed(3)} POL`;
const fmt = (n: number, currency: string) => currency === "POL" ? fmtPOL(n) : fmtINR(n);

const daysLeft = (deadline: string) =>
  Math.max(0, Math.ceil((new Date(deadline).getTime() - Date.now()) / 86400000));

// ── Types ─────────────────────────────────────────────────────────────────────
interface Member {
  user_id: string;
  wallet: string;
  display_name: string;
  avatar_initials: string;
  joined_at: string;
  pledge_amount: number;
  saved_amount: number;
  status: "fulfilled" | "on_track" | "behind";
}

interface Pool {
  pool_id: string;
  name: string;
  target_amount: number;
  target_currency: string;
  target_date: string;
  max_members: number;
  member_count: number;
  members: Member[];
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

// ── Status Pill ───────────────────────────────────────────────────────────────
function StatusPill({ status }: { status: string }) {
  const styles: Record<string, { bg: string; text: string; label: string }> = {
    fulfilled: { bg: "bg-emerald-100", text: "text-emerald-700", label: "Fulfilled" },
    on_track:  { bg: "bg-blue-100",    text: "text-blue-700",    label: "On track" },
    behind:    { bg: "bg-amber-100",   text: "text-amber-700",   label: "Behind" },
  };
  const s = styles[status] || styles.on_track;
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  );
}

function PoolStatusBadge({ pool }: { pool: Pool }) {
  const dl = daysLeft(pool.target_date);
  if (pool.chain_status === "completed" || pool.is_complete)
    return <span className="flex items-center gap-1 text-xs font-semibold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full"><CheckCircle2 size={12} /> Complete</span>;
  if (dl <= 0)
    return <span className="flex items-center gap-1 text-xs font-semibold text-red-600 bg-red-50 px-2.5 py-1 rounded-full"><AlertTriangle size={12} /> Overdue</span>;
  return <span className="flex items-center gap-1 text-xs font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full"><Clock size={12} /> Active</span>;
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function GroupGoalPanel({ pool, onRefresh }: { pool: Pool; onRefresh: () => void }) {
  const { contribute, completePool, loading: escrowLoading, error: escrowError, txHash } = useEscrowPool();

  const [inviteCopied, setInviteCopied] = useState(false);
  const [showContribute, setShowContribute] = useState(false);
  const [contribAmount, setContribAmount] = useState("");
  const [minting, setMinting] = useState(false);
  const [mintMsg, setMintMsg] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const isPOL = pool.target_currency === "POL";
  const dl = daysLeft(pool.target_date);

  const copyInvite = () => {
    const url = `${window.location.origin}/escrow/join/${pool.pool_id}`;
    navigator.clipboard.writeText(url);
    setInviteCopied(true);
    setTimeout(() => setInviteCopied(false), 2000);
  };

  const handleContribute = async () => {
    if (!contribAmount || !pool.chain_pool_id) return;
    const ok = await contribute(BigInt(pool.chain_pool_id), contribAmount);
    if (ok) {
      setShowContribute(false);
      setContribAmount("");
      onRefresh();
    }
  };

  const handleComplete = async () => {
    if (!pool.chain_pool_id) return;
    setMinting(true);
    setMintMsg(null);

    // 1. Call on-chain completePool
    const ok = await completePool(BigInt(pool.chain_pool_id));
    if (!ok) {
      setMintMsg("❌ On-chain completePool failed");
      setMinting(false);
      return;
    }

    // 2. Trigger backend batch mint
    try {
      const res = await fetch(`${API}/api/v1/escrow/${pool.pool_id}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (data.success) {
        setMintMsg(`🎉 ${data.badges_minted} badges minted!`);
        onRefresh();
      } else {
        setMintMsg(`❌ ${data.detail || "Mint failed"}`);
      }
    } catch {
      setMintMsg("❌ Network error");
    }
    setMinting(false);
  };

  // ── Avatar color from user_id hash ──────────────────────────────────────
  const avatarColor = (uid: string) => {
    const hue = [...uid].reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360;
    return `hsl(${hue}, 65%, 55%)`;
  };

  return (
    <motion.div
      className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {/* Header */}
      <div
        className="p-5 flex items-start justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 bg-gradient-to-br from-amber-400 to-orange-500 rounded-xl flex items-center justify-center shadow-lg shadow-amber-200/50">
            <Users size={20} className="text-white" />
          </div>
          <div>
            <h3 className="font-bold text-gray-900 text-base">{pool.name}</h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-500">
                {pool.member_count} member{pool.member_count !== 1 ? "s" : ""} · {dl}d left
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <PoolStatusBadge pool={pool} />
          {expanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
        </div>
      </div>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {/* Target + Progress */}
            <div className="px-5 pb-4">
              <div className="bg-gradient-to-r from-gray-50 to-slate-50 rounded-xl p-4 mb-4">
                <div className="flex justify-between items-baseline mb-2">
                  <span className="text-sm font-medium text-gray-500">Target</span>
                  <span className="text-2xl font-black text-gray-900">
                    {fmt(pool.target_amount, pool.target_currency)}
                  </span>
                </div>
                {/* Progress bar */}
                <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden mb-2">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500"
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(pool.completion_pct, 100)}%` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                  />
                </div>
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-gray-700">
                    {fmt(pool.total_saved, pool.target_currency)} saved
                  </span>
                  <span className="text-gray-500">{pool.completion_pct}% complete</span>
                </div>
              </div>

              {/* Members */}
              <div className="mb-4">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  Members ({pool.member_count})
                </p>
                <div className="space-y-2">
                  {pool.members.map((m) => (
                    <div
                      key={m.user_id}
                      className="flex items-center gap-3 p-2.5 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors"
                    >
                      {/* Avatar */}
                      <div
                        className="w-9 h-9 rounded-full flex items-center justify-center text-white text-xs font-bold shrink-0"
                        style={{ backgroundColor: avatarColor(m.user_id) }}
                      >
                        {m.avatar_initials}
                      </div>
                      {/* Name + Progress */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-gray-900 truncate">{m.display_name}</p>
                        <p className="text-xs text-gray-500">
                          {fmt(m.saved_amount, pool.target_currency)} / {fmt(m.pledge_amount, pool.target_currency)}
                        </p>
                      </div>
                      {/* Status */}
                      <StatusPill status={m.status} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Mint Message */}
              {mintMsg && (
                <div className={`mb-3 px-4 py-2.5 rounded-xl text-sm font-medium ${
                  mintMsg.startsWith("🎉") ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
                }`}>
                  {mintMsg}
                </div>
              )}
              {escrowError && (
                <div className="mb-3 px-4 py-2.5 rounded-xl text-sm font-medium bg-red-50 text-red-700">
                  ⚠️ {escrowError}
                </div>
              )}

              {/* Inline Contribute Input */}
              <AnimatePresence>
                {showContribute && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="mb-3 overflow-hidden"
                  >
                    <div className="flex gap-2">
                      <input
                        type="number"
                        placeholder="Amount in POL"
                        value={contribAmount}
                        onChange={(e) => setContribAmount(e.target.value)}
                        className="flex-1 px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-amber-400"
                      />
                      <button
                        onClick={handleContribute}
                        disabled={escrowLoading || !contribAmount}
                        className="px-4 py-2 bg-amber-500 text-white rounded-xl text-sm font-bold hover:bg-amber-600 transition disabled:opacity-50 flex items-center gap-1"
                      >
                        {escrowLoading ? <Loader2 size={14} className="animate-spin" /> : <Coins size={14} />}
                        Send
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Actions */}
              <div className="flex gap-2 flex-wrap">
                {/* Invite */}
                <button
                  onClick={copyInvite}
                  className="flex items-center gap-1.5 px-3 py-2 bg-indigo-50 text-indigo-700 rounded-xl text-xs font-semibold hover:bg-indigo-100 transition"
                >
                  {inviteCopied ? <CheckCircle2 size={12} /> : <Copy size={12} />}
                  {inviteCopied ? "Copied!" : "Invite Link"}
                </button>

                {/* Contribute (crypto pools, not completed) */}
                {isPOL && pool.chain_status !== "completed" && (
                  <button
                    onClick={() => setShowContribute(!showContribute)}
                    className="flex items-center gap-1.5 px-3 py-2 bg-amber-50 text-amber-700 rounded-xl text-xs font-semibold hover:bg-amber-100 transition"
                  >
                    <Coins size={12} /> Contribute
                  </button>
                )}

                {/* Complete & Mint (only when is_complete or funded by creator) */}
                {pool.is_complete && pool.chain_status !== "completed" && (
                  <button
                    onClick={handleComplete}
                    disabled={minting || escrowLoading}
                    className="flex items-center gap-1.5 px-3 py-2 bg-gradient-to-r from-emerald-500 to-green-500 text-white rounded-xl text-xs font-bold hover:opacity-90 transition disabled:opacity-50"
                  >
                    {minting ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                    Complete & Mint
                  </button>
                )}

                {/* Polygonscan link */}
                {pool.badge_tx_hash && (
                  <a
                    href={`${POLYGONSCAN_BASE}/tx/${pool.badge_tx_hash}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1 px-3 py-2 text-xs text-indigo-600 font-medium hover:text-indigo-800"
                  >
                    <ExternalLink size={11} /> View on chain
                  </a>
                )}
              </div>

              {/* Tx hash if just submitted */}
              {txHash && (
                <div className="mt-2 text-xs text-gray-500">
                  TX: <a href={`${POLYGONSCAN_BASE}/tx/${txHash}`} target="_blank" rel="noreferrer" className="text-indigo-600 hover:underline">{txHash.slice(0, 16)}...</a>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
