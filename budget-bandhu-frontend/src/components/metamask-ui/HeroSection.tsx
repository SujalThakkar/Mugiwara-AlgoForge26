import HeroRightPanel from '@/components/shared/HeroRightPanel';
import Link from 'next/link';
import { ArrowRight, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import { useTranslation } from '@/lib/hooks/useTranslation';

export function HeroSection() {
    const { t } = useTranslation();

    return (
        <section className="relative overflow-hidden pt-12 pb-20 md:pt-12 md:pb-32">
            <div className="mm-container relative z-10">
                <div className="grid lg:grid-cols-2 gap-12 items-start">
                    {/* Left Side: Text Content */}
                    <motion.div
                        initial={{ opacity: 0, x: -50 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.8 }}
                    >
                        {/* Brand Label */}
                        <motion.div
                            initial={{ opacity: 0, y: -16 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ duration: 0.5, delay: 0.1 }}
                            className="inline-flex items-center gap-2 mb-6"
                        >
                            <span className="inline-flex items-center gap-1.5 bg-mm-purple/10 border border-mm-purple/20 text-mm-purple text-sm font-semibold px-4 py-1.5 rounded-full tracking-wide uppercase">
                                <Sparkles className="w-3.5 h-3.5" />
                                Budget Bandhu
                            </span>
                            <span className="h-px w-8 bg-gradient-to-r from-mm-purple/40 to-transparent" />
                            <span className="text-xs font-medium text-gray-500 tracking-widest uppercase">AI Finance</span>
                        </motion.div>

                        {/* Hero Heading — styled per word */}
                        <h1 className="hero-mega-heading mb-6">
                            <motion.span
                                className="hero-word hero-word--gradient block"
                                initial={{ opacity: 0, x: -40 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.6, delay: 0.2 }}
                            >
                                YOUR WEALTH
                            </motion.span>
                            <motion.span
                                className="hero-word hero-word--outline block"
                                initial={{ opacity: 0, x: -40 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.6, delay: 0.35 }}
                            >
                                IN
                            </motion.span>
                            <motion.span
                                className="hero-word hero-word--accent block"
                                initial={{ opacity: 0, x: -40 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.6, delay: 0.5 }}
                            >
                                CONTROL
                            </motion.span>
                        </h1>

                        <p className="mm-body-lg text-gray-700 mb-8 max-w-lg">
                            {t('hero_subtitle')}
                        </p>

                        <div className="flex flex-col sm:flex-row gap-4">
                            <Link href="/auth/signup" className="mm-btn mm-btn-primary group">
                                {t('btn_get_started')}
                                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                            </Link>

                            <Link href="#features" className="mm-btn mm-btn-secondary">
                                {t('btn_learn_more')}
                            </Link>
                        </div>

                        {/* Stats Row */}
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.4, duration: 0.6 }}
                            className="grid grid-cols-3 gap-8 mt-12 pt-12 border-t border-gray-300"
                        >
                            <div>
                                <div className="text-3xl font-bold text-mm-purple">10K+</div>
                                <div className="text-sm text-gray-600">{t('stats_active_users')}</div>
                            </div>
                            <div>
                                <div className="text-3xl font-bold text-mm-purple">₹500Cr+</div>
                                <div className="text-sm text-gray-600">{t('stats_money_managed')}</div>
                            </div>
                            <div>
                                <div className="text-3xl font-bold text-mm-purple">4.9★</div>
                                <div className="text-sm text-gray-600">{t('stats_rating')}</div>
                            </div>
                        </motion.div>
                    </motion.div>

                    {/* Right Side: New Animated Panel */}
                    <motion.div
                        className="relative overflow-hidden min-h-[520px] lg:pt-14"
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.9, delay: 0.2 }}
                    >
                        <HeroRightPanel />
                    </motion.div>
                </div>
            </div>
        </section>
    );
}
