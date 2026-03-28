'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    X,
    Send,
    Sparkles,
    Calculator,
    CheckCircle,
    MessageCircle,
    Brain,
    Loader2,
    ExternalLink,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { useUserStore } from '@/lib/store/useUserStore';
import { mlApi } from '@/lib/api/ml-api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface AILearningModalProps {
    topic: {
        id: string;
        title: string;
        description: string;
        icon: any;
        gradient: string;
    };
    isOpen: boolean;
    onClose: () => void;
}

interface Message {
    id: string;
    role: 'user' | 'ai';
    content: string;
    suggestions?: string[];
    calculatorLink?: { name: string; href: string; amount?: number };
}

export function AILearningModal({ topic, isOpen, onClose }: AILearningModalProps) {
    const router = useRouter();
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputValue, setInputValue] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const { userId } = useUserStore();
    const activeUserId = userId || "demo_user";

    useEffect(() => {
        if (isOpen) {
            const fetchLesson = async () => {
                setIsLoading(true);
                try {
                    const sessionId = `lesson_${Date.now()}`;
                    const res = await mlApi.literacy.getLesson(activeUserId, topic.title, 'beginner', sessionId);
                    const lessonText = `**${res.lesson.title}**\n\n${res.lesson.content}\n\n**Example specific to you:**\n> ${res.lesson.personalized_example}\n\n**Key Takeaways:**\n${res.lesson.key_points.map((kp: string) => `• ${kp}`).join('\n')}\n\nLet me know if you have any questions or want to see a quiz!`;
                    
                    const greeting: Message = {
                        id: '1',
                        role: 'ai',
                        content: lessonText,
                        suggestions: [
                            'Generate a quiz',
                            'Show an example',
                            'Tell me more',
                        ],
                    };
                    setMessages([greeting]);
                } catch (e) {
                    setMessages([{ id: '1', role: 'ai', content: 'Could not load lesson right now.' }]);
                } finally {
                    setIsLoading(false);
                }
            };
            fetchLesson();
        } else {
            setMessages([]);
        }
    }, [isOpen, topic, activeUserId]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSendMessage = async () => {
        if (!inputValue.trim()) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: inputValue,
        };

        setMessages((prev) => [...prev, userMessage]);
        const currentInput = inputValue;
        setInputValue('');
        setIsLoading(true);

        try {
            const sessionId = `lesson_${Date.now()}`;
            const chatResponse = await mlApi.chat.send(activeUserId, currentInput, sessionId);
            const aiResponse: Message = {
                id: Date.now().toString(),
                role: 'ai',
                content: chatResponse.response,
            };
            setMessages((prev) => [...prev, aiResponse]);
        } catch (error) {
            setMessages((prev) => [...prev, {
                id: Date.now().toString(),
                role: 'ai',
                content: "Sorry, I couldn't reach the AI server right now."
            }]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSuggestionClick = (suggestion: string) => {
        setInputValue(suggestion);
    };

    const handleCalculatorClick = (href: string) => {
        toast.success('Opening calculator with your data!');
        router.push(href);
        onClose();
    };

    if (!isOpen) return null;

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={onClose}
        >
            <motion.div
                initial={{ scale: 0.9, y: 20 }}
                animate={{ scale: 1, y: 0 }}
                exit={{ scale: 0.9, y: 20 }}
                onClick={(e) => e.stopPropagation()}
                className="w-full max-w-4xl h-[80vh] backdrop-blur-xl bg-white/90 rounded-3xl shadow-2xl border border-white/50 flex flex-col overflow-hidden"
            >
                {/* Header */}
                <div className={`p-6 bg-gradient-to-r ${topic.gradient} text-white`}>
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-xl bg-white/20 backdrop-blur-sm flex items-center justify-center">
                                <Brain className="w-6 h-6" />
                            </div>
                            <div>
                                <h2 className="text-2xl font-bold">{topic.title}</h2>
                                <p className="text-sm opacity-90">AI-Powered Learning Session</p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="w-10 h-10 rounded-xl bg-white/20 backdrop-blur-sm hover:bg-white/30 transition-colors flex items-center justify-center"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                {/* Messages */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
                    {messages.map((message) => (
                        <div
                            key={message.id}
                            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div
                                className={`max-w-[80%] rounded-2xl p-4 ${message.role === 'user'
                                        ? 'bg-gradient-to-r from-emerald-500 to-blue-500 text-white'
                                        : 'bg-white/70 border border-gray-200'
                                    }`}
                            >
                                {message.role === 'ai' && (
                                    <div className="flex items-center gap-2 mb-2">
                                        <Sparkles className="w-4 h-4 text-emerald-600" />
                                        <span className="text-xs font-semibold text-emerald-600">AI Assistant</span>
                                    </div>
                                )}
                                <div className={`prose prose-sm max-w-none prose-p:leading-relaxed prose-p:mb-2 prose-ul:my-1 prose-li:my-0 ${message.role === 'user' ? 'text-white prose-strong:text-emerald-100' : 'text-gray-800 prose-strong:text-emerald-600'}`}>
                                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                                </div>

                                {/* Calculator Link */}
                                {message.calculatorLink && (
                                    <motion.button
                                        whileHover={{ scale: 1.02 }}
                                        whileTap={{ scale: 0.98 }}
                                        onClick={() => handleCalculatorClick(message.calculatorLink!.href)}
                                        className="mt-4 w-full flex items-center justify-between px-4 py-3 bg-gradient-to-r from-emerald-500 to-blue-500 text-white rounded-xl hover:shadow-lg transition-all"
                                    >
                                        <div className="flex items-center gap-2">
                                            <Calculator className="w-5 h-5" />
                                            <span className="font-semibold">{message.calculatorLink.name}</span>
                                        </div>
                                        <ExternalLink className="w-4 h-4" />
                                    </motion.button>
                                )}

                                {/* Suggestions */}
                                {message.suggestions && message.suggestions.length > 0 && (
                                    <div className="mt-4 flex flex-wrap gap-2">
                                        {message.suggestions.map((suggestion, idx) => (
                                            <button
                                                key={idx}
                                                onClick={() => handleSuggestionClick(suggestion)}
                                                className="px-3 py-1.5 bg-emerald-50 text-emerald-700 rounded-lg text-sm font-medium hover:bg-emerald-100 transition-colors"
                                            >
                                                {suggestion}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}

                    {isLoading && (
                        <div className="flex justify-start">
                            <div className="bg-white/70 border border-gray-200 rounded-2xl p-4">
                                <div className="flex items-center gap-2">
                                    <Loader2 className="w-5 h-5 text-emerald-600 animate-spin" />
                                    <span className="text-sm text-gray-600">AI is thinking...</span>
                                </div>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} />
                </div>

                {/* Input */}
                <div className="p-4 bg-white/50 border-t border-gray-200">
                    <div className="flex items-center gap-3">
                        <input
                            type="text"
                            value={inputValue}
                            onChange={(e) => setInputValue(e.target.value)}
                            onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                            placeholder="Ask me anything about this topic..."
                            className="flex-1 px-4 py-3 rounded-xl border border-gray-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition-all bg-white/70"
                        />
                        <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={handleSendMessage}
                            disabled={!inputValue.trim() || isLoading}
                            className="px-6 py-3 rounded-xl bg-gradient-to-r from-emerald-500 to-blue-500 text-white font-semibold shadow-lg hover:shadow-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            <Send className="w-5 h-5" />
                            Send
                        </motion.button>
                    </div>
                </div>
            </motion.div>
        </motion.div>
    );
}
