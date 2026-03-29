"use client";

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { SuggestedQueries } from '@/components/chat/SuggestedQueries';
import { VoiceRecorder } from '@/components/chat/VoiceRecorder';
import { TypingIndicator } from '@/components/chat/TypingIndicator';
import { FinanceAdvisor3D } from '@/components/chat/FinanceAdvisor3D';
import { ChatMessage } from '@/lib/types/chat';
import { Logo3D } from '@/components/shared/Logo3D';
import { Send, Mic, Camera, TrendingUp, PiggyBank, Target } from 'lucide-react';
import { useUserStore } from '@/lib/store/useUserStore';
import { mlApi } from '@/lib/api/ml-api';
import { useTranslation } from '@/lib/hooks/useTranslation';
import { motion, AnimatePresence } from 'framer-motion';
import { translateText } from '@/lib/utils/translate';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Quick Action Items
const quickActions = [
    { id: 'budget', label: 'Check my budget', icon: PiggyBank },
    { id: 'invest', label: 'Investment Tips', icon: TrendingUp, emergency: false },
    { id: 'goals', label: 'My Savings Goals', icon: Target },
];

export default function ChatPage() {
    const router = useRouter();
    const { userId, isLoggedIn } = useUserStore();
    const { currentLanguage, t, translate } = useTranslation();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [isTyping, setIsTyping] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [sessionId, setSessionId] = useState<string | undefined>(undefined);

    const [selectedLanguage, setSelectedLanguage] = useState('en'); // Defaults to English but updated by VoiceRecorder

    const [isTranslating, setIsTranslating] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Voice Settings
    const ELEVEN_LABS_API_KEY = 'ea21421a4314844a637bb85f41e670833a8f97a813fc6692a014c2c7fa72ff1e';
    const ELEVEN_LABS_VOICE_ID = '8i52rsySWGYoU4SRQCex';

    // Text-to-Speech Engine (ULTRA-STABLE FOR PRESENTATION)
    const speak = (text: string, langCode: string) => {
        if (typeof window === 'undefined' || !window.speechSynthesis) return;

        // 1. Clean up Text (Very Important)
        const cleanText = text
            .replace(/[\*\_\#\!\>\[\]\(\)\`]/g, '') // Remove MD chars
            .replace(/\n+/g, ' ')                  // Newlines to spaces
            .replace(/\//g, ' ')                   // Strip problematic slashes
            .trim();

        if (!cleanText) return;

        // 2. Language Optimization
        let targetLang = langCode;
        if (langCode.startsWith('hi')) targetLang = 'hi-IN';
        else if (langCode.startsWith('mr')) targetLang = 'mr-IN';
        else if (langCode.startsWith('gu')) targetLang = 'gu-IN';
        else if (langCode.startsWith('bn')) targetLang = 'bn-IN';
        else if (langCode.startsWith('ta')) targetLang = 'ta-IN';
        else if (langCode.startsWith('te')) targetLang = 'te-IN';
        else if (langCode.startsWith('kn')) targetLang = 'kn-IN';
        else if (langCode.startsWith('ml')) targetLang = 'ml-IN';

        // 3. Prepare the utterance
        const speakNow = () => {
            window.speechSynthesis.cancel();
            
            const utterance = new SpeechSynthesisUtterance(cleanText);
            utterance.lang = targetLang;

            const voices = window.speechSynthesis.getVoices();
            
            // Intelligent Voice Selection
            // Priority: 1. Exact BCP-47 match, 2. Base code match (e.g. 'mr'), 3. Default
            const baseCode = targetLang.split('-')[0];
            let selectedVoice = voices.find(v => v.lang === targetLang) || 
                               voices.find(v => v.lang.startsWith(baseCode)) || 
                               null;

            // English specific high-quality search
            if (!selectedVoice && targetLang.startsWith('en')) {
                selectedVoice = voices.find(v => v.name.includes('Google')) || voices[0];
            }

            if (selectedVoice) utterance.voice = selectedVoice;

            utterance.pitch = 1.0;
            utterance.rate = 1.0;
            utterance.volume = 1.0;

            utterance.onstart = () => setIsSpeaking(true);
            utterance.onend = () => setIsSpeaking(false);
            utterance.onerror = () => setIsSpeaking(false);

            window.speechSynthesis.speak(utterance);
        };

        // 4. Handle Voice Loading
        if (window.speechSynthesis.getVoices().length === 0) {
            window.speechSynthesis.onvoiceschanged = () => {
                window.speechSynthesis.onvoiceschanged = null; // Prevent multi-calls
                speakNow();
            };
        } else {
            speakNow();
        }
    };

    // Keep this for future ElevenLabs testing if needed, but not as primary
    const speakElevenLabs = async (text: string, langCode: string) => {
        // Disabled for presentation stability
        console.warn("ElevenLabs disabled for stability. Using native browser TTS.");
        speak(text, langCode);
    };

    // Chat initialization and history logic handles guest/demo users automatically

    // Load chat history
    useEffect(() => {

        const loadHistory = async () => {
            const activeUserId = userId || 'demo_user';
            try {
                const history = await mlApi.chat.getHistory(activeUserId);
                if (history && history.length > 0) {
                    setMessages(history);
                    return;
                }
            } catch (err) {
                console.error('Failed to load history:', err);
            }

            // Fallback to welcome message if no history
            const welcomeText = t('ai_welcome_msg');
            
            setMessages([{
                id: 'welcome',
                role: 'assistant',
                content: welcomeText,
                timestamp: new Date().toISOString(),
                type: 'text',
            }]);
        };
        loadHistory();
    }, [userId]); // Removed translate dependency to avoid infinite loops if it changes

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isTyping]);

    const handleSend = async (text?: string, isVoiceData: boolean = false, voiceTranslatedText?: string, voiceLang?: string) => {
        // STATE MANAGEMENT
        let originalText = text || input;
        let englishText = voiceTranslatedText || "";
        let lang = voiceLang || selectedLanguage;

        if (!originalText.trim() || isTyping) return;
        
        const activeUserId = userId || 'demo_user';

        // 1. UI DISPLAY (USER MESSAGE)
        // Immediately display originalText in chat UI
        const userMessage: ChatMessage = {
            id: `msg_${Date.now()}`,
            role: 'user',
            content: originalText, // DO NOT display translated English here
            timestamp: new Date().toISOString(),
            type: 'text',
        };

        setMessages(prev => [...prev, userMessage]);
        setInput('');
        setIsTyping(true);

        try {
            // 2. TRANSLATION (FOR BACKEND ONLY)
            if (!isVoiceData && !lang.startsWith('en')) {
                setIsTranslating(true);
                try {
                    const gcode = lang.split('-')[0];
                    englishText = await translateText(originalText, gcode, 'en');
                } catch (e) {
                    console.error('Manual input translation failed:', e);
                    englishText = originalText; // Fallback
                } finally {
                    setIsTranslating(false);
                }
            } else if (!isVoiceData && lang.startsWith('en')) {
                englishText = originalText;
            }

            // 3. SEND TO BACKEND (Payload uses translated_text)
            const payload = {
                original_text: originalText,
                translated_text: englishText,
                language: lang
            };

            const response = await mlApi.chat.send(activeUserId, payload, sessionId);

            // Update session ID if returned
            if (response.session_id) {
                setSessionId(response.session_id);
            }

            // 4. BACKEND RESPONSE is in English: response.response
            const responseTextEnglish = response.response;

            // 5. TRANSLATE RESPONSE back to user's language
            let responseTextUserLang = responseTextEnglish;
            if (!lang.startsWith('en')) {
                setIsTranslating(true);
                try {
                    const gcode = lang.split('-')[0];
                    responseTextUserLang = await translateText(responseTextEnglish, 'en', gcode);
                } catch (translationError) {
                    console.error('AI Response Translation failed:', translationError);
                    responseTextUserLang = responseTextEnglish; // Fallback: show English as backup
                } finally {
                    setIsTranslating(false);
                }
            }

            // 6. UI DISPLAY (BOT MESSAGE)
            // Show ONLY responseTextUserLang
            const aiMessage: ChatMessage = {
                id: `msg_${Date.now()}_ai`,
                role: 'assistant',
                content: responseTextUserLang,
                timestamp: new Date().toISOString(),
                type: 'text',
                metadata: {
                    confidence: response.confidence
                }
            };

            setMessages(prev => [...prev, aiMessage]);

            // 7. TEXT TO SPEECH (IMPORTANT)
            speak(responseTextUserLang, lang);

        } catch (error) {
            console.error('Chat error:', error);
            const errorMsg = "Sorry, I'm having trouble connecting to the brain. Please try again.";
            let translatedError = errorMsg;
            if (lang !== 'en') {
                translatedError = await translateText(errorMsg, 'en', lang);
            }

            setMessages(prev => [...prev, {
                id: `err_${Date.now()}`,
                role: 'assistant',
                content: translatedError,
                timestamp: new Date().toISOString(),
                type: 'text'
            }]);
        } finally {
            setIsTyping(false);
            setIsTranslating(false);
        }
    };

    const handleVoiceTranscript = (original: string, translated: string, langCode: string) => {
        // langCode is 'hi-IN', 'mr-IN', etc.
        // gcode for translation is 'hi', 'mr', etc.
        const gcode = langCode.split('-')[0];
        
        setSelectedLanguage(langCode);
        
        // Pass both original and translated to handleSend
        handleSend(original, true, translated, langCode);
    };

    const handleQuickAction = (actionId: string) => {
        const actionMessages: Record<string, string> = {
            budget: "What's my current budget status?",
            invest: "Give me some investment tips",
            goals: "Show me my savings goals",
        };
        handleSend(actionMessages[actionId] || actionId);
    };

    return (
        <>
            <Logo3D />
            <div className="chat-page-bg h-screen overflow-hidden flex flex-col">
            {/* Header / Nav would go here, but focusing on page content */}

            <div className="chat-split-layout flex-1 flex overflow-hidden">
                {/* Left Side - Chat Area */}
                <div className="chat-area flex-1 flex flex-col bg-slate-900/90 backdrop-blur-sm relative">

                    {/* Messages Container */}
                    <div className="chat-messages-container flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar">
                        {messages.map((message) => (
                            <div
                                key={message.id}
                                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[80%] rounded-2xl p-4 shadow-lg ${message.role === 'user'
                                        ? 'bg-emerald-600 text-white rounded-tr-none'
                                        : 'bg-slate-800 text-gray-100 rounded-tl-none border border-slate-700'
                                        }`}
                                >
                                    <div className="prose prose-sm prose-invert max-w-none prose-p:leading-relaxed prose-p:mb-2 prose-ul:my-1 prose-li:my-0 text-current prose-strong:text-emerald-300">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                                    </div>

                                    <div className="flex items-center justify-end mt-2 gap-2 opacity-60">
                                        <span className="text-[10px]">
                                            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        ))}

                        {isTyping && (
                            <div className="flex flex-col gap-2">
                                <div className="flex justify-start">
                                    <div className="bg-slate-800 rounded-2xl p-4 rounded-tl-none border border-slate-700">
                                        <TypingIndicator />
                                    </div>
                                </div>
                                {isTranslating && (
                                    <motion.div 
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        className="text-[10px] text-emerald-400 font-mono ml-4 flex items-center gap-2"
                                    >
                                        <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-ping" />
                                        TRANSLATING...
                                    </motion.div>
                                )}
                            </div>
                        )}

                        <div ref={messagesEndRef} />
                    </div>

                    {/* Quick Action Items - Fixed Quick Actions */}
                    <div className="chat-quick-actions p-4 flex gap-2 overflow-x-auto custom-scrollbar">
                        {quickActions.map((action) => (
                            <button
                                key={action.id}
                                onClick={() => handleQuickAction(action.id)}
                                className="flex items-center gap-2 px-4 py-2 bg-slate-800/80 hover:bg-emerald-600/20 hover:border-emerald-500/50 text-slate-300 hover:text-emerald-400 rounded-xl border border-slate-700/50 text-xs sm:text-sm whitespace-nowrap transition-all group"
                                disabled={isTyping}
                            >
                                <action.icon className="w-4 h-4 group-hover:scale-110 transition-transform" />
                                {action.label}
                            </button>
                        ))}
                    </div>

                    {/* Input Area */}
                    <div className="chat-input-area p-4 bg-slate-950/80 backdrop-blur-md border-t border-slate-800/50">
                        <div className="chat-input-box flex items-center gap-2 bg-slate-900/50 rounded-2xl p-2 border border-slate-800 focus-within:border-emerald-500/30 transition-all shadow-inner">
                            <input
                                ref={inputRef}
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyPress={(e) => e.key === 'Enter' && handleSend()}
                                placeholder={t('ai_input_placeholder')}
                                disabled={isTyping}
                                className="flex-1 bg-transparent border-none focus:ring-0 text-white placeholder-slate-600 px-4"
                            />

                            <VoiceRecorder onTranscript={handleVoiceTranscript} disabled={isTyping} />

                            <button
                                onClick={() => handleSend()}
                                disabled={!input.trim() || isTyping}
                                className="p-3 bg-gradient-to-br from-emerald-600 to-teal-700 rounded-xl text-white hover:from-emerald-500 hover:to-teal-600 disabled:opacity-30 disabled:grayscale transition-all shadow-lg active:scale-95"
                            >
                                <Send className="w-5 h-5" />
                            </button>
                        </div>

                        <p className="text-center text-[10px] text-slate-600 mt-3 font-medium uppercase tracking-widest opacity-50">
                            Powered by Phi-3.5 • Multilingual Engine Active
                        </p>
                    </div>
                </div>

                {/* Right Side - Finance Advisor 3D Panel */}
                <div className="chat-advisor-panel hidden md:flex flex-col w-[380px] bg-black border-l border-slate-800/50 relative overflow-hidden">
                    {/* Background Detail */}
                    <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/5 blur-[100px] rounded-full -mr-32 -mt-32" />
                    <div className="absolute bottom-0 left-0 w-64 h-64 bg-purple-500/5 blur-[100px] rounded-full -ml-32 -mb-32" />

                    {/* 3D Finance Advisor */}
                    <div className="flex-1 relative flex items-center justify-center">
                        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(16,185,129,0.05)_0%,transparent_70%)]" />
                        <FinanceAdvisor3D isThinking={isTyping || isTranslating} isSpeaking={isSpeaking} />
                    </div>

                    {/* Status Indicator Panel */}
                    <div className="p-8 border-t border-slate-800/50 bg-slate-950/50 backdrop-blur-sm">
                        <div className="flex flex-col gap-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className={`w-2.5 h-2.5 rounded-full ${
                                        isTranslating ? 'bg-blue-400 animate-pulse' :
                                        isTyping ? 'bg-amber-400 animate-pulse' : 
                                        isSpeaking ? 'bg-emerald-500 shadow-[0_0_10px_#10b981]' : 
                                        'bg-slate-600'
                                    }`} />
                                    <span className="text-slate-400 font-bold font-mono uppercase tracking-[0.2em] text-[10px]">
                                        {isTranslating ? 'Translating' : isTyping ? 'Thinking' : isSpeaking ? 'Speaking' : 'Standby'}
                                    </span>
                                </div>
                                <div className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[9px] text-slate-500 font-mono">
                                    v3.5L
                                </div>
                            </div>

                            {/* Activity Progress Bar */}
                            {(isTyping || isTranslating || isSpeaking) && (
                                <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                                    <motion.div 
                                        className={`h-full ${isTranslating ? 'bg-blue-500' : isSpeaking ? 'bg-emerald-500' : 'bg-amber-500'}`}
                                        animate={{
                                            x: ["-100%", "100%"]
                                        }}
                                        transition={{
                                            duration: 1.5,
                                            repeat: Infinity,
                                            ease: "linear"
                                        }}
                                        style={{ width: '40%' }}
                                    />
                                </div>
                            )}

                            <div className="flex items-center gap-2 text-slate-500 text-[10px] font-medium italic">
                                <span>Selected:</span>
                                <span className={selectedLanguage !== 'en' ? 'text-emerald-400 not-italic font-bold' : ''}>
                                    {selectedLanguage.toUpperCase()}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        </>
    );
}
