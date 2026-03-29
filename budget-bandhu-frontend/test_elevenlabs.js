async function test() {
    const key = 'sk_bcce713e8b29f08d937d33fbe557bd49a4c04fc019d5b26e';
    const rachelVoiceId = '21m00Tcm4T7sD674y9S6';

    console.log("Testing Rachel (Standard Voice) with free key...");
    try {
        const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${rachelVoiceId}`, {
            method: 'POST',
            headers: {
                'xi-api-key': key,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: "Hello World",
                model_id: "eleven_multilingual_v2"
            })
        });
        
        console.log("Status:", response.status);
        if (response.ok) {
            console.log("Success! Audio generated with Rachel.");
        } else {
            const data = await response.json();
            console.log("Error response:", JSON.stringify(data, null, 2));
        }
    } catch (err) {
        console.error("Fetch failed:", err);
    }
}

test();
