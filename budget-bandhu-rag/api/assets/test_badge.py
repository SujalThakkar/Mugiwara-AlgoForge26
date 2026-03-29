
import sys
import os

# Set up path so we can import the module correctly
sys.path.insert(0, os.path.abspath(r'e:\\PICT Techfiesta\\BudgetBandhu\\budget-bandhu-rag'))

from api.services.ipfs_service import _make_badge_image, _make_certificate_image
import os
import io
from PIL import Image

try:
    badge_bytes = _make_badge_image('Goa Trip 2026', 'personal_csv', 15000.0)
    b_img = Image.open(io.BytesIO(badge_bytes))
    b_img.save('e:\\\\PICT Techfiesta\\\\BudgetBandhu\\\\budget-bandhu-rag\\\\api\\\\assets\\\\sample_badge.png')

    cert_bytes = _make_certificate_image('Mercedes Downpayment', 'group_csv', 2500000.0, '2026-03-29', '0x1234567890abcdef1234567890abcdef12345678')
    c_img = Image.open(io.BytesIO(cert_bytes))
    c_img.save('e:\\\\PICT Techfiesta\\\\BudgetBandhu\\\\budget-bandhu-rag\\\\api\\\\assets\\\\sample_certificate.png')
    print('Samples generated successfully.')
except Exception as e:
    import traceback
    traceback.print_exc()
