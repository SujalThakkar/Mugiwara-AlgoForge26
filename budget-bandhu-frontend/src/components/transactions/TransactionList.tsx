"use client";

import { useState } from "react";
import { TransactionCard } from "./TransactionCard";
import { formatRelativeTime } from "@/lib/utils";
import { List, AlertCircle } from "lucide-react";

interface Transaction {
    id: string;
    date: string;
    merchant: string;
    amount: number;
    category: string;
    type: 'debit' | 'credit';
    isAnomaly: boolean;
    anomalySeverity?: string;
    anomalyReason?: string;
    anomalyScore?: number;
}

interface TransactionListProps {
    transactions: Transaction[];
}

export function TransactionList({ transactions }: TransactionListProps) {
    const [activeTab, setActiveTab] = useState<'all' | 'suspicious'>('all');

    // Filter based on tab
    const filteredTxns = activeTab === 'all' 
        ? transactions 
        : transactions.filter(t => t.isAnomaly);

    // Group transactions by date
    const groupedTransactions = filteredTxns.reduce((acc, txn) => {
        const dateLabel = formatRelativeTime(txn.date);
        if (!acc[dateLabel]) {
            acc[dateLabel] = [];
        }
        acc[dateLabel].push(txn);
        return acc;
    }, {} as Record<string, Transaction[]>);

    return (
        <div className="space-y-6">
            {/* 50/50 Tab Switcher */}
            <div className="flex p-1 bg-gray-100/50 backdrop-blur-sm rounded-xl border border-gray-200">
                <button
                    onClick={() => setActiveTab('all')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-bold transition-all duration-200 rounded-lg ${
                        activeTab === 'all' 
                            ? 'bg-white text-indigo-600 shadow-sm ring-1 ring-black/5' 
                            : 'text-gray-500 hover:text-gray-700'
                    }`}
                >
                    <List size={16} />
                    All History ({transactions.length})
                </button>
                <button
                    onClick={() => setActiveTab('suspicious')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-bold transition-all duration-200 rounded-lg ${
                        activeTab === 'suspicious' 
                            ? 'bg-red-50 text-red-600 shadow-sm ring-1 ring-red-200/50' 
                            : 'text-gray-500 hover:text-red-500'
                    }`}
                >
                    <AlertCircle size={16} />
                    Suspicious ({transactions.filter(t => t.isAnomaly).length})
                </button>
            </div>

            {Object.keys(groupedTransactions).length === 0 ? (
                <div className="text-center py-12 bg-white rounded-2xl border border-dashed border-gray-300">
                    <p className="text-gray-500 font-medium">No transactions found in this view.</p>
                </div>
            ) : (
                Object.entries(groupedTransactions).map(([date, txns]) => (
                    <div key={date}>
                        <h3 className="text-sm font-semibold text-gray-600 mb-3 sticky top-0 bg-gray-50/80 backdrop-blur-md py-2 z-10 px-1">
                            {date}
                        </h3>
                        <div className="space-y-2">
                            {txns.map((txn) => (
                                <TransactionCard key={txn.id} transaction={txn as any} />
                            ))}
                        </div>
                    </div>
                ))
            )}
        </div>
    );
}
