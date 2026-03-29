const fs = require('fs');
const content = fs.readFileSync('c:/Users/varma shivam/Downloads/BB1/budget-bandhu/budget-bandhu-frontend/src/lib/translations.ts', 'utf8');

const languages = ['en', 'hi', 'mr', 'gu', 'ta', 'te', 'kn', 'bn', 'pa', 'ml'];

languages.forEach(lang => {
    const langStart = content.indexOf(`${lang}: {`);
    if (langStart === -1) return;
    
    // Find matching closing brace
    let depth = 0;
    let end = -1;
    for (let i = langStart + lang.length + 3; i < content.length; i++) {
        if (content[i] === '{') depth++;
        if (content[i] === '}') {
            if (depth === 0) {
                end = i;
                break;
            }
            depth--;
        }
    }
    
    if (end === -1) return;
    
    const block = content.substring(langStart, end);
    const keys = block.match(/^\s+([a-z0-9_]+):/gm)?.map(m => m.trim().replace(':', '')) || [];
    
    const seen = new Set();
    const duplicates = [];
    keys.forEach(k => {
        if (seen.has(k)) duplicates.push(k);
        seen.add(k);
    });
    
    if (duplicates.length > 0) {
        console.log(`Duplicates in ${lang}:`, duplicates);
    }
});
