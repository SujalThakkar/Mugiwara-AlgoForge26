
import sys
import os
import httpx
from datetime import datetime

sys.path.insert(0, os.path.abspath(r'e:\\PICT Techfiesta\\BudgetBandhu\\budget-bandhu-rag'))
from api.services.ipfs_service import _make_badge_svg, _make_certificate_svg

r = httpx.get('http://localhost:8000/api/v1/goals/demo_user_001')
goals = r.json()

goa_goal = next((g for g in goals if 'goa' in g.get('name', '').lower()), goals[0] if goals else None)

if goa_goal:
    print(f'Using Goal: {goa_goal['name']} for {goa_goal['target']}')
    
    # Generate Badge
    badge_bytes = _make_badge_svg(goa_goal['name'], goa_goal['type'], float(goa_goal['target']))
    with open('e:\\\\PICT Techfiesta\\\\BudgetBandhu\\\\budget-bandhu-rag\\\\api\\\\assets\\\\goa_badge_vector.svg', 'wb') as f:
        f.write(badge_bytes)

    # Generate Certificate
    cert_bytes = _make_certificate_svg(goa_goal['name'], goa_goal['type'], float(goa_goal['target']), goa_goal.get('deadline', '2026-03-30'), '0x88981A...')
    with open('e:\\\\PICT Techfiesta\\\\BudgetBandhu\\\\budget-bandhu-rag\\\\api\\\\assets\\\\goa_certificate_vector.svg', 'wb') as f:
        f.write(cert_bytes)
        
    print('DB-based SVGs generated successfully.')
else:
    print('No goals found in API.')
