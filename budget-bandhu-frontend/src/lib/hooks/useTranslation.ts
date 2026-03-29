import { useCallback } from 'react';
import { useLanguageStore } from '../store/useLanguageStore';
import { TranslationKey } from '../translations';

export function useTranslation() {
    const { currentLanguage, setLanguage, t: storeT } = useLanguageStore();

    const t = useCallback((key: TranslationKey) => {
        return storeT(key);
    }, [storeT]);

    // Compatible async version for runtime translations (optional/fallback)
    const translate = useCallback(async (text: string): Promise<string> => {
        return text; // In the new system, we prefer hardcoded keys
    }, []);

    return {
        currentLanguage,
        setLanguage,
        t,
        translate,
        isTranslating: false,
    };
}
