"use client";

import { useState, useEffect, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Users, Coins, Shield, Loader2, CheckCircle2, ExternalLink } from "lucide-react";
import { useEscrowPool } from "@/lib/hooks/useEscrowPool";
import { POLYGONSCAN_BASE } from "@/lib/contracts/config";

const API = process.env.NEXT_PUBLIC_API_URL || "https://babylike-overtimorously-stacey.ngrok-free.dev";

interface PoolMember {
  user_id:   string;
  wallet:    string;
  joined_at: string;
}

interface EscrowPool {
  pool_id:         string;
  name:            string;
  target_amount:   number;
  target_currency: string;
  deadline:        string;
  max_members:     number;
  member_count:    number;
  members:         PoolMember[];
  chain_status:    string;
  badge_tx_hash:   string | null;
  chain_pool_id:   number | null;
  creator_wallet:  string;
}

export default function EscrowJoinPage() {
  const { poolId } = useParams<{ poolId: string }>();
  const router     = useRouter();

  const [pool, setPool]       = useState<EscrowPool | null>(null);
  const [loading, setLoading] = useState(true);
  const [joined,  setJoined]  = useState(false);
  const [userId,  setUserId]  = useState("");
  const [wallet,  setWallet]  = useState("");
  const [joining, setJoining] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const { contribute, loading: escrowLoading, txHash } = useEscrowPool();

  useEffect(() => {
    fetch(`${API}/api/v1/escrow/${poolId}`)
      .then(r => r.json())
      .then((d: EscrowPool) => { setPool(d); setLoading(false); })
      .catch(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // useMemo must be called unconditionally — compute from pool or defaults
  const daysLeft = useMemo(() => {
    if (!pool?.deadline) return 0;
    return Math.max(0, Math.ceil((new Date(pool.deadline).getTime() - new Date().getTime()) / 86_400_000));
  }, [pool?.deadline]);

  const handleJoin = async () => {
    if (!userId || !wallet) { setError("Enter your user ID and wallet address"); return; }
    setJoining(true); setError(null);
    try {
      const res  = await fetch(`${API}/api/v1/escrow/${poolId}/join`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, wallet_address: wallet }),
      });
      const data = await res.json() as { joined?: boolean; already_member?: boolean };
      if (data.joined || data.already_member) setJoined(true);
      else setError("Could not join pool");
    } catch {
      setError("Network error");
    }
    setJoining(false);
  };

  const handleContribute = async () => {
    if (!pool?.chain_pool_id) { setError("Pool not yet linked to chain"); return; }
    const amt = window.prompt("Enter amount to contribute (in POL):");
    if (!amt) return;
    await contribute(BigInt(pool.chain_pool_id), amt);
  };

  if (loading) return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-indigo-50">
      <Loader2 className="animate-spin text-indigo-500" size={32} />
    </div>
  );

  if (!pool) return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-indigo-50">
      <div className="text-center">
        <p className="text-gray-600 text-lg">Pool not found 🤔</p>
        <button onClick={() => router.push("/goals")} className="mt-4 px-5 py-2 bg-indigo-600 text-white rounded-xl font-semibold text-sm">Go to Goals</button>
      </div>
    </div>
  );

  const isCrypto = pool.target_currency === "POL";

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-purple-50 to-indigo-100 flex items-center justify-center p-4">
      <motion.div
        className="w-full max-w-md bg-white rounded-3xl shadow-2xl overflow-hidden"
        initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
      >
        {/* Header banner */}
        <div className="bg-gradient-to-r from-indigo-600 to-purple-600 p-6 text-white">
          <div className="flex items-center gap-2 mb-1">
            {isCrypto ? <Coins size={20} /> : <Users size={20} />}
            <span className="text-sm font-semibold opacity-80">{isCrypto ? "Crypto Escrow Pool" : "Group Savings Pool"}</span>
          </div>
          <h1 className="text-2xl font-black">{pool.name}</h1>
          <p className="text-sm opacity-70 mt-1">You&apos;ve been invited to join</p>
        </div>

        {/* Pool stats */}
        <div className="grid grid-cols-3 divide-x divide-gray-100 border-b border-gray-100">
          {[
            { label: "Target",    value: isCrypto ? `${pool.target_amount} POL` : `₹${pool.target_amount.toLocaleString()}` },
            { label: "Members",   value: `${pool.member_count}/${pool.max_members}` },
            { label: "Days Left", value: String(daysLeft) },
          ].map(stat => (
            <div key={stat.label} className="p-4 text-center">
              <p className="text-xs text-gray-500">{stat.label}</p>
              <p className="text-base font-black text-gray-900 mt-0.5">{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="p-6">
          {joined ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-4">
              <CheckCircle2 size={40} className="text-emerald-500 mx-auto mb-3" />
              <h3 className="text-lg font-bold text-gray-900 mb-1">You&apos;re in! 🎉</h3>
              <p className="text-sm text-gray-500 mb-4">You&apos;ve joined &ldquo;{pool.name}&rdquo;. When the goal is complete, you&apos;ll receive an SBT badge.</p>

              {isCrypto && (
                <button
                  onClick={handleContribute}
                  disabled={escrowLoading}
                  className="w-full flex items-center justify-center gap-2 py-3 bg-amber-500 text-white rounded-xl font-bold hover:bg-amber-600 transition mb-3 disabled:opacity-50"
                >
                  {escrowLoading ? <Loader2 size={16} className="animate-spin" /> : <Coins size={16} />}
                  Contribute POL via MetaMask
                </button>
              )}

              {txHash && (
                <a href={`${POLYGONSCAN_BASE}/tx/${txHash}`} target="_blank" rel="noreferrer"
                  className="flex items-center justify-center gap-1 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
                  <ExternalLink size={13} /> View on Polygonscan
                </a>
              )}

              <button onClick={() => router.push("/goals")} className="mt-3 w-full py-2.5 border border-gray-200 text-gray-600 rounded-xl text-sm font-medium hover:bg-gray-50 transition">
                Go to Goals
              </button>
            </motion.div>
          ) : (
            <div className="space-y-4">
              <div className="bg-indigo-50 rounded-xl p-4 flex items-start gap-3">
                <Shield size={18} className="text-indigo-600 mt-0.5 shrink-0" />
                <p className="text-sm text-indigo-800">
                  {isCrypto
                    ? "Funds are locked in a smart contract on Polygon — nobody can touch them until the goal is met."
                    : "Progress is tracked via UPI CSV uploads. Everyone gets an SBT badge when the target is hit."}
                </p>
              </div>

              <input
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
                placeholder="Your user ID (phone / email)"
                value={userId} onChange={e => setUserId(e.target.value)}
              />
              <input
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-400"
                placeholder="Wallet address (for contributions + SBT)"
                value={wallet} onChange={e => setWallet(e.target.value)}
              />

              {error && <p className="text-xs text-red-500">{error}</p>}

              <button
                onClick={handleJoin} disabled={joining}
                className="w-full flex items-center justify-center gap-2 py-3 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 transition disabled:opacity-50"
              >
                {joining ? <Loader2 size={16} className="animate-spin" /> : <Users size={16} />}
                Join Pool
              </button>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
