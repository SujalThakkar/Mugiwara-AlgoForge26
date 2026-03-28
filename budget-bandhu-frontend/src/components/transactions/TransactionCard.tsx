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
                            <h4 className="font-semibold text-gray-900">{transaction.merchant}</h4>
                            {transaction.isAnomaly && (
                                <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold ${
                                    transaction.anomalySeverity === 'HIGH' ? 'bg-red-100 text-red-700' :
                                    transaction.anomalySeverity === 'MEDIUM' ? 'bg-orange-100 text-orange-700' :
                                    'bg-yellow-100 text-yellow-700'
                                }`}>
                                    <AlertCircle className="w-3 h-3" />
                                    ⚠ {transaction.anomalySeverity || 'ANOMALY'}
                                </div>
                            )}
                        </div>
                        <CategoryBadge category={transaction.category} />
                        {transaction.isAnomaly && (transaction.anomalyReason || transaction.anomalyType) && (
                            <div className="mt-1 flex flex-col gap-0.5">
                                {transaction.anomalyType && (
                                    <span className="text-[10px] font-bold text-red-700 uppercase tracking-widest">{transaction.anomalyType}</span>
                                )}
                                {transaction.anomalyReason && (
                                    <p className="text-xs text-red-600 italic leading-snug">{transaction.anomalyReason}</p>
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
