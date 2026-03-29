'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { ArrowRight, PiggyBank, ShieldCheck, Sparkles, Wallet } from 'lucide-react';

export function HeroSection() {
    return (
        <div className="mm-container px-8 py-16 w-full max-w-7xl mx-auto">
            <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="space-y-8">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-flex items-center gap-2 rounded-full bg-white/70 px-4 py-2 text-sm font-bold text-mm-purple shadow-lg"
                    >
                        <Sparkles className="h-4 w-4" />
                        Budget Bandhu AI
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.08 }}
                        className="space-y-5"
                    >
                        <h1 className="mm-mega-heading max-w-4xl">
                            Smart budgeting,
                            <br />
                            faster decisions,
                            <br />
                            calmer money.
                        </h1>
                        <p className="max-w-2xl text-lg leading-8 text-mm-black/70 md:text-xl">
                            Track transactions, talk to your finance assistant, and get ML-backed nudges
                            across budgets, goals, anomalies, and spending patterns.
                        </p>
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, y: 24 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.16 }}
                        className="flex flex-wrap gap-4"
                    >
                        <Link href="/transactions" className="mm-btn mm-btn-primary text-base">
                            Open Transactions
                            <ArrowRight className="h-4 w-4" />
                        </Link>
                        <Link href="/goals" className="mm-btn mm-btn-secondary text-base">
                            View Goals
                        </Link>
                    </motion.div>
                </div>

                <motion.div
                    initial={{ opacity: 0, scale: 0.96 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.2 }}
                    className="grid gap-4 sm:grid-cols-2"
                >
                    <FeatureCard
                        icon={Wallet}
                        title="Track Everything"
                        description="Manual entry, CSV imports, receipts, and chat-powered transaction logging."
                    />
                    <FeatureCard
                        icon={PiggyBank}
                        title="Budget Better"
                        description="See category pressure early and get recommendation-driven allocations."
                    />
                    <FeatureCard
                        icon={ShieldCheck}
                        title="Catch Anomalies"
                        description="Spot risky or unusual transactions before they quietly snowball."
                    />
                    <FeatureCard
                        icon={Sparkles}
                        title="Talk Naturally"
                        description="Use voice or text to ask what changed, what’s risky, and what to do next."
                    />
                </motion.div>
            </div>
        </div>
    );
}

function FeatureCard({
    icon: Icon,
    title,
    description,
}: {
    icon: typeof Wallet;
    title: string;
    description: string;
}) {
    return (
        <div className="mm-card min-h-[180px] border border-white/60 bg-white/80 p-6">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-mm-purple/10 text-mm-purple">
                <Icon className="h-6 w-6" />
            </div>
            <h3 className="mb-2 text-xl font-bold text-mm-black">{title}</h3>
            <p className="text-sm leading-6 text-mm-black/65">{description}</p>
        </div>
    );
}
