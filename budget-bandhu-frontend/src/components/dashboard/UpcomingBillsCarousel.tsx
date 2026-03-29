'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Calendar, Zap, Wifi, Phone, Home, CreditCard, ChevronLeft, ChevronRight, Clock, MessageSquare, Loader2 } from 'lucide-react';

// ── Live bill interface (matches Atlas bills collection) ──────────────────────
export interface LiveBill {
    id: string;
    title: string;
    amount: number;
    due_date: string;
    category: string;
    status: 'upcoming' | 'due-soon' | 'overdue' | 'future';
    days_until_due: number;
}

interface UpcomingBillsCarouselProps {
    bills?: LiveBill[];
    loading?: boolean;
}

// ── Category icon mapping ─────────────────────────────────────────────────────
function getCategoryIcon(category: string) {
    const c = (category || '').toLowerCase();
    if (c.includes('electric') || c.includes('power') || c.includes('utilities')) return Zap;
    if (c.includes('internet') || c.includes('wifi') || c.includes('broadband')) return Wifi;
    if (c.includes('phone') || c.includes('mobile') || c.includes('telecom')) return Phone;
    if (c.includes('rent') || c.includes('housing') || c.includes('home')) return Home;
    return CreditCard;
}

function getStatusBadge(status: LiveBill['status'], days: number) {
    if (status === 'overdue') return { text: '🔴 Overdue', bg: 'bg-red-500' };
    if (days <= 2)            return { text: `🟠 ${days}d left`, bg: 'bg-amber-500' };
    if (days <= 7)            return { text: `🟡 ${days} days`, bg: 'bg-yellow-500' };
    return                           { text: `🟢 ${days} days`, bg: 'bg-emerald-500' };
}

// ── Empty state ───────────────────────────────────────────────────────────────
function EmptyBills() {
    return (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 py-6">
            <motion.div
                animate={{ scale: [1, 1.1, 1] }}
                transition={{ repeat: Infinity, duration: 2 }}
                className="w-16 h-16 rounded-2xl bg-white/10 flex items-center justify-center"
            >
                <MessageSquare className="w-8 h-8 text-indigo-200" />
            </motion.div>
            <div className="text-center">
                <p className="text-white font-bold mb-1">No upcoming bills</p>
                <p className="text-indigo-300 text-xs leading-relaxed max-w-[180px]">
                    Tell Bandhu about your bills! Try:<br />
                    <span className="italic text-indigo-200">"I have rent due ₹15,000 on April 1"</span>
                </p>
            </div>
        </div>
    );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export function UpcomingBillsCarousel({ bills = [], loading = false }: UpcomingBillsCarouselProps) {
    const [currentIndex, setCurrentIndex] = useState(0);
    const [direction, setDirection] = useState(0);

    const totalDue = bills.reduce((sum, b) => sum + b.amount, 0);
    const safeIndex = Math.min(currentIndex, Math.max(0, bills.length - 1));

    const nextBill = () => {
        if (bills.length === 0) return;
        setDirection(1);
        setCurrentIndex((prev) => (prev + 1) % bills.length);
    };

    const prevBill = () => {
        if (bills.length === 0) return;
        setDirection(-1);
        setCurrentIndex((prev) => (prev - 1 + bills.length) % bills.length);
    };

    const variants = {
        enter: (dir: number) => ({ x: dir > 0 ? 150 : -150, opacity: 0 }),
        center: { x: 0, opacity: 1 },
        exit:  (dir: number) => ({ x: dir < 0 ? 150 : -150, opacity: 0 }),
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="relative rounded-3xl overflow-hidden h-full min-h-[420px]"
            style={{
                background: 'linear-gradient(145deg, #1E1B4B 0%, #312E81 50%, #3730A3 100%)',
                boxShadow: '0 20px 40px rgba(30, 27, 75, 0.4), 0 0 0 1px rgba(255,255,255,0.05)'
            }}
        >
            <div className="relative z-10 p-6 h-full flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <motion.div
                            initial={{ scale: 0, rotate: -180 }}
                            animate={{ scale: 1, rotate: 0 }}
                            transition={{ delay: 0.5, type: 'spring' }}
                            className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center"
                        >
                            <Calendar className="w-5 h-5 text-white" />
                        </motion.div>
                        <div>
                            <h3 className="text-xl font-bold text-white">Upcoming Bills</h3>
                            <p className="text-sm text-indigo-300">
                                {loading ? 'Loading...' : bills.length > 0 ? `${bills.length} bill${bills.length > 1 ? 's' : ''} pending` : 'No bills yet'}
                            </p>
                        </div>
                    </div>

                    {/* Live badge */}
                    <motion.div
                        initial={{ scale: 0, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: 0.6, type: 'spring' }}
                        className="text-right"
                    >
                        <p className="text-xs text-indigo-300 uppercase tracking-wider">Total Due</p>
                        <p className="text-xl font-bold text-white">
                            ₹{totalDue.toLocaleString('en-IN')}
                        </p>
                    </motion.div>
                </div>

                {/* Content */}
                <div className="flex-1 flex flex-col min-h-0">
                    {loading ? (
                        <div className="flex-1 flex items-center justify-center">
                            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
                                <Loader2 className="w-8 h-8 text-indigo-300" />
                            </motion.div>
                        </div>
                    ) : bills.length === 0 ? (
                        <EmptyBills />
                    ) : (
                        <>
                            {/* Bill Card */}
                            <div className="relative flex-1 overflow-hidden mb-4">
                                <AnimatePresence initial={false} custom={direction} mode="wait">
                                    <motion.div
                                        key={safeIndex}
                                        custom={direction}
                                        variants={variants}
                                        initial="enter"
                                        animate="center"
                                        exit="exit"
                                        transition={{ x: { type: 'spring', stiffness: 300, damping: 30 }, opacity: { duration: 0.15 } }}
                                        className="absolute inset-0 flex flex-col justify-center"
                                    >
                                        {(() => {
                                            const bill = bills[safeIndex];
                                            const Icon = getCategoryIcon(bill.category);
                                            const badge = getStatusBadge(bill.status, bill.days_until_due);
                                            return (
                                                <div className="p-4 rounded-2xl bg-white/10 backdrop-blur-sm border border-white/10">
                                                    <div className="flex items-center gap-3 mb-3">
                                                        <div className="w-10 h-10 rounded-xl bg-indigo-500/30 flex items-center justify-center">
                                                            <Icon className="w-5 h-5 text-indigo-200" />
                                                        </div>
                                                        <div className={`px-3 py-1 rounded-full ${badge.bg} text-white text-xs font-bold`}>
                                                            {badge.text}
                                                        </div>
                                                        <span className="ml-auto text-xs text-indigo-300 px-2 py-1 rounded-lg bg-white/10">
                                                            {bill.category}
                                                        </span>
                                                    </div>
                                                    <h4 className="text-lg font-bold text-white mb-1">{bill.title}</h4>
                                                    <div className="flex items-center gap-2 text-indigo-300 text-sm mb-3">
                                                        <Clock className="w-4 h-4" />
                                                        Due: {new Date(bill.due_date + 'T00:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                                                    </div>
                                                    <div className="text-3xl font-black text-white">
                                                        ₹{bill.amount.toLocaleString('en-IN')}
                                                    </div>
                                                </div>
                                            );
                                        })()}
                                    </motion.div>
                                </AnimatePresence>
                            </div>

                            {/* Navigation dots */}
                            <div className="flex items-center justify-center gap-4 mb-4">
                                <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} onClick={prevBill}
                                    className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center cursor-pointer">
                                    <ChevronLeft className="w-5 h-5 text-white" />
                                </motion.button>
                                <div className="flex items-center gap-2">
                                    {bills.map((_, idx) => (
                                        <button key={idx} onClick={() => { setDirection(idx > safeIndex ? 1 : -1); setCurrentIndex(idx); }} className="group">
                                            <motion.div
                                                className={`h-2 rounded-full transition-all ${idx === safeIndex ? 'w-6 bg-white' : 'w-2 bg-white/30 group-hover:bg-white/50'}`}
                                                whileHover={{ scale: 1.2 }}
                                            />
                                        </button>
                                    ))}
                                </div>
                                <motion.button whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }} onClick={nextBill}
                                    className="w-10 h-10 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center cursor-pointer">
                                    <ChevronRight className="w-5 h-5 text-white" />
                                </motion.button>
                            </div>
                        </>
                    )}

                    {/* Footer CTA */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.9 }}
                        className="mt-auto p-3 rounded-xl bg-white/10 border border-white/10 text-center"
                    >
                        <p className="text-xs text-indigo-300">
                            💬 <span className="text-white font-medium">Tell Bandhu</span> about new bills in the chat →
                        </p>
                    </motion.div>
                </div>
            </div>
        </motion.div>
    );
}
