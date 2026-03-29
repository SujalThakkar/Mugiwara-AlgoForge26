import os

def fix_translations():
    filepath = r"c:\Users\varma shivam\Downloads\BB1\budget-bandhu\budget-bandhu-frontend\src\lib\translations.ts"
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Find the corrupted area in ta (Tamil)
    # 1247:         insights_title: 'ஸ்மார்ட் நுண்ணறிவு',
    # 1248:         insights_subtitle: 'AI-ஆல் இயங்கும் பகுப்பாய்வு',
    # 1249:         insights_active_count: 'செயሊ    },
    
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Repair ta block
        if "insights_title: 'ஸ்மார்ட் நுண்ணறிவு'" in line:
            new_lines.append(line)
            new_lines.append("        insights_subtitle: 'AI-ஆல் இயங்கும் பகுப்பாய்வு',\n")
            new_lines.append("        insights_active_count: 'செயலில்',\n")
            new_lines.append("        insights_weekly_summary: 'வாராந்திர சுருக்கம்',\n")
            new_lines.append("        insight_saving_potential: 'வரை சேமிக்கவும்',\n")
            new_lines.append("        emergency_fund_title: 'அவசരக்கால நிதி',\n")
            new_lines.append("        financial_safety_net: 'உங்கள் நிதிப் பாதுகாப்பு வலை',\n")
            new_lines.append("        status_fair: 'பரவாயில்லை',\n")
            new_lines.append("        months_label: 'மாதங்கள்',\n")
            new_lines.append("        of_target_label: 'இலக்கில்',\n")
            new_lines.append("        current_balance_label: 'தற்போதைய இருப்பு',\n")
            new_lines.append("        target_amount_label: 'இலக்குத் தொகை',\n")
            new_lines.append("        coverage_period_label: 'கவரேஜ் காலம்',\n")
            
            # Skip the corrupted lines
            while i < len(lines) and "coverage_period_label:" not in lines[i]:
                i += 1
            i += 1
            continue
            
        # Remove duplicates in te block
        # Look for the duplicated blocks between 1670 and 1700
        if "status_analyzing_spending: 'మీ ఖర్చులను విశ్లేషిస్తోంది...'" in line:
             # We only want to keep ONE of these blocks and the closing brace
             # The block ends with tooltip_reject and msg_ai_feedback_note
             if " పాలసీలేర్నర్ వ్యక్తిగతీకరించిన సిഫార్సులను సిద్ధం చేస్తోంది" in lines[i+1]:
                 # This is the "correct" one maybe?
                 pass
        
        new_lines.append(line)
        i += 1

    # Second pass for te duplication
    # Actually, we can just deduplicate the keys in the te object.
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Repair attempt 1 finished.")

if __name__ == "__main__":
    fix_translations()
