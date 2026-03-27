'use client';

import { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Globe, Loader2 } from 'lucide-react';
import { useSpeechToText } from '@/lib/hooks/useSpeechToText';

interface VoiceInputProps {
    onTranscript: (transcript: string, language: string) => void;
    isProcessing?: boolean;
}

export function VoiceInput({ onTranscript, isProcessing = false }: VoiceInputProps) {
    const [selectedLanguage, setSelectedLanguage] = useState('hi-IN');
    const [showLanguages, setShowLanguages] = useState(false);
    const latestTranscriptRef = useRef('');

    const {
        isRecording,
        transcript,
        error,
        start,
        stop,
        reset,
    } = useSpeechToText({
        lang: selectedLanguage,
        continuous: false,
        interimResults: true,
        onResult: (value) => {
            latestTranscriptRef.current = value;
        },
        onEnd: () => {
            const finalTranscript = latestTranscriptRef.current || transcript;
            if (finalTranscript) {
                onTranscript(finalTranscript, selectedLanguage);
                latestTranscriptRef.current = '';
                reset();
            }
        },
    });

    const languages = [
        { code: 'hi-IN', name: 'Hindi' },
        { code: 'mr-IN', name: 'Marathi' },
        { code: 'ta-IN', name: 'Tamil' },
        { code: 'te-IN', name: 'Telugu' },
        { code: 'bn-IN', name: 'Bengali' },
        { code: 'gu-IN', name: 'Gujarati' },
        { code: 'kn-IN', name: 'Kannada' },
        { code: 'ml-IN', name: 'Malayalam' },
        { code: 'pa-IN', name: 'Punjabi' },
        { code: 'en-US', name: 'English' },
    ];

    const currentLangName = languages.find((language) => language.code === selectedLanguage)?.name || 'Language';

    return (
        <div className="relative flex items-center gap-2">
            <div className="relative">
                <button
                    onClick={() => setShowLanguages(!showLanguages)}
                    className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-500 hover:text-mm-purple transition-colors bg-gray-50 rounded-lg border border-gray-100"
                    type="button"
                >
                    <Globe className="w-3 h-3" />
                    <span>{currentLangName}</span>
                </button>

                <AnimatePresence>
                    {showLanguages && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 10 }}
                            className="absolute bottom-full left-0 mb-2 w-32 bg-white rounded-xl shadow-xl border border-gray-100 overflow-hidden z-[100]"
                        >
                            <div className="max-h-48 overflow-y-auto">
                                {languages.map((language) => (
                                    <button
                                        key={language.code}
                                        onClick={() => {
                                            setSelectedLanguage(language.code);
                                            setShowLanguages(false);
                                        }}
                                        className={`w-full text-left px-3 py-2 text-xs hover:bg-gray-50 transition-colors ${selectedLanguage === language.code ? 'text-mm-purple font-bold bg-mm-purple/5' : 'text-gray-600'}`}
                                        type="button"
                                    >
                                        {language.name}
                                    </button>
                                ))}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            <div className="relative">
                <motion.button
                    whileTap={{ scale: 0.9 }}
                    onClick={isRecording ? stop : start}
                    disabled={isProcessing}
                    className={`p-2 rounded-lg transition-all duration-300 relative overflow-hidden ${isRecording ? 'bg-red-500 text-white shadow-lg shadow-red-200' : isProcessing ? 'bg-gray-100 text-gray-400' : 'bg-mm-purple/10 text-mm-purple hover:bg-mm-purple hover:text-white'}`}
                    type="button"
                >
                    {isProcessing ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                        <Mic className={`w-4 h-4 ${isRecording ? 'animate-pulse' : ''}`} />
                    )}
                </motion.button>

                {isRecording && (
                    <div className="absolute top-1/2 left-full ml-3 -translate-y-1/2 flex items-center gap-1 h-4">
                        {[1, 2, 3, 4].map((index) => (
                            <motion.div
                                key={index}
                                animate={{ height: [4, 16, 4] }}
                                transition={{
                                    repeat: Infinity,
                                    duration: 0.5,
                                    delay: index * 0.1,
                                }}
                                className="w-1 bg-red-400 rounded-full"
                            />
                        ))}
                    </div>
                )}
            </div>

            {error && (
                <div className="absolute bottom-full right-0 mb-2 p-2 bg-red-50 text-red-500 text-[10px] rounded-lg border border-red-100 whitespace-nowrap">
                    {error}
                </div>
            )}
        </div>
    );
}
