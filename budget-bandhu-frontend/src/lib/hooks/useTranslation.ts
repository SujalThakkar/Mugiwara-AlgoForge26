import { useState, useCallback } from 'react';
import { mlApi } from '../api/ml-api';
import { useLanguageStore } from '../store/useLanguageStore';

export function useTranslation() {
    const { currentLanguage, setLanguage } = useLanguageStore();
    const [isTranslating, setIsTranslating] = useState(false);

    const translate = useCallback(async (text: string): Promise<string> => {
        if (currentLanguage === 'en') {
            return text;
        }

        setIsTranslating(true);

        try {
            const result = await mlApi.translate.text(text, currentLanguage, 'en');
            return result.translatedText;
        } catch (error) {
            console.error('[Translation] Error:', error);
            return text;
        } finally {
            setIsTranslating(false);
        }
    }, [currentLanguage]);

    const translateBatch = useCallback(async (texts: string[]): Promise<string[]> => {
        if (currentLanguage === 'en') {
            return texts;
        }

        return Promise.all(texts.map((text) => translate(text)));
    }, [currentLanguage, translate]);

    return {
        currentLanguage,
        setLanguage,
        translate,
        translateBatch,
        isTranslating,
    };
}
