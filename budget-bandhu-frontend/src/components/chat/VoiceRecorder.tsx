"use client";

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, MicOff, Send, Globe, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { translateText, VOICE_LANGUAGES } from '@/lib/utils/translate';

interface VoiceRecorderProps {
    onTranscript: (original: string, translated: string, gcode: string) => void;
    disabled?: boolean;
}

export function VoiceRecorder({ onTranscript, disabled }: VoiceRecorderProps) {
    const [isRecording, setIsRecording] = useState(false);
    const [duration, setDuration] = useState(0);
    const [transcript, setTranscript] = useState('');
    const [selectedLang, setSelectedLang] = useState(VOICE_LANGUAGES[0]); // Default: Hindi/English
    const [isLangMenuOpen, setIsLangMenuOpen] = useState(false);
    const [isTranslating, setIsTranslating] = useState(false);

    const timerRef = useRef<NodeJS.Timeout | null>(null);
    const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
    const recognitionRef = useRef<any>(null);

    // Update recognition language when selection changes
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
            if (SpeechRecognition) {
                if (recognitionRef.current) {
                    recognitionRef.current.stop(); // Stop current if running
                }
                recognitionRef.current = new SpeechRecognition();
                recognitionRef.current.continuous = true;
                recognitionRef.current.interimResults = true;
                recognitionRef.current.lang = selectedLang.code;

                recognitionRef.current.onresult = (event: any) => {
                    // Reset silence timer
                    if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
                    silenceTimerRef.current = setTimeout(stopRecording, 5000);

                    let interimTranscript = '';
                    let finalTranscript = '';

                    for (let i = event.resultIndex; i < event.results.length; i++) {
                        const transcript = event.results[i][0].transcript;
                        if (event.results[i].isFinal) {
                            finalTranscript += transcript + ' ';
                        } else {
                            interimTranscript += transcript;
                        }
                    }

                    setTranscript(finalTranscript || interimTranscript);
                };

                recognitionRef.current.onerror = (event: any) => {
                    console.error('Speech recognition error:', event.error);
                    if (event.error === 'not-allowed') {
                        alert("Microphone permission denied. Please enable it in your browser settings.");
                    } else if (event.error === 'network') {
                        alert("Network error. Please check your connection.");
                    }
                    stopRecording();
                };
            }
        }

        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [selectedLang]);

    const startRecording = () => {
        if (!recognitionRef.current) {
            // Fallback: Notify user or simulate (user asked for fallback)
            alert("Speech recognition is not supported in this browser. Try Chrome.");
            return;
        }

        try {
            recognitionRef.current.start();
            setIsRecording(true);
            setTranscript('');
            setDuration(0);

            timerRef.current = setInterval(() => {
                setDuration(d => d + 1);
            }, 1000);
        } catch (error) {
            console.error('Failed to start recording:', error);
        }
    };

    const stopRecording = async () => {
        if (recognitionRef.current) {
            try {
                recognitionRef.current.stop();
            } catch (error) {
                console.error('Failed to stop recording:', error);
            }
        }

        if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
        }

        setIsRecording(false);
        setDuration(0);

        if (transcript.trim()) {
            setIsTranslating(true);
            // Translate to English before sending
            const translated = await translateText(transcript.trim(), selectedLang.gcode, 'en');
            onTranscript(transcript.trim(), translated, selectedLang.gcode);
            setTranscript('');
            setIsTranslating(false);
        }
    };

    const formatDuration = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="flex items-center gap-2">
            {/* Language Selection Dropdown */}
            <div className="relative">
                <button
                    onClick={() => setIsLangMenuOpen(!isLangMenuOpen)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/50 hover:bg-slate-700 rounded-lg text-slate-300 text-xs font-medium border border-slate-700 transition-colors"
                >
                    <Globe className="w-3.5 h-3.5 text-emerald-400" />
                    {selectedLang.name.split(' ')[0]}
                    <ChevronDown className={`w-3 h-3 transition-transform ${isLangMenuOpen ? 'rotate-180' : ''}`} />
                </button>

                <AnimatePresence>
                    {isLangMenuOpen && (
                        <motion.div
                            initial={{ opacity: 0, y: 5 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 5 }}
                            className="absolute bottom-full left-0 mb-2 w-40 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl overflow-hidden z-50 py-1"
                        >
                            {VOICE_LANGUAGES.map((lang) => (
                                <button
                                    key={lang.code}
                                    onClick={() => {
                                        setSelectedLang(lang);
                                        setIsLangMenuOpen(false);
                                    }}
                                    className={`w-full text-left px-3 py-2 text-xs transition-colors ${selectedLang.code === lang.code
                                            ? 'bg-emerald-600/20 text-emerald-400'
                                            : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                                        }`}
                                >
                                    {lang.name}
                                </button>
                            ))}
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Recording Modal/Indicator */}
            <AnimatePresence>
                {isRecording && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-md p-4"
                        onClick={stopRecording}
                    >
                        <motion.div
                            initial={{ y: 20 }}
                            animate={{ y: 0 }}
                            className="bg-slate-900 border border-emerald-500/30 rounded-[2.5rem] p-10 max-w-sm w-full shadow-[0_0_50px_rgba(16,185,129,0.2)]"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex flex-col items-center mb-8">
                                <motion.div
                                    className="relative w-28 h-28 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-full flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(16,185,129,0.4)]"
                                    animate={{
                                        scale: [1, 1.05, 1],
                                        boxShadow: [
                                            "0 0 30px rgba(16,185,129,0.4)",
                                            "0 0 60px rgba(16,185,129,0.6)",
                                            "0 0 30px rgba(16,185,129,0.4)"
                                        ]
                                    }}
                                    transition={{
                                        duration: 2,
                                        repeat: Infinity,
                                        ease: "easeInOut",
                                    }}
                                >
                                    <Mic className="w-14 h-14 text-white" />

                                    {/* Rotating Rings */}
                                    {[0, 1, 2].map((i) => (
                                        <motion.div
                                            key={i}
                                            className="absolute inset-0 rounded-full border border-emerald-500/30"
                                            initial={{ scale: 1, opacity: 0.6 }}
                                            animate={{
                                                scale: [1, 2.2, 2.8],
                                                opacity: [0.6, 0.2, 0],
                                            }}
                                            transition={{
                                                duration: 2.5,
                                                repeat: Infinity,
                                                delay: i * 0.5,
                                                ease: "easeOut",
                                            }}
                                        />
                                    ))}
                                </motion.div>

                                <h3 className="text-2xl font-black text-white tracking-tight mb-2 uppercase">Listening...</h3>
                                <div className="flex items-center gap-2 mb-4">
                                    <Globe className="w-4 h-4 text-emerald-400" />
                                    <span className="text-emerald-400 font-mono text-sm tracking-widest">{selectedLang.name}</span>
                                </div>
                                <div className="text-4xl font-mono font-black text-white/90 mb-4 bg-slate-800/50 px-6 py-2 rounded-2xl border border-slate-700">
                                    {formatDuration(duration)}
                                </div>
                                <p className="text-sm text-slate-500 font-medium">Click button to stop and translate</p>
                            </div>

                            {/* Live Text Preview with subtle animation */}
                            <AnimatePresence>
                                {transcript && (
                                    <motion.div
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="p-5 bg-black/40 border border-slate-800 rounded-3xl mb-8 relative overflow-hidden group"
                                    >
                                        <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>
                                        <p className="text-sm text-slate-300 leading-relaxed font-medium italic italic">"{transcript}"</p>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            <button
                                onClick={stopRecording}
                                className="w-full h-16 bg-white text-black font-black uppercase tracking-tighter rounded-full hover:bg-emerald-400 transition-all shadow-xl flex items-center justify-center gap-3 text-lg"
                            >
                                <div className="w-6 h-6 border-2 border-black/20 rounded-sm flex items-center justify-center">
                                    <div className="w-2.5 h-2.5 bg-black rounded-sm group-hover:bg-black transition-colors"></div>
                                </div>
                                STOP RECORDING
                            </button>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Translation Progress Indicator */}
            {isTranslating && (
                <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[100] bg-emerald-600 text-white px-6 py-3 rounded-full shadow-2xl flex items-center gap-3 animate-bounce">
                    <Globe className="w-5 h-5 animate-spin" />
                    <span className="font-bold text-sm tracking-widest uppercase">Translating to English...</span>
                </div>
            )}

            {/* Mic Toggle Button */}
            <button
                onClick={isRecording ? stopRecording : startRecording}
                disabled={disabled || isTranslating}
                className={`p-3 rounded-xl transition-all relative group flex items-center justify-center ${isRecording
                        ? 'bg-emerald-500 text-white animate-pulse'
                        : 'bg-slate-800/50 text-slate-400 hover:bg-slate-700 hover:text-emerald-400 border border-slate-700'
                    }`}
            >
                {isRecording ? (
                    <Mic className="w-5 h-5" />
                ) : (
                    <Mic className="w-5 h-5 group-hover:scale-110 transition-transform" />
                )}
                {isRecording && (
                    <span className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full border-2 border-slate-950 animate-ping"></span>
                )}
            </button>
        </div>
    );
}
