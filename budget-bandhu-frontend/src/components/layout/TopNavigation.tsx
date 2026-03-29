'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    LayoutDashboard,
    Wallet,
    Target,
    GraduationCap,
    MessageSquare,
    User,
    Menu,
    X,
    ChevronDown
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { LanguageSelector } from '@/components/shared/LanguageSelector';
import { useTranslation } from '@/lib/hooks/useTranslation';
import { TranslationKey } from '@/lib/translations';

const navItems: { href?: string; label: TranslationKey; icon: any; submenu?: { href: string; label: TranslationKey }[] }[] = [
    { href: '/', label: 'nav_dashboard', icon: LayoutDashboard },
    { href: '/budget', label: 'nav_budget', icon: Wallet },
    { href: '/transactions', label: 'nav_transactions', icon: null },
    { href: '/goals', label: 'nav_goals', icon: Target },
    {
        label: 'nav_learn_finance',
        icon: GraduationCap,
        submenu: [
            { href: '/literacy', label: 'nav_literacy' },
            { href: '/literacy/calculators/sip', label: 'calc_sip' },
            { href: '/literacy/calculators/tax', label: 'calc_tax' },
        ]
    },
    { href: '/chat', label: 'nav_ai_chat', icon: MessageSquare },
];

export function TopNavigation() {
    const { t } = useTranslation();
    const pathname = usePathname();
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
    const [openSubmenu, setOpenSubmenu] = useState<string | null>(null);

    const isActive = (href: string) => pathname === href;
    const isChatPage = pathname === '/chat';

    return (
        <nav className={`sticky top-0 z-[100] transition-all duration-300 ${isChatPage
            ? 'bg-transparent backdrop-blur-md border-b border-white/10'
            : 'bg-white shadow-sm border-b border-gray-100'
            }`}>
            <div className="mm-container">
                <div className="flex items-center justify-between h-16">
                    {/* Logo */}
                    <Link href="/" className="flex items-center gap-3 whitespace-nowrap min-w-max overflow-visible">
                        <div className="w-10 h-10 bg-gradient-to-br from-mm-purple to-mm-lavender rounded-xl flex items-center justify-center shrink-0">
                            <span className="text-white font-bold text-xl">BB</span>
                        </div>
                        <span className={`font-display font-bold text-lg whitespace-nowrap ${isChatPage ? 'text-white' : 'text-mm-purple'}`}>
                            Budget Bandhu
                        </span>
                    </Link>

                    {/* Desktop Navigation */}
                    <div className="hidden lg:flex items-center gap-1">
                        {navItems.map((item, index) => (
                            <div key={index} className="relative">
                                {item.submenu ? (
                                    <div
                                        className="relative"
                                        onMouseEnter={() => setOpenSubmenu(item.label)}
                                        onMouseLeave={() => setOpenSubmenu(null)}
                                    >
                                        <button className={`flex items-center gap-1 px-4 py-2 rounded-full transition-colors whitespace-nowrap ${isChatPage
                                            ? 'text-white hover:bg-white/10'
                                            : 'text-mm-black hover:bg-gray-50'
                                            }`}>
                                            {item.icon && <item.icon className="w-4 h-4" />}
                                            <span className="whitespace-nowrap">{t(item.label)}</span>
                                            <ChevronDown className="w-4 h-4" />
                                        </button>

                                        <AnimatePresence>
                                            {openSubmenu === item.label && (
                                                <motion.div
                                                    initial={{ opacity: 0, y: -10 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    exit={{ opacity: 0, y: -10 }}
                                                    transition={{ duration: 0.2 }}
                                                    className="absolute top-full left-0 mt-2 w-48 bg-white rounded-2xl shadow-lg border border-gray-100 py-2"
                                                >
                                                    {item.submenu.map((subItem, subIndex) => (
                                                        <Link
                                                            key={subIndex}
                                                            href={subItem.href}
                                                            className="block px-4 py-3 text-sm text-mm-black hover:bg-gray-50 transition-colors"
                                                        >
                                                            {t(subItem.label)}
                                                        </Link>
                                                    ))}
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>
                                ) : (
                                    <Link
                                        href={item.href || '#'}
                                        className={`flex items-center gap-2 px-4 py-2 rounded-full transition-colors whitespace-nowrap ${(item.href && isActive(item.href))
                                            ? 'bg-mm-purple text-white'
                                            : isChatPage
                                                ? 'text-white hover:bg-white/10'
                                                : 'text-mm-black hover:bg-gray-50'
                                            }`}
                                    >
                                        {item.icon && <item.icon className="w-4 h-4" />}
                                        <span className="whitespace-nowrap">{t(item.label)}</span>
                                    </Link>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Right Side Actions */}
                    <div className="hidden lg:flex items-center gap-4">
                        <LanguageSelector />

                        <Link href="/profile" className={`p-2 rounded-full transition-colors ${isChatPage ? 'hover:bg-white/10' : 'hover:bg-gray-50'}`}>
                            <User className={`w-5 h-5 ${isChatPage ? 'text-white' : 'text-mm-black'}`} />
                        </Link>

                        <Link href="/auth/login" className="mm-btn mm-btn-primary whitespace-nowrap px-5">
                            {t('btn_get_started')}
                        </Link>
                    </div>

                    {/* Mobile Menu Button */}
                    <button
                        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                        className="lg:hidden p-2 rounded-full hover:bg-gray-50 transition-colors"
                    >
                        {mobileMenuOpen ? (
                            <X className="w-6 h-6 text-mm-black" />
                        ) : (
                            <Menu className="w-6 h-6 text-mm-black" />
                        )}
                    </button>
                </div>
            </div>

            {/* Mobile Menu */}
            <AnimatePresence>
                {mobileMenuOpen && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.3 }}
                        className="lg:hidden border-t border-gray-100"
                    >
                        <div className="mm-container py-4 space-y-2">
                            <div className="px-4 pb-4">
                                <LanguageSelector />
                            </div>
                            {navItems.map((item, index) => (
                                <div key={index}>
                                    {item.submenu ? (
                                        <div>
                                            <button
                                                onClick={() => setOpenSubmenu(openSubmenu === item.label ? null : item.label)}
                                                className="flex items-center justify-between w-full px-4 py-3 rounded-xl text-mm-black hover:bg-gray-50 transition-colors"
                                            >
                                                <span className="flex items-center gap-2">
                                                    {item.icon && <item.icon className="w-5 h-5" />}
                                                    {t(item.label)}
                                                </span>
                                                <ChevronDown className={`w-5 h-5 transition-transform ${openSubmenu === item.label ? 'rotate-180' : ''}`} />
                                            </button>

                                            <AnimatePresence>
                                                {openSubmenu === item.label && (
                                                    <motion.div
                                                        initial={{ opacity: 0, height: 0 }}
                                                        animate={{ opacity: 1, height: 'auto' }}
                                                        exit={{ opacity: 0, height: 0 }}
                                                        className="pl-8 space-y-1 mt-1"
                                                    >
                                                        {item.submenu.map((subItem, subIndex) => (
                                                            <Link
                                                                key={subIndex}
                                                                href={subItem.href}
                                                                onClick={() => setMobileMenuOpen(false)}
                                                                className="block px-4 py-2 rounded-lg text-sm text-mm-black hover:bg-gray-50 transition-colors"
                                                            >
                                                                {t(subItem.label)}
                                                            </Link>
                                                        ))}
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </div>
                                    ) : (
                                        <Link
                                            href={item.href || '#'}
                                            onClick={() => setMobileMenuOpen(false)}
                                            className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-colors ${(item.href && isActive(item.href))
                                                ? 'bg-mm-purple text-white'
                                                : 'text-mm-black hover:bg-gray-50'
                                                }`}
                                        >
                                            {item.icon && <item.icon className="w-5 h-5" />}
                                            <span>{t(item.label)}</span>
                                        </Link>
                                    )}
                                </div>
                            ))}

                            <Link
                                href="/auth/login"
                                onClick={() => setMobileMenuOpen(false)}
                                className="mm-btn mm-btn-primary w-full mt-4 whitespace-nowrap"
                            >
                                {t('btn_get_started')}
                            </Link>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </nav>
    );
}
