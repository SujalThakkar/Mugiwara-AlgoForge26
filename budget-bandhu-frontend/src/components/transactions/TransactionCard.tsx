"use client";

import { CategoryBadge } from "./CategoryBadge";
import { formatCurrency } from "@/lib/utils";
import { AlertCircle } from "lucide-react";

interface Transaction {
    id: string;
    merchant: string;
    amount: number;
    category: string;
    type: 'debit' | 'credit';
    isAnomaly: boolean;
    anomalySeverity?: 'HIGH' | 'MEDIUM' | 'LOW' | 'NORMAL';
    anomalyType?: string;
    anomalyReason?: string;
    anomalyScore?: number;
}

interface TransactionCardProps {
    transaction: Transaction;
}

export function TransactionCard({ transaction }: TransactionCardProps) {
    return (
        <div className="glass p-4 rounded-xl border-2 border-white/50 hover:shadow-lg transition-all duration-200 cursor-pointer">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 flex-1">
                    <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center">
                        <span className="text-lg">🏪</span>
                    </div>
                    <div className="flex-1">
                        <div className="flex items-center gap-2">
                            <h4 className="font-semibold text-gray-900 truncate max-w-[200px]">{transaction.merchant}</h4>
                            {transaction.isAnomaly && (
                                <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-black tracking-tight ${
                                    transaction.anomalySeverity === 'HIGH' ? 'bg-red-500 text-white shadow-sm' :
                                    transaction.anomalySeverity === 'MEDIUM' ? 'bg-orange-500 text-white' :
                                    'bg-amber-400 text-black'
                                }`}>
                                    <AlertCircle className="w-2.5 h-2.5" />
                                    {transaction.anomalySeverity || 'FLAGGED'}
                                </div>
                            )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                            <CategoryBadge category={transaction.category} />
                            {transaction.isAnomaly && transaction.anomalyScore && (
                                <span className="text-[10px] font-bold text-red-600 bg-red-50 px-1.5 rounded-full border border-red-100">
                                    Risk: {(transaction.anomalyScore * 100).toFixed(0)}%
                                </span>
                            )}
                        </div>
                        {transaction.isAnomaly && (transaction.anomalyReason || transaction.anomalyType) && (
                            <div className="mt-2 p-2 bg-red-50/50 rounded-lg border border-red-100/50 flex flex-col gap-1">
                                {transaction.anomalyType && (
                                    <span className="text-[9px] font-black text-red-700 uppercase tracking-tighter leading-none opacity-80">{transaction.anomalyType}</span>
                                )}
                                {transaction.anomalyReason && (
                                    <p className="text-[11px] text-red-800 font-medium leading-tight italic">"{transaction.anomalyReason}"</p>
                                )}
                            </div>
                        )}
                    </div>
                </div>
                <div className="text-right">
                    <div className={`text-lg font-bold ${transaction.type === 'credit' ? 'text-mint-600' : 'text-gray-900'}`}>
                        {transaction.type === 'credit' ? '+' : '-'}{formatCurrency(transaction.amount)}
                    </div>
                </div>
            </div>
        </div>
    );
}
