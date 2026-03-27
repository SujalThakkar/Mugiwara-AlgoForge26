import { useState, useEffect, useRef, useCallback } from 'react';

interface UseSpeechToTextOptions {
    lang?: string;
    continuous?: boolean;
    interimResults?: boolean;
    onResult?: (transcript: string) => void;
    onError?: (error: string) => void;
    onEnd?: () => void;
}

interface SpeechRecognitionAlternativeLike {
    transcript: string;
}

interface SpeechRecognitionResultLike {
    0: SpeechRecognitionAlternativeLike;
    length: number;
    [index: number]: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike extends Event {
    resultIndex: number;
    results: {
        length: number;
        [index: number]: SpeechRecognitionResultLike;
    };
}

interface SpeechRecognitionErrorEventLike extends Event {
    error: string;
}

interface SpeechRecognitionInstance {
    lang: string;
    continuous: boolean;
    interimResults: boolean;
    onresult: ((event: SpeechRecognitionEventLike) => void) | null;
    onstart: (() => void) | null;
    onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
    onend: (() => void) | null;
    start: () => void;
    stop: () => void;
}

interface SpeechRecognitionConstructor {
    new (): SpeechRecognitionInstance;
}

declare global {
    interface Window {
        SpeechRecognition?: SpeechRecognitionConstructor;
        webkitSpeechRecognition?: SpeechRecognitionConstructor;
    }
}

export function useSpeechToText({
    lang = 'en-US',
    continuous = false,
    interimResults = true,
    onResult,
    onError,
    onEnd,
}: UseSpeechToTextOptions = {}) {
    const [isRecording, setIsRecording] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [error, setError] = useState<string | null>(null);
    const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
    const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const onResultRef = useRef(onResult);
    const onErrorRef = useRef(onError);
    const onEndRef = useRef(onEnd);

    useEffect(() => {
        onResultRef.current = onResult;
    }, [onResult]);

    useEffect(() => {
        onErrorRef.current = onError;
    }, [onError]);

    useEffect(() => {
        onEndRef.current = onEnd;
    }, [onEnd]);

    const resetSilenceTimer = useCallback(() => {
        if (silenceTimeoutRef.current) {
            clearTimeout(silenceTimeoutRef.current);
        }

        silenceTimeoutRef.current = setTimeout(() => {
            if (recognitionRef.current) {
                recognitionRef.current.stop();
            }
        }, 5000);
    }, []);

    useEffect(() => {
        if (typeof window === 'undefined') {
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (!SpeechRecognition) {
            recognitionRef.current = null;
            return;
        }

        const recognition = new SpeechRecognition();
        recognition.lang = lang;
        recognition.continuous = continuous;
        recognition.interimResults = interimResults;

        recognition.onresult = (event) => {
            resetSilenceTimer();
            let currentTranscript = '';

            for (let index = event.resultIndex; index < event.results.length; index += 1) {
                currentTranscript += event.results[index][0].transcript;
            }

            setTranscript(currentTranscript);
            onResultRef.current?.(currentTranscript);
        };

        recognition.onstart = () => {
            setIsRecording(true);
            resetSilenceTimer();
        };

        recognition.onerror = (event) => {
            console.error('Speech Recognition Error:', event.error);
            setError(event.error);
            setIsRecording(false);

            if (silenceTimeoutRef.current) {
                clearTimeout(silenceTimeoutRef.current);
            }

            onErrorRef.current?.(event.error);
        };

        recognition.onend = () => {
            setIsRecording(false);

            if (silenceTimeoutRef.current) {
                clearTimeout(silenceTimeoutRef.current);
            }

            onEndRef.current?.();
        };

        recognitionRef.current = recognition;

        return () => {
            if (silenceTimeoutRef.current) {
                clearTimeout(silenceTimeoutRef.current);
            }

            recognitionRef.current = null;
        };
    }, [lang, continuous, interimResults, resetSilenceTimer]);

    const start = useCallback(() => {
        if (!recognitionRef.current) {
            const unsupportedMessage = 'Speech Recognition is not supported in this browser.';
            setError(unsupportedMessage);
            onErrorRef.current?.(unsupportedMessage);
            return;
        }

        setError(null);
        setTranscript('');

        try {
            recognitionRef.current.start();
            setIsRecording(true);
        } catch (err) {
            console.error('Failed to start recognition:', err);
            const message = err instanceof Error ? err.message : 'Failed to start speech recognition.';
            setError(message);
        }
    }, []);

    const stop = useCallback(() => {
        if (!recognitionRef.current) {
            return;
        }

        recognitionRef.current.stop();
        setIsRecording(false);
    }, []);

    const reset = useCallback(() => {
        setTranscript('');
        setError(null);
    }, []);

    return {
        isRecording,
        transcript,
        error,
        start,
        stop,
        reset,
    };
}
