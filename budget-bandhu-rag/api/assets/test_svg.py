
import sys
import os

sys.path.insert(0, os.path.abspath(r'e:\\PICT Techfiesta\\BudgetBandhu\\budget-bandhu-rag'))

from api.services.ipfs_service import _make_badge_svg, _make_certificate_svg
import os

try:
    badge_bytes = _make_badge_svg('Goa Trip 2026', 'personal_csv', 15000.0)
    with open('e:\\\\PICT Techfiesta\\\\BudgetBandhu\\\\budget-bandhu-rag\\\\api\\\\assets\\\\sample_badge_vector.svg', 'wb') as f:
        f.write(badge_bytes)

    cert_bytes = _make_certificate_svg('Mercedes Downpayment', 'group_csv', 2500000.0, '2026-03-29', '0x1234567890abcdef1234567890abcdef12345678')
    with open('e:\\\\PICT Techfiesta\\\\BudgetBandhu\\\\budget-bandhu-rag\\\\api\\\\assets\\\\sample_certificate_vector.svg', 'wb') as f:
        f.write(cert_bytes)
        
    print('SVG Samples generated successfully.')
except Exception as e:
    import traceback
    traceback.print_exc()
