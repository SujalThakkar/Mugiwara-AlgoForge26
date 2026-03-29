const fs = require('fs');

const path = 'c:\\Users\\varma shivam\\Downloads\\BB1\\budget-bandhu\\budget-bandhu-frontend\\src\\lib\\translations.ts';
const content = fs.readFileSync(path, 'utf8');

// 1. Extract Keys
const keyMatch = content.match(/export type TranslationKey =([\s\S]*?);/);
if (!keyMatch) {
    console.error("TranslationKey not found");
    process.exit(1);
}
const keys = [...new Set(keyMatch[1].split('|').map(k => k.trim().replace(/['\s]/g, '')).filter(k => k))];
console.log(`Working with ${keys.length} keys`);

// 2. Extract Each Language Block
const languages = ['en', 'hi', 'mr', 'ta', 'te', 'bn', 'gu', 'kn', 'ml', 'pa'];
const langData = {};

languages.forEach(lang => {
    // Regex to find: lang: { [any characters until ] },
    const langRegex = new RegExp(`${lang}: \\{([\\s\\S]*?)\\},`, 'g');
    const match = langRegex.exec(content);
    if (match) {
        const langContent = match[1];
        const obj = {};
        // Simple extraction: key: 'value'
        keys.forEach(k => {
             const kRegex = new RegExp(`\\s${k}:\\s*(['"\`])([\\s\\S]*?)\\1,`, 'g');
             const kMatch = kRegex.exec(langContent);
             if(kMatch) {
                 obj[k] = kMatch[2].replace(/\\\\/g, '\\'); // Simple unescape
             }
        });
        langData[lang] = obj;
    } else {
        console.error(`Language ${lang} not found`);
    }
});

// 3. Fill missing with 'en' values
keys.forEach(k => {
    const defaultVal = langData['en'][k] || k;
    languages.forEach(lang => {
        if (!langData[lang][k]) {
            langData[lang][k] = defaultVal;
        }
    });
});

// 4. Reconstruct the file
let newContent = `import { LanguageCode } from './store/useLanguageStore';\n\nexport type TranslationKey = \n    '${keys.join("'\n    | '")}';\n\nexport const translations: Record<LanguageCode, Record<TranslationKey, string>> = {\n`;

languages.forEach(lang => {
    newContent += `    ${lang}: {\n`;
    keys.forEach(k => {
        // Double escaping for single quotes and backslashes in value
        const val = langData[lang][k].replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        newContent += `        ${k}: '${val}',\n`;
    });
    newContent += `    },\n`;
});

newContent += `};\n`;

fs.writeFileSync(path, newContent);
console.log("Translations file harmonized successfully!");
