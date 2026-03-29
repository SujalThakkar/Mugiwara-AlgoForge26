const fs = require('fs');

const content = fs.readFileSync('c:\\Users\\varma shivam\\Downloads\\BB1\\budget-bandhu\\budget-bandhu-frontend\\src\\lib\\translations.ts', 'utf8');

const keyMatch = content.match(/export type TranslationKey =([\s\S]*?);/);
if (!keyMatch) {
    console.log("Could not find TranslationKey");
    process.exit(1);
}

const rawKeys = keyMatch[1].split('|').map(k => k.trim().replace(/['\s]/g, '')).filter(k => k);
// Deduplicate keys
const keys = [...new Set(rawKeys)];

console.log(`Found ${keys.length} unique keys in TranslationKey`);

const languages = ['en', 'hi', 'mr', 'ta', 'te', 'bn', 'gu', 'kn', 'ml', 'pa'];

languages.forEach(lang => {
    // Look for the specific language block
    const langRegex = new RegExp(`${lang}: \\{[\\s\\S]*?\\},`, 'g');
    const match = langRegex.exec(content);
    if (match) {
        const langContent = match[0]; // match[0] is better because it includes the closing brace
        const missing = [];
        keys.forEach(key => {
            const pattern = new RegExp(`\\s${key}:`, 'i');
            if (!pattern.test(langContent)) {
               missing.push(key);
            }
        });
        if (missing.length > 0) {
            console.log(`Language ${lang}: missing ${missing.length} keys.`);
            console.log(`Missing keys examples: ${missing.slice(0, 5).join(', ')}`);
        } else {
            console.log(`Language ${lang}: ALL OK!`);
        }
    } else {
        console.log(`Language ${lang}: NOT FOUND`);
    }
});
