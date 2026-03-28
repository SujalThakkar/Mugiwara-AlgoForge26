"""
api/services/ipfs_service.py — Pinata IPFS upload for badge metadata + images.

Workflow:
1. Generate badge or certificate image (PIL) based on goal size
2. Upload image to Pinata IPFS → imageCID
3. Build metadata JSON with "image": "ipfs://<imageCID>"
4. Upload metadata JSON to Pinata IPFS → metadataCID
5. Return "ipfs://<metadataCID>" as tokenURI for minting

Goal size thresholds:
  INR goals:  target >= 10,000 → certificate, else badge
  POL goals:  target >= 0.1    → certificate, else badge
"""

import os
import io
import json
import math
import logging
import httpx
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Pinata credentials ────────────────────────────────────────────────────────
PINATA_API_KEY    = os.getenv("PINATA_API_KEY", "")
PINATA_API_SECRET = os.getenv("PINATA_API_SECRET", "")
PINATA_JWT        = os.getenv("PINATA_JWT", "")

PINATA_PIN_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
PINATA_PIN_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"

# ── Thresholds ────────────────────────────────────────────────────────────────
CERTIFICATE_THRESHOLD_INR = 10_000   # ₹10,000+  → certificate
CERTIFICATE_THRESHOLD_POL = 0.1      # 0.1 POL+ → certificate

# ── Design constants ──────────────────────────────────────────────────────────
BRAND_PURPLE = (99,  102, 241)   # indigo-500
BRAND_DARK   = (30,  27,  75)    # deep indigo
GOLD         = (251, 191, 36)    # amber-400
WHITE        = (255, 255, 255)
LIGHT_BG     = (238, 242, 255)   # indigo-50


def _get_auth_headers() -> dict:
    if PINATA_JWT:
        return {"Authorization": f"Bearer {PINATA_JWT}"}
    return {
        "pinata_api_key":        PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_API_SECRET,
    }


def _is_certificate(goal_type: str, target: float) -> bool:
    """Determine if this goal earns a certificate (large) vs badge (small)."""
    if goal_type == "group_escrow":
        return target >= CERTIFICATE_THRESHOLD_POL
    return target >= CERTIFICATE_THRESHOLD_INR


# ── Lazy Load Base64 Logo ─────────────────────────────────────────────────────
_LOGO_B64 = None

def _get_logo_b64() -> str:
    global _LOGO_B64
    if _LOGO_B64 is None:
        try:
            logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo_b64.txt")
            with open(logo_path, "r") as f:
                _LOGO_B64 = f.read().strip()
        except Exception as e:
            logger.warning(f"[IPFS] Could not load logo base64: {e}")
            _LOGO_B64 = ""
    return _LOGO_B64


# ── Image generation ──────────────────────────────────────────────────────────

def _make_badge_svg(
    goal_title: str,
    goal_type:  str,
    target:     float,
) -> bytes:
    """
    Generate a highly premium SVG badge.
    Simulates a 3D Obsidian & Gold Medallion using precise vector gradients.
    """
    amt_str = f"₹{int(target):,}" if "crypto" not in goal_type else f"{target} POL"
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="100%" height="100%">
  <defs>
    <!-- Background Space/Glow -->
    <radialGradient id="glow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#4c1d95" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0"/>
    </radialGradient>

    <!-- Dark Obsidian Base -->
    <linearGradient id="obsidian" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e293b"/>
      <stop offset="50%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#020617"/>
    </linearGradient>

    <!-- Metallic Gold Rim -->
    <linearGradient id="gold-rim" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#b45309"/>
      <stop offset="20%" stop-color="#fef08a"/>
      <stop offset="40%" stop-color="#d97706"/>
      <stop offset="60%" stop-color="#fdf08a"/>
      <stop offset="80%" stop-color="#78350f"/>
      <stop offset="100%" stop-color="#fcd34d"/>
    </linearGradient>

    <!-- Inner Reflection -->
    <linearGradient id="reflection" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.15"/>
      <stop offset="50%" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>

    <!-- Drop Shadows -->
    <filter id="shadow-deep" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="15" stdDeviation="10" flood-color="#000000" flood-opacity="0.8"/>
    </filter>
    
    <filter id="shadow-text" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="2" flood-color="#000000" flood-opacity="0.9"/>
    </filter>

    <style>
      @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@700;900&amp;family=Inter:wght@400;700;900&amp;display=swap');
      .sub {{ font-family: 'Inter', sans-serif; font-weight: 700; font-size: 16px; fill: #d1d5db; text-anchor: middle; letter-spacing: 6px; }}
      .title {{ font-family: 'Cinzel', serif; font-weight: 900; font-size: 52px; fill: #ffffff; text-anchor: middle; }}
      .amt {{ font-family: 'Inter', sans-serif; font-weight: 900; font-size: 64px; fill: url(#gold-rim); text-anchor: middle; letter-spacing: -1px; }}
      .brand {{ font-family: 'Inter', sans-serif; font-weight: 700; font-size: 12px; fill: #6366f1; text-anchor: middle; letter-spacing: 2px; opacity: 0.8; }}
      .accent {{ font-size: 24px; fill: url(#gold-rim); text-anchor: middle; }}
    </style>
  </defs>

  <!-- Ambient Glow -->
  <rect width="600" height="600" fill="url(#glow)"/>

  <!-- Thick Outer Gold Rim / Base Coin -->
  <circle cx="300" cy="300" r="260" fill="url(#gold-rim)" filter="url(#shadow-deep)"/>
  
  <!-- Outer Bevel indent (Dark) -->
  <circle cx="300" cy="300" r="248" fill="#451a03"/>
  
  <!-- Inner Obsidian Plate -->
  <circle cx="300" cy="300" r="244" fill="url(#obsidian)"/>
  
  <!-- Top Glass Reflection on Obsidian -->
  <circle cx="300" cy="300" r="244" fill="url(#reflection)"/>

  <!-- Intricate Tech / Magic Rings -->
  <circle cx="300" cy="300" r="230" fill="none" stroke="url(#gold-rim)" stroke-width="1" stroke-dasharray="2 6" opacity="0.6"/>
  <circle cx="300" cy="300" r="220" fill="none" stroke="#6366f1" stroke-width="2" opacity="0.4"/>
  <circle cx="300" cy="300" r="200" fill="none" stroke="url(#gold-rim)" stroke-width="1" stroke-dasharray="15 5 2 5"/>

  <!-- Logo (Embedded base64) -->
  <image href="data:image/png;base64,{_get_logo_b64()}" x="250" y="70" width="100" height="100" />

  <!-- Text Group -->
  <g filter="url(#shadow-text)">
    <text x="300" y="170" class="sub">GOAL ACHIEVED</text>
    
    <!-- Dynamically sized title -->
    <text x="300" y="260" class="title" lengthAdjust="spacingAndGlyphs" textLength="{min(400, len(goal_title)*30)}">{goal_title.upper()}</text>
    
    <!-- Divider -->
    <path d="M 160 310 L 440 310" stroke="url(#gold-rim)" stroke-width="2" opacity="0.5"/>
    <path d="M 280 310 L 320 310" stroke="#ffffff" stroke-width="4"/>
    
    <text x="300" y="410" class="amt">{amt_str}</text>
  </g>

  <!-- Wrapping Text Path Brand (Requires a path def) -->
  <defs>
    <path id="curve" d="M 140 300 a 160 160 0 0 0 320 0" fill="transparent" />
  </defs>
  <text class="brand">
    <textPath href="#curve" startOffset="50%" text-anchor="middle">BUDGETBANDHU SOULBOUND ASSET</textPath>
  </text>
</svg>"""
    return svg.encode('utf-8')


def _make_certificate_svg(
    goal_title:  str,
    goal_type:   str,
    target:      float,
    completed_at: str,
    user_wallet: Optional[str] = None,
) -> bytes:
    """
    Generate an ultra-premium SVG certificate.
    """
    amt_str = f"₹{int(target):,}" if "crypto" not in goal_type else f"{target:.4f} POL"
    wallet_block = f'<text x="500" y="580" class="text-meta">WALLET: {user_wallet}</text>' if user_wallet else ""

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 700" width="100%" height="100%">
  <defs>
    <!-- Dark Luxury Background Gradient -->
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#09090b" />
      <stop offset="100%" stop-color="#1e1b4b" />
    </linearGradient>

    <!-- Gold Foil Gradient -->
    <linearGradient id="gold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#d97706" />
      <stop offset="25%" stop-color="#fef08a" />
      <stop offset="50%" stop-color="#b45309" />
      <stop offset="75%" stop-color="#fde047" />
      <stop offset="100%" stop-color="#78350f" />
    </linearGradient>

    <filter id="glow">
      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
      <feMerge>
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    
    <filter id="shadow">
      <feDropShadow dx="0" dy="5" stdDeviation="5" flood-color="#000" flood-opacity="0.8"/>
    </filter>

    <style>
      @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;800&amp;family=Inter:wght@400;700&amp;display=swap');
      .header {{ font-family: 'Cinzel', serif; font-weight: 800; font-size: 38px; fill: url(#gold); text-anchor: middle; letter-spacing: 6px; }}
      .sub {{ font-family: 'Inter', sans-serif; font-weight: 700; font-size: 16px; fill: #818cf8; text-anchor: middle; letter-spacing: 4px; }}
      .title {{ font-family: 'Cinzel', serif; font-weight: 800; font-size: 72px; fill: #ffffff; text-anchor: middle; }}
      .target-lbl {{ font-family: 'Inter', sans-serif; font-weight: 700; font-size: 18px; fill: #6366f1; text-anchor: middle; letter-spacing: 2px; }}
      .target-val {{ font-family: 'Cinzel', serif; font-weight: 800; font-size: 64px; fill: url(#gold); text-anchor: middle; }}
      .text-meta {{ font-family: 'Inter', sans-serif; font-weight: 400; font-size: 14px; fill: #94a3b8; text-anchor: middle; }}
      .footer {{ font-family: 'Inter', sans-serif; font-weight: 700; font-size: 12px; fill: #4f46e5; text-anchor: middle; letter-spacing: 2px; }}
    </style>
  </defs>

  <!-- Base Rectangle -->
  <rect width="1000" height="700" fill="url(#bg)" />
  
  <!-- Outer Gold Border -->
  <rect x="30" y="30" width="940" height="640" fill="none" stroke="url(#gold)" stroke-width="4" />
  
  <!-- Inner Delicate Border -->
  <rect x="42" y="42" width="916" height="616" fill="none" stroke="#4c1d95" stroke-width="2" />
  
  <!-- Geometric accents -->
  <path d="M 30 100 L 100 30" stroke="url(#gold)" stroke-width="2"/>
  <path d="M 970 100 L 900 30" stroke="url(#gold)" stroke-width="2"/>
  <path d="M 30 600 L 100 670" stroke="url(#gold)" stroke-width="2"/>
  <path d="M 970 600 L 900 670" stroke="url(#gold)" stroke-width="2"/>

  <!-- Brand Logo -->
  <image href="data:image/png;base64,{_get_logo_b64()}" x="450" y="20" width="100" height="100" />

  <!-- Content Group -->
  <g filter="url(#shadow)">
    <text x="500" y="140" class="header">CERTIFICATE OF DISCIPLINE</text>
    
    <text x="500" y="240" class="sub">AWARDED FOR THE SUCCESSFUL COMPLETION OF</text>
    
    <!-- Title with dynamic sizing logic based on length via SVG textLength (max width 800) -->
    <text x="500" y="340" class="title" textLength="{min(800, len(goal_title)*40)}" lengthAdjust="spacingAndGlyphs">{goal_title.upper()}</text>
    
    <rect x="250" y="400" width="500" height="2" fill="url(#gold)" opacity="0.5"/>
    
    <text x="500" y="460" class="target-val">{amt_str}</text>
  </g>

  <!-- Metadata -->
  <text x="500" y="550" class="text-meta">VERIFIED ON CHAIN: {completed_at}</text>
  {wallet_block}

  <text x="500" y="650" class="footer">BUDGETBANDHU · IMMUTABLE SOULBOUND PROOF</text>
</svg>"""
    return svg.encode('utf-8')



# ── Pinata uploads ────────────────────────────────────────────────────────────

async def upload_image_to_ipfs(
    image_bytes: bytes, 
    filename: str = "badge.svg", 
    content_type: str = "image/svg+xml"
) -> str:
    """
    Upload an image to Pinata and return ipfs://CID.
    Defaults to SVG handling.
    """
    if not PINATA_JWT and not (PINATA_API_KEY and PINATA_API_SECRET):
        raise RuntimeError("Pinata credentials not configured")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            PINATA_PIN_FILE_URL,
            headers=_get_auth_headers(),
            files={"file": (filename, image_bytes, content_type)},
            data={
                "pinataMetadata": json.dumps({"name": filename}),
                "pinataOptions":  json.dumps({"cidVersion": 1}),
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"Pinata image upload failed: {response.text}")

        cid = response.json()["IpfsHash"]
        logger.info(f"[IPFS] Image uploaded: ipfs://{cid}")
        return f"ipfs://{cid}"


async def upload_metadata_to_ipfs(metadata: dict, pin_name: str = "BudgetBandhu Badge") -> str:
    """
    Upload metadata JSON to Pinata IPFS and return ipfs://CID.
    """
    if not PINATA_JWT and not (PINATA_API_KEY and PINATA_API_SECRET):
        raise RuntimeError("Pinata credentials not configured")

    payload = {
        "pinataContent":  metadata,
        "pinataMetadata": {"name": pin_name},
        "pinataOptions":  {"cidVersion": 1},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            PINATA_PIN_JSON_URL,
            headers={**_get_auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Pinata metadata upload failed: {response.text}")

        cid = response.json()["IpfsHash"]
        logger.info(f"[IPFS] Metadata uploaded: ipfs://{cid}")
        return f"ipfs://{cid}"


# ── Main entry point ──────────────────────────────────────────────────────────

async def generate_and_upload_badge(
    goal_title:   str,
    goal_type:    str,       # "personal_csv" | "personal_crypto" | "group_csv" | "group_escrow"
    target:       float,
    completed_at: Optional[str] = None,
    user_wallet:  Optional[str] = None,
    extra_attrs:  Optional[list] = None,
    icon:         str = "🎯",
) -> str:
    """
    Full pipeline:
    1. Decide badge vs certificate based on target size
    2. Generate image (PIL)
    3. Upload image to Pinata → imageCID
    4. Build metadata JSON with image field
    5. Upload metadata → metadataCID
    6. Return ipfs://<metadataCID> as tokenURI

    Falls back gracefully if PIL is not installed (uses placeholder image).
    """
    if completed_at is None:
        completed_at = datetime.utcnow().strftime("%Y-%m-%d")

    is_cert   = _is_certificate(goal_type, target)
    nft_type  = "Certificate" if is_cert else "Badge"

    # 1. Generate image bytes
    if is_cert:
        img_bytes = _make_certificate_svg(goal_title, goal_type, target, completed_at, user_wallet)
        img_name  = f"certificate_{goal_title[:20].replace(' ', '_')}.svg"
    else:
        img_bytes = _make_badge_svg(goal_title, goal_type, target)
        img_name  = f"badge_{goal_title[:20].replace(' ', '_')}.svg"

    # 2. Upload image
    image_cid_uri = await upload_image_to_ipfs(img_bytes, img_name, content_type="image/svg+xml")

    # 3. Build metadata
    goal_type_display = {
        "personal_csv":    "Personal Savings",
        "personal_crypto": "Personal Crypto",
        "group_csv":       "Group Savings",
        "group_escrow":    "Group Escrow Pool",
    }.get(goal_type, "Goal Achievement")

    target_display = f"₹{target:,.0f}" if goal_type != "group_escrow" else f"{target} POL"

    attributes = [
        {"trait_type": "Type",       "value": nft_type},
        {"trait_type": "Goal Type",  "value": goal_type_display},
        {"trait_type": "Goal Value", "value": target_display},
        {"trait_type": "Status",     "value": "Completed"},
        {"trait_type": "Platform",   "value": "BudgetBandhu"},
        {"trait_type": "Network",    "value": "Polygon Amoy"},
        {"trait_type": "Date",       "value": completed_at},
    ]
    if user_wallet:
        attributes.append({"trait_type": "Recipient", "value": user_wallet})
    if extra_attrs:
        attributes.extend(extra_attrs)

    metadata = {
        "name":        f"BudgetBandhu — {goal_title} ({nft_type})",
        "description": (
            f"Soulbound {nft_type.lower()} awarded for completing the '{goal_title}' goal "
            f"on BudgetBandhu. Permanently bound to the holder's wallet."
        ),
        "image":       image_cid_uri,   # ← ipfs://<imageCID>
        "attributes":  attributes,
        "external_url": "https://budgetbandhu.in",
    }

    # 4. Upload metadata
    meta_uri = await upload_metadata_to_ipfs(
        metadata,
        pin_name=f"BB-{nft_type}-{goal_title[:30]}",
    )

    logger.info(f"[IPFS] Badge pipeline complete: {nft_type} → image={image_cid_uri} → meta={meta_uri}")
    return meta_uri   # ipfs://<metadataCID>
