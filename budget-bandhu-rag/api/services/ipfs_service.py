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


# ── Image generation ──────────────────────────────────────────────────────────

def _make_badge_image(
    goal_title: str,
    goal_type:  str,
    target:     float,
    icon:       str = "🎯",
) -> bytes:
    """
    Generate a circular badge-style PNG (400×400px).
    Falls back to a plain colored square if PIL is not installed.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        size  = 400
        img   = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(img)

        # Outer circle background
        draw.ellipse([0, 0, size, size], fill=BRAND_PURPLE)
        # Inner ring
        draw.ellipse([15, 15, size - 15, size - 15], outline=GOLD, width=6)
        # Inner white circle
        draw.ellipse([30, 30, size - 30, size - 30], fill=LIGHT_BG)

        # Title text
        title = goal_title[:20] + ("…" if len(goal_title) > 20 else "")
        try:
            font_lg = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 28)
            font_sm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
        except Exception:
            font_lg = ImageFont.load_default()
            font_sm = font_lg

        # Center title
        bbox = draw.textbbox((0, 0), title, font=font_lg)
        tw   = bbox[2] - bbox[0]
        draw.text(((size - tw) / 2, 170), title, font=font_lg, fill=BRAND_DARK)

        # "GOAL ACHIEVED" label
        sub = "GOAL ACHIEVED"
        bbox2 = draw.textbbox((0, 0), sub, font=font_sm)
        tw2   = bbox2[2] - bbox2[0]
        draw.text(((size - tw2) / 2, 215), sub, font=font_sm, fill=BRAND_PURPLE)

        # Target amount
        amt_str = f"₹{int(target):,}" if "crypto" not in goal_type else f"{target} POL"
        bbox3   = draw.textbbox((0, 0), amt_str, font=font_sm)
        tw3     = bbox3[2] - bbox3[0]
        draw.text(((size - tw3) / 2, 246), amt_str, font=font_sm, fill=GOLD)

        # BudgetBandhu branding
        brand = "BudgetBandhu"
        bbox4 = draw.textbbox((0, 0), brand, font=font_sm)
        tw4   = bbox4[2] - bbox4[0]
        draw.text(((size - tw4) / 2, 295), brand, font=font_sm, fill=BRAND_PURPLE)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except ImportError:
        # PIL not installed — return minimal valid PNG (1×1 purple pixel)
        logger.warning("[IPFS] PIL not installed, using placeholder badge")
        return _minimal_png(BRAND_PURPLE)


def _make_certificate_image(
    goal_title:  str,
    goal_type:   str,
    target:      float,
    completed_at: str,
    user_wallet: Optional[str] = None,
) -> bytes:
    """
    Generate a landscape certificate-style PNG (800×560px).
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        W, H = 800, 560
        img  = Image.new("RGB", (W, H), WHITE)
        draw = ImageDraw.Draw(img)

        # Background
        draw.rectangle([0, 0, W, H], fill=(245, 243, 255))   # purple-50
        # Top banner
        draw.rectangle([0, 0, W, 100], fill=BRAND_PURPLE)
        # Gold border
        draw.rectangle([12, 12, W - 12, H - 12], outline=GOLD, width=4)
        draw.rectangle([18, 18, W - 18, H - 18], outline=GOLD, width=1)

        try:
            f_title  = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 48)
            f_header = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
            f_body   = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
            f_small  = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
        except Exception:
            f_title = f_header = f_body = f_small = ImageFont.load_default()

        # Header text
        hdr = "🏆  Certificate of Achievement  🏆"
        bb  = draw.textbbox((0, 0), hdr, font=f_body)
        draw.text(((W - (bb[2] - bb[0])) / 2, 34), hdr, font=f_body, fill=WHITE)

        # "CERTIFIES THAT"
        ct = "THIS CERTIFIES THAT THE FOLLOWING GOAL HAS BEEN ACHIEVED"
        bb2 = draw.textbbox((0, 0), ct, font=f_small)
        draw.text(((W - (bb2[2] - bb2[0])) / 2, 130), ct, font=f_small, fill=BRAND_PURPLE)

        # Goal title (large)
        title  = goal_title[:40] + ("…" if len(goal_title) > 40 else "")
        bb3    = draw.textbbox((0, 0), title, font=f_title)
        draw.text(((W - (bb3[2] - bb3[0])) / 2, 170), title, font=f_title, fill=BRAND_DARK)

        # Horizontal divider
        draw.line([(80, 255), (W - 80, 255)], fill=GOLD, width=2)

        # Amount
        amt = f"₹{int(target):,}" if "crypto" not in goal_type else f"{target:.4f} POL"
        bb4 = draw.textbbox((0, 0), amt, font=f_header)
        draw.text(((W - (bb4[2] - bb4[0])) / 2, 275), amt, font=f_header, fill=BRAND_PURPLE)

        draw.text((80, 350), f"Date: {completed_at}", font=f_small, fill=(100, 100, 120))

        if user_wallet:
            wallet_short = f"{user_wallet[:10]}...{user_wallet[-6:]}"
            draw.text((80, 375), f"Wallet: {wallet_short}", font=f_small, fill=(100, 100, 120))

        # Soulbound note
        note = "⛓  Soulbound Token (Non-Transferable) · Polygon Amoy"
        bb5  = draw.textbbox((0, 0), note, font=f_small)
        draw.text(((W - (bb5[2] - bb5[0])) / 2, 460), note, font=f_small, fill=BRAND_PURPLE)

        # BudgetBandhu footer
        brand = "BudgetBandhu · budgetbandhu.in"
        bb6   = draw.textbbox((0, 0), brand, font=f_small)
        draw.text(((W - (bb6[2] - bb6[0])) / 2, H - 40), brand, font=f_small, fill=(120, 120, 140))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except ImportError:
        logger.warning("[IPFS] PIL not installed, using placeholder certificate")
        return _minimal_png(BRAND_DARK)


def _minimal_png(color: tuple) -> bytes:
    """1×1 pixel PNG as fallback when PIL is unavailable."""
    import struct, zlib
    r, g, b = color
    raw  = bytes([0, r, g, b])
    comp = zlib.compress(raw)
    def chunk(name, data):
        c = struct.pack(">I", len(data)) + name + data
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return c + struct.pack(">I", crc)
    png  = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    return png


# ── Pinata uploads ────────────────────────────────────────────────────────────

async def upload_image_to_ipfs(image_bytes: bytes, filename: str = "badge.png") -> str:
    """
    Upload a PNG image to Pinata and return ipfs://CID.
    """
    if not PINATA_JWT and not (PINATA_API_KEY and PINATA_API_SECRET):
        raise RuntimeError("Pinata credentials not configured")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            PINATA_PIN_FILE_URL,
            headers=_get_auth_headers(),
            files={"file": (filename, image_bytes, "image/png")},
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
        img_bytes = _make_certificate_image(goal_title, goal_type, target, completed_at, user_wallet)
        img_name  = f"certificate_{goal_title[:20].replace(' ', '_')}.png"
    else:
        img_bytes = _make_badge_image(goal_title, goal_type, target, icon)
        img_name  = f"badge_{goal_title[:20].replace(' ', '_')}.png"

    # 2. Upload image
    image_cid_uri = await upload_image_to_ipfs(img_bytes, img_name)

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
