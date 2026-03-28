"use client";

/**
 * SavingsPanel — Shows gross available savings (forecast + hard) at top of Goals tab.
 * Collapsible section, always visible when expanded.
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, ChevronDown, ChevronUp, Loader2, AlertCircle, Upload } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const fmtINR = (n: number) =>
  n >= 1e7 ? `₹${(n / 1e7).toFixed(1)}Cr`
  : n >= 1e5 ? `₹${(n / 1e5).toFixed(1)}L`
  : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

interface SavingsData {
  hard_savings: number;
  forecast_savings: number;
  gross_savings: number;
  forecast_source: "ml" | "average" | "none";
  period: string;
}

export default function SavingsPanel({ userId }: { userId: string }) {
  const [data, setData] = useState<SavingsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/api/v1/savings/${userId}`);
        if (res.ok) setData(await res.json());
      } catch {}
      setLoading(false);
    })();
  }, [userId]);

  if (loading) {
    return (
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 mb-5 flex items-center justify-center h-24">
        <Loader2 className="animate-spin text-indigo-400" size={24} />
      </div>
    );
  }

  if (!data) return null;

  const isNegative = data.gross_savings <= 0;

  return (
    <motion.div
      className="bg-white rounded-2xl shadow-sm border border-gray-100 mb-5 overflow-hidden"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {/* Header */}
      <div
        className="px-5 py-4 flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shadow-lg ${
            isNegative
              ? "bg-gradient-to-br from-red-400 to-orange-500 shadow-red-200/50"
              : "bg-gradient-to-br from-emerald-400 to-teal-500 shadow-emerald-200/50"
          }`}>
            <TrendingUp size={20} className="text-white" />
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Gross Savings</p>
            <p className={`text-xl font-black ${isNegative ? "text-red-600" : "text-gray-900"}`}>
              {fmtINR(data.gross_savings)}
            </p>
          </div>
        </div>
        {expanded
          ? <ChevronUp size={18} className="text-gray-400" />
          : <ChevronDown size={18} className="text-gray-400" />
        }
      </div>

      {/* Expanded Details */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-4 space-y-2.5">
              {/* Forecast savings */}
              <div className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">Forecast savings</span>
                  {data.forecast_source === "average" && (
                    <span className="text-[10px] font-semibold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
                      using avg
                    </span>
                  )}
                  {data.forecast_source === "none" && (
                    <span className="text-[10px] font-semibold text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                      no data
                    </span>
                  )}
                </div>
                <span className="text-sm font-bold text-gray-900">{fmtINR(data.forecast_savings)}</span>
              </div>

              {/* Hard savings */}
              <div className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-600">Hard savings</span>
                  {data.hard_savings === 0 && (
                    <span className="text-[10px] font-semibold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded flex items-center gap-0.5">
                      <Upload size={8} /> pending upload
                    </span>
                  )}
                </div>
                <span className="text-sm font-bold text-gray-900">{fmtINR(data.hard_savings)}</span>
              </div>

              {/* Period */}
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-gray-400">
                  Period: {data.period === "monthly" ? "This month" : "This week"}
                </span>
              </div>

              {/* Warning when negative */}
              {isNegative && (
                <div className="flex items-center gap-2 px-3 py-2 bg-red-50 rounded-xl">
                  <AlertCircle size={14} className="text-red-500" />
                  <span className="text-xs font-medium text-red-600">
                    No available savings — upload transactions or wait for next cycle
                  </span>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
