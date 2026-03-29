/**
 * Free Translation Utility using Google Translate Unofficial API
 * This is lightweight and requires no API keys.
 */

export async function translateText(text: string, from: string = 'auto', to: string = 'en'): Promise<string> {
    if (!text.trim()) return '';
    if (from === to) return text;

    try {
        const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=${from}&tl=${to}&dt=t&q=${encodeURIComponent(text)}`;
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error('Translation request failed');
        }

        const data = await response.json();
        
        // Google Translate structure: [[["translated_text", "original_text", ...]]]
        if (data && data[0] && data[0][0] && data[0][0][0]) {
            return data[0].map((part: any) => part[0]).join('');
        }
        
        return text;
    } catch (error) {
        console.error('Translation error:', error);
        return text; // Fallback to original text on failure
    }
}

// Map of common language codes for Google Translate
export const VOICE_LANGUAGES = [
    { code: 'en-US', name: 'English (US)', gcode: 'en' },
    { code: 'hi-IN', name: 'Hindi (हिंदी)', gcode: 'hi' },
    { code: 'mr-IN', name: 'Marathi (मराठी)', gcode: 'mr' },
    { code: 'ta-IN', name: 'Tamil (தமிழ்)', gcode: 'ta' },
    { code: 'te-IN', name: 'Telugu (తెలుగు)', gcode: 'te' },
    { code: 'kn-IN', name: 'Kannada (ಕನ್ನಡ)', gcode: 'kn' },
    { code: 'ml-IN', name: 'Malayalam (മലയാളം)', gcode: 'ml' },
    { code: 'gu-IN', name: 'Gujarati (ગુજરાતી)', gcode: 'gu' },
    { code: 'pa-IN', name: 'Punjabi (ਪੰਜਾਬੀ)', gcode: 'pa' },
    { code: 'bn-IN', name: 'Bengali (বাংলা)', gcode: 'bn' },
];
