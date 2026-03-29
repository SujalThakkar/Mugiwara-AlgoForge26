'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { FileText, TrendingUp, AlertCircle, CheckCircle, Plus, Calculator, PiggyBank, Shield } from 'lucide-react';
import { mockData } from '@/lib/api/mock-data';
import { useTranslation } from '@/lib/hooks/useTranslation';
import type { Tax80CData } from '@/lib/api/ml-api';

interface TaxOptimizerDashboardProps {
    taxData?: Tax80CData | null;
}

interface TaxInvestment {
    id: string;
    category: string;
    amount: number;
    limit: number;
    icon: any;
    color: string;
    gradient: string;
    description: string;
}

export function TaxOptimizerDashboard({ taxData }: TaxOptimizerDashboardProps) {
    const { t } = useTranslation();
    const maxLimit80C = 150000;

    // ── Use live Atlas data if available, else fall back to mock ──
    const liveMode = taxData != null;
    const totalInvested = liveMode ? (taxData?.total_invested ?? 0) : (mockData.tax?.investments?.reduce((s, i) => s + i.amount, 0) || 0);
    const remaining     = liveMode ? (taxData?.remaining_limit ?? 0) : Math.max(0, maxLimit80C - totalInvested);
    const percentage    = (totalInvested / maxLimit80C) * 100;
    const taxSaved      = liveMode ? (taxData?.tax_saved ?? 0) : totalInvested * 0.3;
    const potentialSavings = liveMode ? (taxData?.potential_additional_saving ?? 0) : remaining * 0.3;
    const slabRate      = liveMode ? ((taxData?.slab_rate ?? 0.3) * 100).toFixed(0) : '30';

    // Synthesize investment list from live breakdown (or mock)
    const getInvestStyle = (category: string) => {
        const c = category.toUpperCase();
        if (c.includes('PPF'))  return { icon: PiggyBank, gradient: 'from-emerald-500 to-green-600' };
        if (c.includes('ELSS')) return { icon: TrendingUp, gradient: 'from-blue-500 to-cyan-600' };
        if (c.includes('NPS'))  return { icon: Shield, gradient: 'from-purple-500 to-pink-600' };
        if (c.includes('LIC') || c.includes('LIFE')) return { icon: Shield, gradient: 'from-violet-500 to-purple-600' };
        return { icon: FileText, gradient: 'from-gray-500 to-gray-600' };
    };

    const investments = liveMode
        ? Object.entries(taxData?.breakdown ?? {}).map(([cat, data], i) => {
            const style = getInvestStyle(cat);
            return { id: String(i), category: cat.toUpperCase(), amount: data.amount, description: `${data.count} transaction${data.count > 1 ? 's' : ''}`, icon: style.icon, gradient: style.gradient };
          })
        : (mockData.tax?.investments || []).map((inv, i) => {
            const style = getInvestStyle(inv.category);
            return { id: inv.id || String(i), category: inv.category, amount: inv.amount, description: inv.description, icon: style.icon, gradient: style.gradient };
          });

    const noData = investments.length === 0;

    if (!liveMode && (!mockData.tax || !mockData.tax.investments)) {
        return (
            <div className="flex items-center justify-center p-6 h-[300px] bg-white/70 rounded-2xl border border-white/50">
                <p className="text-gray-500 font-medium">{t('accumulating_data')}</p>
            </div>
        );
    }

    const getStatusDetails = () => {
        if (percentage >= 100) return { color: 'text-emerald-600', bg: 'bg-emerald-50', status: t('status_maxed_out') };
        if (percentage >= 75)  return { color: 'text-blue-600',    bg: 'bg-blue-50',    status: t('status_almost_there') };
        if (percentage >= 50)  return { color: 'text-orange-600',  bg: 'bg-orange-50',  status: t('status_good_progress') };
        return                        { color: 'text-red-600',     bg: 'bg-red-50',     status: t('status_needs_attention') };
    };

    const status = getStatusDetails();

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
            className="backdrop-blur-xl bg-white/70 rounded-2xl shadow-xl border border-white/50 p-6"
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center shadow-lg">
                        <FileText className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h3 className="text-xl font-bold text-gray-900">{t('tax_optimizer_title')}</h3>
                        <p className="text-sm text-gray-500">{t('section_80c_deductions')}</p>
                    </div>
                </div>

                {/* Status Badge */}
                <motion.div
                    initial={{ scale: 0, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ delay: 0.8, type: 'spring' }}
                    className={`flex items-center gap-2 px-4 py-2 rounded-full ${status.bg}`}
                >
                    {percentage >= 100 ? (
                        <CheckCircle className={`w-5 h-5 ${status.color}`} />
                    ) : (
                        <AlertCircle className={`w-5 h-5 ${status.color}`} />
                    )}
                    <span className={`font-bold ${status.color}`}>{status.status}</span>
                </motion.div>
            </div>

            {/* Main Progress Section */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                {/* Circular Progress */}
                <div className="flex items-center justify-center">
                    <div className="relative w-64 h-64">
                        {/* SVG Circle */}
                        <svg className="w-full h-full -rotate-90" viewBox="0 0 200 200">
                            {/* Background circle */}
                            <circle
                                cx="100"
                                cy="100"
                                r="85"
                                fill="none"
                                stroke="#E5E7EB"
                                strokeWidth="20"
                            />

                            {/* Progress circle */}
                            <motion.circle
                                cx="100"
                                cy="100"
                                r="85"
                                fill="none"
                                stroke="url(#taxGradient)"
                                strokeWidth="20"
                                strokeLinecap="round"
                                initial={{ pathLength: 0 }}
                                animate={{ pathLength: Math.min(percentage / 100, 1) }}
                                transition={{ duration: 2, delay: 0.5, ease: 'easeOut' }}
                                strokeDasharray={2 * Math.PI * 85}
                            />

                            {/* Gradient definition */}
                            <defs>
                                <linearGradient id="taxGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                    <stop offset="0%" stopColor="#F59E0B" />
                                    <stop offset="100%" stopColor="#EF4444" />
                                </linearGradient>
                            </defs>
                        </svg>

                        {/* Center content */}
                        <motion.div
                            initial={{ scale: 0, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            transition={{ delay: 1.5, type: 'spring' }}
                            className="absolute inset-0 flex flex-col items-center justify-center"
                        >
                            <div className="text-5xl font-black text-gray-900 mb-2">
                                {percentage.toFixed(0)}%
                            </div>
                            <div className="text-sm text-gray-600 font-medium mb-1">
                                ₹{totalInvested.toLocaleString('en-IN')}
                            </div>
                            <div className="text-xs text-gray-500">
                                {t('of_limit_label')} ₹1,50,000
                            </div>
                        </motion.div>
                    </div>
                </div>

                {/* Stats Cards */}
                <div className="space-y-4">
                    {/* Tax Saved */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.9 }}
                        className="p-5 bg-gradient-to-br from-emerald-50 to-green-50 rounded-xl border-2 border-emerald-200"
                    >
                        <div className="flex items-center gap-3 mb-2">
                            <div className="w-10 h-10 rounded-xl bg-emerald-500 flex items-center justify-center shadow-lg">
                                <CheckCircle className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <p className="text-xs text-emerald-700 font-medium">{t('tax_saved_label')}</p>
                            </div>
                        </div>
                        <p className="text-3xl font-black text-emerald-800">
                            ₹{taxSaved.toLocaleString('en-IN')}
                        </p>
                        <p className="text-xs text-emerald-600 mt-1">{slabRate}% {t('slab_bracket_label')} {liveMode ? `(${t('btn_learn_more')})` : ''}</p>
                    </motion.div>

                    {/* Remaining Limit */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 1 }}
                        className="p-5 bg-gradient-to-br from-orange-50 to-red-50 rounded-xl border-2 border-orange-200"
                    >
                        <div className="flex items-center gap-3 mb-2">
                            <div className="w-10 h-10 rounded-xl bg-orange-500 flex items-center justify-center shadow-lg">
                                <Calculator className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <p className="text-xs text-orange-700 font-medium">{t('remaining_limit_label')}</p>
                            </div>
                        </div>
                        <p className="text-3xl font-black text-orange-800">
                            ₹{remaining.toLocaleString('en-IN')}
                        </p>
                        <p className="text-xs text-orange-600 mt-1">
                            {t('save_more_tax_label')} ₹{potentialSavings.toLocaleString('en-IN')}
                        </p>
                    </motion.div>

                    {/* Financial Year */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 1.1 }}
                        className="p-4 bg-blue-50 rounded-xl border border-blue-200"
                    >
                        <div className="flex items-center justify-between">
                            <span className="text-sm font-semibold text-blue-900">{t('fy_label')} 2025-26</span>
                            <span className="text-xs text-blue-600">{t('due_label')}: March 31, 2026</span>
                        </div>
                        <div className="mt-2 h-2 bg-blue-200 rounded-full overflow-hidden">
                            <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: '65%' }}
                                transition={{ duration: 1.5, delay: 1.3 }}
                                className="h-full bg-gradient-to-r from-blue-500 to-cyan-600 rounded-full"
                            />
                        </div>
                        <p className="text-xs text-blue-600 mt-1">65% {t('fy_elapsed_label')}</p>
                    </motion.div>
                </div>
            </div>

            {/* Investment Categories */}
            <div className="mb-6">
                <div className="flex items-center justify-between mb-4">
                    <h4 className="text-lg font-bold text-gray-900">{t('your_investments_title')}</h4>
                    <motion.button
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-orange-500 to-red-600 text-white rounded-xl font-semibold text-sm shadow-lg hover:shadow-xl transition-all"
                    >
                        <Plus className="w-4 h-4" />
                        {t('add_investment_btn')}
                    </motion.button>
                </div>

                <div className="space-y-3">
                {noData ? (
                    <div className="p-6 text-center text-gray-400">
                        <p className="font-medium">{t('no_investments_found')}</p>
                        <p className="text-sm mt-1">{t('auto_appear_msg')}</p>
                    </div>
                ) : (
                    investments.map((inv, index) => {
                        const Icon = inv.icon;
                        const invPercentage = Math.min((inv.amount / maxLimit80C) * 100, 100);

                        return (
                            <motion.div
                                key={inv.id}
                                initial={{ opacity: 0, x: -20 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 1.2 + index * 0.1 }}
                                whileHover={{ x: 5 }}
                                className="p-4 bg-gray-50 rounded-xl border border-gray-200 hover:bg-white hover:border-gray-300 transition-all group"
                            >
                                <div className="flex items-center justify-between mb-3">
                                    <div className="flex items-center gap-3">
                                        <motion.div
                                            whileHover={{ rotate: 10, scale: 1.1 }}
                                            className={`w-11 h-11 rounded-xl bg-gradient-to-br ${inv.gradient} flex items-center justify-center shadow-lg`}
                                        >
                                            <Icon className="w-5 h-5 text-white" />
                                        </motion.div>
                                        <div>
                                            <p className="font-semibold text-gray-900">{inv.category}</p>
                                            <p className="text-xs text-gray-500">{inv.description}</p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-lg font-bold text-gray-900">
                                            ₹{inv.amount.toLocaleString('en-IN')}
                                        </p>
                                        <p className="text-xs text-gray-500">{invPercentage.toFixed(1)}% {t('of_limit_label')}</p>
                                    </div>
                                </div>

                                {/* Progress bar */}
                                <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                                    <motion.div
                                        initial={{ width: 0 }}
                                        animate={{ width: `${invPercentage}%` }}
                                        transition={{ duration: 1, delay: 1.5 + index * 0.1 }}
                                        className={`h-full bg-gradient-to-r ${inv.gradient} rounded-full relative overflow-hidden`}
                                    >
                                        <motion.div
                                            className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent"
                                            animate={{ x: ['-100%', '200%'] }}
                                            transition={{ repeat: Infinity, duration: 2, ease: 'linear', repeatDelay: 1 }}
                                        />
                                    </motion.div>
                                </div>
                            </motion.div>
                        );
                    })
                )}
                </div>
            </div>

            {/* Bottom Recommendation */}
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 2 }}
                className="p-5 bg-gradient-to-r from-orange-50 to-red-50 rounded-xl border border-orange-200"
            >
                <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 flex items-center justify-center flex-shrink-0 shadow-lg">
                        <Calculator className="w-6 h-6 text-white" />
                    </div>
                    <div className="flex-1">
                        <h4 className="font-bold text-gray-900 mb-2">{t('tax_recommendation_title')} 💡</h4>
                        <p className="text-sm text-gray-700 leading-relaxed mb-3">
                            {percentage >= 100 ? (
                                t('tax_rec_maxed')
                            ) : percentage >= 75 ? (
                                <>
                                    {t('tax_rec_close')} ₹
                                    <span className="font-bold text-orange-600">{remaining.toLocaleString('en-IN')}</span>
                                </>
                            ) : (
                                <>
                                    {t('tax_rec_start')} ₹
                                    <span className="font-bold text-orange-600">{remaining.toLocaleString('en-IN')}</span>
                                </>
                            )}
                        </p>
                        <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            className="px-4 py-2 bg-gradient-to-r from-orange-500 to-red-600 text-white rounded-lg font-semibold text-sm shadow-lg hover:shadow-xl transition-all"
                        >
                            {t('explore_options_btn')}
                        </motion.button>
                    </div>
                </div>
            </motion.div>
        </motion.div>
    );
}
