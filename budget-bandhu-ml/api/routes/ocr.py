"""
OCR Routes - Receipt/Bill Scanning
Uses EasyOCR for text extraction from images

Author: Aryan Lomte
Date: Jan 17, 2026
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional
import re
import io
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ocr", tags=["OCR"])

# Lazy load EasyOCR (heavy import)
_ocr_reader = None

def get_ocr_reader():
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            logger.info("[OCR] Loading EasyOCR (first time, may take a moment)...")
            _ocr_reader = easyocr.Reader(['en', 'hi'], gpu=False)  # English + Hindi
            logger.info("[OCR] EasyOCR loaded successfully")
        except ImportError:
            logger.error("[OCR] EasyOCR not installed. Run: pip install easyocr")
            raise HTTPException(status_code=503, detail="OCR service not available")
    return _ocr_reader


def extract_amount(text: str) -> Optional[float]:
    """Extract monetary amount from OCR text"""
    patterns = [
        r'₹\s*([\d,]+(?:\.\d{2})?)',
        r'Rs\.?\s*([\d,]+(?:\.\d{2})?)',
        r'INR\s*([\d,]+(?:\.\d{2})?)',
        r'Total[:\s]*([\d,]+(?:\.\d{2})?)',
        r'Amount[:\s]*([\d,]+(?:\.\d{2})?)',
        r'Grand\s*Total[:\s]*([\d,]+(?:\.\d{2})?)',
        r'Net\s*Amount[:\s]*([\d,]+(?:\.\d{2})?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(',', ''))
    return None


def extract_date(text: str) -> Optional[str]:
    """Extract date from OCR text"""
    patterns = [
        r'(\d{2}[-/]\d{2}[-/]\d{4})',  # DD-MM-YYYY or DD/MM/YYYY
        r'(\d{4}[-/]\d{2}[-/]\d{2})',  # YYYY-MM-DD
        r'(\d{2}\s+\w{3}\s+\d{4})',    # 17 Jan 2026
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def extract_merchant(text: str) -> Optional[str]:
    """Try to extract merchant/store name from first few lines"""
    lines = text.strip().split('\n')
    if lines:
        # Usually merchant name is in first 1-2 lines
        for line in lines[:3]:
            cleaned = line.strip()
            if len(cleaned) > 3 and not re.match(r'^[\d\s₹Rs.]+$', cleaned):
                return cleaned[:50]  # Limit length
    return None


@router.post("/scan-receipt")
async def scan_receipt(image: UploadFile = File(...)):
    """
    Scan a receipt/bill image and extract transaction details.
    
    Returns:
        - amount: Detected monetary amount
        - description: Merchant/description
        - date: Detected date
        - rawText: Full OCR text
    """
    # Validate file type
    if not image.content_type or not image.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Please upload an image file")
    
    try:
        # Read image bytes
        contents = await image.read()
        
        # Get OCR reader
        reader = get_ocr_reader()
        
        # Perform OCR
        logger.info(f"[OCR] Processing image: {image.filename}")
        result = reader.readtext(contents)
        
        # Combine all detected text
        full_text = '\n'.join([detection[1] for detection in result])
        
        # Extract structured data
        amount = extract_amount(full_text)
        date = extract_date(full_text)
        merchant = extract_merchant(full_text)
        
        logger.info(f"[OCR] Extracted: amount={amount}, date={date}, merchant={merchant}")
        
        return {
            "amount": amount,
            "description": merchant,
            "date": date,
            "merchant": merchant,
            "rawText": full_text,
            "confidence": sum([d[2] for d in result]) / len(result) if result else 0
        }
        
    except Exception as e:
        logger.error(f"[OCR] Error processing image: {e}")
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")
