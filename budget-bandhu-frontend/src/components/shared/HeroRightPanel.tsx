'use client';

import { motion } from 'framer-motion';
import React, { memo } from 'react';
import { Logo3D } from './Logo3D';

// Performance optimization: Define constant arrays outside component
const chips = [
    { symbol: '₹', top: '42%', right: '22%', bg: 'rgba(124,58,237,0.12)', color: '#7c3aed', dur: 7, del: 1.1 },
    { symbol: '%', top: '60%', left: '28%', bg: 'rgba(14,102,106,0.1)', color: '#0e666a', dur: 6, del: 1.6 },
    { symbol: '↑', top: '25%', left: '32%', bg: 'rgba(251,146,60,0.12)', color: '#ea580c', dur: 8, del: 0.8 },
];

const particles = [
    { top: '18%', left: '48%', size: 5, color: 'rgba(124,58,237,0.5)', dur: 5, del: 0 },
    { top: '38%', left: '18%', size: 4, color: 'rgba(14,102,106,0.5)', dur: 6, del: 0.7 },
    { top: '72%', left: '55%', size: 5, color: 'rgba(124,58,237,0.4)', dur: 4.5, del: 1.2 },
    { top: '55%', right: '28%', size: 4, color: 'rgba(45,212,191,0.6)', dur: 7, del: 0.4 },
    { top: '85%', left: '38%', size: 6, color: 'rgba(251,146,60,0.4)', dur: 5.5, del: 2 },
    { top: '10%', right: '35%', size: 4, color: 'rgba(106,75,159,0.5)', dur: 6.5, del: 1.8 },
    { top: '30%', left: '62%', size: 3, color: 'rgba(14,102,106,0.4)', dur: 4, del: 0.9 },
    { top: '65%', right: '42%', size: 5, color: 'rgba(124,58,237,0.3)', dur: 5.8, del: 1.5 },
    { top: '8%', left: '50%', size: 7, color: '#7c3aed', dur: 6, del: 0 },
    { top: '50%', left: '5%', size: 7, color: '#0e666a', dur: 7, del: 1 },
    { bottom: '5%', left: '50%', size: 7, color: '#ea580c', dur: 5, del: 2 },
];

const GridTexture = () => (
    <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `
      linear-gradient(rgba(124,58,237,0.06) 1px, transparent 1px),
      linear-gradient(90deg, rgba(124,58,237,0.06) 1px, transparent 1px)`,
        backgroundSize: '32px 32px',
        pointerEvents: 'none', zIndex: 0,
        borderRadius: '24px',
    }} />
);

const GlowOrbs = () => (
    <>
        <motion.div
            style={{
                position: 'absolute', top: '50%', left: '50%',
                width: '260px', height: '260px', borderRadius: '50%',
                background: 'radial-gradient(circle at 40% 40%, rgba(124,58,237,0.18), rgba(14,102,106,0.12) 40%, transparent 70%)',
                filter: 'blur(30px)', x: '-50%', y: '-50%', zIndex: 1,
                willChange: 'transform, opacity',
            }}
            animate={{ scale: [1, 1.18, 1], opacity: [0.7, 1, 0.7] }}
            transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        />
        <motion.div
            style={{
                position: 'absolute', top: '12%', right: '18%',
                width: '120px', height: '120px', borderRadius: '50%',
                background: 'radial-gradient(circle at 40% 40%, rgba(124,58,237,0.18), rgba(14,102,106,0.12) 40%, transparent 70%)',
                filter: 'blur(30px)', zIndex: 1,
                willChange: 'transform, opacity',
            }}
            animate={{ scale: [1.18, 1, 1.18], opacity: [1, 0.7, 1] }}
            transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut', delay: 1.2 }}
        />
    </>
);

const ConcentricRings = () => (
    <>
        {[200, 300, 400].map((size, i) => (
            <motion.div
                key={size}
                style={{
                    position: 'absolute', top: '50%', left: '50%',
                    width: size, height: size,
                    borderRadius: '50%',
                    border: `1px ${size === 300 ? 'dashed' : 'solid'} rgba(124,58,237,0.1)`,
                    x: '-50%', y: '-50%',
                    zIndex: 2,
                    willChange: 'transform, opacity',
                }}
                animate={{ scale: [1, 1.04, 1], opacity: [0.4, 0.8, 0.4] }}
                transition={{
                    duration: 6, repeat: Infinity, ease: 'easeInOut',
                    delay: i * 0.5
                }}
            />
        ))}
    </>
);

const SymbolChips = () => (
    <>
        {chips.map((chip) => (
            <motion.div
                key={chip.symbol}
                style={{
                    position: 'absolute', width: '36px', height: '36px',
                    borderRadius: '50%', display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                    background: chip.bg, color: chip.color,
                    fontSize: '15px', fontWeight: 800,
                    top: chip.top,
                    ...(chip.right ? { right: chip.right } : { left: chip.left }),
                    zIndex: 15, willChange: 'transform, opacity',
                }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: [0, -12, 0], rotate: [0, 8, 0] }}
                transition={{
                    opacity: { duration: 0.5, delay: chip.del },
                    y: {
                        duration: chip.dur, repeat: Infinity, ease: 'easeInOut',
                        delay: chip.del
                    },
                    rotate: {
                        duration: chip.dur, repeat: Infinity, ease: 'easeInOut',
                        delay: chip.del
                    },
                }}
            >
                {chip.symbol}
            </motion.div>
        ))}
    </>
);

const Particles = () => (
    <>
        {particles.map((p, i) => (
            <motion.div
                key={i}
                style={{
                    position: 'absolute', borderRadius: '50%',
                    width: `${p.size}px`, height: `${p.size}px`,
                    background: p.color, willChange: 'transform, opacity',
                    ...(p.top ? { top: p.top } : { bottom: p.bottom }),
                    ...(p.left ? { left: p.left } : { right: p.right }),
                }}
                animate={{ y: [0, -18, 0], scale: [1, 1.4, 1], opacity: [0.5, 1, 0.5] }}
                transition={{
                    duration: p.dur, repeat: Infinity,
                    ease: 'easeInOut', delay: p.del,
                }}
            />
        ))}
    </>
);

const FloatingCards = () => {
    const cardBaseStyle: React.CSSProperties = {
        position: 'absolute', zIndex: 20,
        background: 'rgba(255,255,255,0.82)',
        backdropFilter: 'blur(20px)',
        border: '1px solid rgba(255,255,255,0.95)',
        borderRadius: '18px',
        boxShadow: '0 8px 32px rgba(0,0,0,0.08), 0 1px 0 rgba(255,255,255,1) inset',
        padding: '14px 18px',
    };

    return (
        <>
            {/* CARD A — Financial Score */}
            <motion.div
                style={{ ...cardBaseStyle, top: '7%', right: '6%', minWidth: '170px', willChange: 'transform, opacity' }}
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: 1, x: 0, y: [0, -10, 0] }}
                transition={{
                    opacity: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.3 },
                    x: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.3 },
                    y: { duration: 5, repeat: Infinity, ease: 'easeInOut', delay: 1.0 }
                }}
            >
                <div style={{
                    fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
                    textTransform: 'uppercase', color: '#8b8aa8',
                    display: 'flex', alignItems: 'center', gap: 5
                }}>
                    <motion.span style={{
                        width: 6, height: 6, borderRadius: '50%',
                        background: '#7c3aed', display: 'inline-block'
                    }}
                        animate={{
                            boxShadow: ['0 0 0 0 rgba(124,58,237,0.4)',
                                '0 0 0 5px rgba(124,58,237,0)', '0 0 0 0 rgba(124,58,237,0.4)']
                        }}
                        transition={{ duration: 2, repeat: Infinity }}
                    />
                    ML Insight
                </div>
                <div style={{ fontSize: 10, color: '#8b8aa8', marginBottom: 2 }}>Financial Score</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: '#2d1b6b', lineHeight: 1 }}>
                    782 <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 700 }}>▲ 12</span>
                </div>
                <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 8px',
                    borderRadius: 999, background: 'rgba(22,163,74,0.1)', color: '#16a34a',
                    marginTop: 4, display: 'inline-block'
                }}>Excellent</span>
            </motion.div>

            {/* CARD B — AI Forecast */}
            <motion.div
                style={{ ...cardBaseStyle, bottom: '14%', left: '3%', minWidth: '180px', willChange: 'transform, opacity' }}
                initial={{ opacity: 0, x: -40 }}
                animate={{ opacity: 1, x: 0, y: [0, -12, 0] }}
                transition={{
                    opacity: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.5 },
                    x: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.5 },
                    y: { duration: 6, repeat: Infinity, ease: 'easeInOut', delay: 1.2 }
                }}
            >
                <div style={{
                    fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
                    textTransform: 'uppercase', color: '#8b8aa8',
                    display: 'flex', alignItems: 'center', gap: 5
                }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#7c3aed', display: 'inline-block' }} />
                    AI FORECAST
                </div>
                <div style={{ fontSize: 10, color: '#8b8aa8', marginBottom: 2 }}>Savings Potential (Mar)</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#2d1b6b', lineHeight: 1 }}>₹42,000</div>
                <div style={{ width: '100%', height: 5, background: 'rgba(124,58,237,0.1)', borderRadius: 99, marginTop: 8, overflow: 'hidden' }}>
                    <motion.div
                        initial={{ width: '0%' }}
                        animate={{ width: '76%' }}
                        transition={{ duration: 1.5, ease: [0.22, 1, 0.36, 1], delay: 1 }}
                        style={{ height: '100%', borderRadius: 99, background: 'linear-gradient(90deg,#7c3aed,#2dd4bf)' }}
                    />
                </div>
                <div style={{ fontSize: 10, color: '#8b8aa8', marginTop: 4 }}>76% of monthly target</div>
            </motion.div>

            {/* CARD C — Savings Streak */}
            <motion.div
                style={{ ...cardBaseStyle, top: '9%', left: '5%', padding: '10px 14px', willChange: 'transform, opacity' }}
                initial={{ opacity: 0, x: -40 }}
                animate={{ opacity: 1, x: 0, y: [0, -8, 0] }}
                transition={{
                    opacity: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.7 },
                    x: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.7 },
                    y: { duration: 4.5, repeat: Infinity, ease: 'easeInOut', delay: 1.4 }
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                    <span style={{ fontSize: 14 }}>🔥</span>
                    <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#8b8aa8' }}>STREAK</span>
                </div>
                <div style={{ fontSize: 15, fontWeight: 800, color: '#2d1b6b' }}>5 Day Savings!</div>
                <div style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 999, background: 'rgba(124,58,237,0.1)', color: '#7c3aed', marginTop: 4, display: 'inline-block' }}>Budget Ninja 🥷</div>
            </motion.div>

            {/* CARD D — Spending Trend */}
            <motion.div
                style={{ ...cardBaseStyle, bottom: '10%', right: '5%', padding: '12px 16px', minWidth: '150px', willChange: 'transform, opacity' }}
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: 1, x: 0, y: [0, -9, 0] }}
                transition={{
                    opacity: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.9 },
                    x: { duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.9 },
                    y: { duration: 5.5, repeat: Infinity, ease: 'easeInOut', delay: 1.6 }
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 6 }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ea580c', display: 'inline-block' }} />
                    <span style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#8b8aa8' }}>SPENDING TREND</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'flex-end', height: 28, gap: 3, marginBottom: 4 }}>
                    {['40%', '60%', '45%', '85%', '55%', '95%', '70%'].map((h, i) => (
                        <motion.div
                            key={i}
                            initial={{ scaleY: 0 }}
                            animate={{ scaleY: 1 }}
                            style={{
                                width: 7, height: h, borderRadius: '3px 3px 0 0',
                                backgroundColor: ['#c4b5fd', '#a78bfa', '#c4b5fd', '#7c3aed', '#a78bfa', '#5b21b6', '#7c3aed'][i],
                                transformOrigin: 'bottom'
                            }}
                            transition={{ duration: 0.5, delay: 1 + i * 0.06, ease: [0.22, 1, 0.36, 1] }}
                        />
                    ))}
                </div>
                <div style={{ fontSize: 10, fontWeight: 700, color: '#16a34a' }}>↓ 4.7% vs last week</div>
            </motion.div>
        </>
    );
};

const HeroRightPanel = memo(function HeroRightPanel() {
    return (
        <div style={{
            position: 'relative',
            width: '100%',
            height: '520px',
            overflow: 'hidden',
            borderRadius: '24px',
            background: 'linear-gradient(135deg, #fdf4ee 0%, #f5e8f5 50%, #eef4fd 100%)',
        }}>
            <GridTexture />
            <GlowOrbs />
            <ConcentricRings />

            {/* PIGGY SHADOW */}
            <motion.div
                style={{
                    position: 'absolute', bottom: '30%', left: '50%',
                    x: '-50%', width: '120px', height: '16px',
                    borderRadius: '50%',
                    background: 'rgba(124,58,237,0.12)',
                    filter: 'blur(8px)', zIndex: 5,
                    willChange: 'transform, opacity',
                }}
                animate={{ scaleX: [1, 0.7, 0.85, 1], opacity: [0.6, 0.3, 0.45, 0.6] }}
                transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
            />

            {/* PIGGY CENTER */}
            <motion.div
                style={{
                    position: 'absolute', top: '50%', left: '50%',
                    x: '-50%', y: '-52%',
                    width: '220px', height: '220px',
                    zIndex: 10, willChange: 'transform',
                }}
                animate={{
                    y: ['-52%', 'calc(-52% - 14px)', '-52%'],
                    rotate: [-2, 2, -2],
                }}
                transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
            >
                <Logo3D heroMode={true} />
            </motion.div>

            <SymbolChips />
            <Particles />
            <FloatingCards />
        </div>
    );
});

export default HeroRightPanel;
