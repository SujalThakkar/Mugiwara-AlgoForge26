"use client";

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, MicOff, Send, Globe, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { translateText, VOICE_LANGUAGES } from '@/lib/utils/translate';

import { createPortal } from 'react-dom';

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
    const [mounted, setMounted] = useState(false);

    const timerRef = useRef<NodeJS.Timeout | null>(null);
    const silenceTimerRef = useRef<NodeJS.Timeout | null>(null);
    const recognitionRef = useRef<any>(null);

    useEffect(() => {
        setMounted(true);
    }, []);

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
            onTranscript(transcript.trim(), translated, selectedLang.code);
            setTranscript('');
            setIsTranslating(false);
        }
    };

    const formatDuration = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const modalContent = (
        <AnimatePresence>
            {isRecording && (
                <>
                    {/* Darker localized Backdrop for focus */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-[100000] bg-black/60 backdrop-blur-md pointer-events-auto"
                        onClick={stopRecording}
                    />
                    
                    <motion.div
                        initial={{ y: -100, opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        exit={{ y: -100, opacity: 0 }}
                        className="fixed top-[15%] left-1/2 -translate-x-1/2 z-[100001] w-[90%] max-w-sm pointer-events-auto"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="bg-[#0f172a] border-2 border-emerald-500/50 rounded-[3rem] p-10 shadow-[0_0_80px_rgba(16,185,129,0.4)] relative overflow-hidden">
                            <div className="flex flex-col items-center">
                                <motion.div
                                    className="relative w-28 h-28 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-full flex items-center justify-center mb-8 shadow-[0_0_30px_rgba(16,185,129,0.4)]"
                                    animate={{
                                        scale: [1, 1.05, 1],
                                        boxShadow: ["0 0 30px rgba(16,185,129,0.4)", "0 0 60px rgba(16,185,129,0.6)", "0 0 30px rgba(16,185,129,0.4)"]
                                    }}
                                    transition={{ duration: 2, repeat: Infinity }}
                                >
                                    <Mic className="w-12 h-12 text-white" />
                                    
                                    <motion.div
                                        className="absolute inset-0 rounded-full border-4 border-emerald-400/40"
                                        animate={{ scale: [1, 1.6], opacity: [0.6, 0] }}
                                        transition={{ duration: 1.5, repeat: Infinity }}
                                    />
                                </motion.div>

                                <h3 className="text-2xl font-black text-white mb-2 uppercase tracking-widest">Listening</h3>
                                <div className="flex items-center gap-2 mb-6">
                                    <Globe className="w-4 h-4 text-emerald-400" />
                                    <span className="text-emerald-400 font-mono text-sm font-black tracking-tighter">{selectedLang.name.toUpperCase()}</span>
                                </div>
                                
                                <div className="text-5xl font-mono font-black text-white mb-8 tabular-nums">
                                    {formatDuration(duration)}
                                </div>

                                <AnimatePresence>
                                    {transcript && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 10 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="w-full p-6 bg-black/40 border border-emerald-500/20 rounded-3xl mb-8 max-h-40 overflow-y-auto custom-scrollbar"
                                        >
                                            <p className="text-sm sm:text-base text-slate-200 italic text-center font-medium leading-relaxed">
                                                "{transcript}"
                                            </p>
                                        </motion.div>
                                    )}
                                </AnimatePresence>

                                <button
                                    onClick={stopRecording}
                                    className="w-full py-5 bg-white text-black font-black uppercase tracking-[0.2em] rounded-2xl transition-all shadow-xl flex items-center justify-center gap-3 active:scale-95 hover:bg-emerald-400 hover:text-white"
                                >
                                    <div className="w-5 h-5 bg-black rounded-sm group-hover:bg-white" />
                                    STOP RECORDING
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );

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

            {/* Render Modal via Portal to avoid clipping by parent backdrop-filters */}
            {mounted && createPortal(modalContent, document.body)}

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
