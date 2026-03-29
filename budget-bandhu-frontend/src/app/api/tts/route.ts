import { NextResponse } from 'next/server';

export async function POST(req: Request) {
    try {
        const { text, langCode } = await req.json();
        
        // Latest Valid Key from user
        const ELEVEN_LABS_API_KEY = 'sk_bcce713e8b29f08d937d33fbe557bd49a4c04fc019d5b26e';
        // Preferred Voice ID from user
        const ELEVEN_LABS_VOICE_ID = 'QO2wwSVI9F7DwU5uUXDX'; 
        // Standard Fallback Voice ID (Adam)
        const FALLBACK_VOICE_ID = 'pNInz6obpgmqS2atpD12';

        console.log(`🔊 [Proxy] Processing: "${text.substring(0, 30)}..." for ${langCode}`);

        // 1. Try Primary Voice
        let response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${ELEVEN_LABS_VOICE_ID}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'xi-api-key': ELEVEN_LABS_API_KEY,
            },
            body: JSON.stringify({
                text: text,
                model_id: 'eleven_multilingual_v2',
                voice_settings: { stability: 0.5, similarity_boost: 0.8 }
            }),
        });

        // 2. If Primary Fails (likely restricted account), try Adam Fallback
        if (!response.ok) {
            console.warn(`[Proxy] Primary choice failed (${response.status}). Trying Adam fallback...`);
            response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${FALLBACK_VOICE_ID}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'xi-api-key': ELEVEN_LABS_API_KEY,
                },
                body: JSON.stringify({
                    text: text,
                    model_id: 'eleven_multilingual_v2',
                    voice_settings: { stability: 0.5, similarity_boost: 0.8 }
                }),
            });
        }

        if (response.ok) {
            const buffer = await response.arrayBuffer();
            return new Response(buffer, {
                headers: { 'Content-Type': 'audio/mpeg' },
            });
        } else {
            const errorText = await response.text();
            console.error('[Proxy] ElevenLabs Error:', errorText);
            return NextResponse.json({ error: errorText }, { status: response.status });
        }
    } catch (error: any) {
        console.error('[Proxy] Critical failure:', error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}
