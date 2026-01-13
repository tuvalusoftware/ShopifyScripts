#!/usr/bin/env python3
"""
PDF Extraction Service V3
Uses GPT-4o Vision to extract products from PDF pages as images.

Key improvements over V1:
- Renders PDF pages as images and sends to GPT-4o Vision
- GPT can "see" the layout, images, and text together
- Better accuracy for complex linesheet layouts

Usage:
    from services.pdf_extraction_service_v3 import extract_products_from_pdf
    
    result = extract_products_from_pdf(
        pdf_path="path/to/linesheet.pdf",
        out_dir="./outputs"
    )
"""

from __future__ import annotations

import base64
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, cast

import fitz  # PyMuPDF
from openai import OpenAI

# Load .env from same directory as this script
SCRIPT_DIR = Path(__file__).parent.resolve()
ENV_FILE = SCRIPT_DIR / ".env"

if ENV_FILE.exists():
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE)
else:
    print(f"[WARN] .env file not found at {ENV_FILE}")

# =============================================================================
# Configuration
# =============================================================================

CONFIG = {
    "model": "gpt-4.1-mini",  # Vision-capable model
    "max_output_tokens": 4000,
    "timeout_s": 120.0,
    "max_retries": 6,
    "backoff_base_s": 0.8,
    "backoff_cap_s": 12.0,
    "image_dpi": 150,  # DPI for rendering PDF pages
    "price_in_per_million": 0.40,  # gpt-4.1-mini pricing
    "price_out_per_million": 1.60,
    "max_workers": 5,  # Concurrent pages to process
}



# Required fields for validation
REQUIRED_KEYS = [
    "product_name",
    "sku",
    "sizes",
    "wholesale_price",
    "retail_price",
    "colors",
]

# =============================================================================
# Prompt for Vision extraction
# =============================================================================

# =============================================================================
# Prompt for PDF Type Detection
# =============================================================================

PDF_TYPE_DETECTION_PROMPT = """You are an expert at classifying fashion industry PDF documents.

Look at this PDF page image and determine what type of document this is.

DOCUMENT TYPES:
1. "linesheet" - A product catalog/linesheet showing multiple products with:
   - Product photos arranged in grid or list
   - SKU/style numbers, wholesale prices, retail prices
   - Size ranges, color options
   - Typically from brands/manufacturers for buyers

2. "order_confirmation" - An order confirmation/purchase order with:
   - "Order Confirmation", "Purchase Order", "Order Summary" header
   - Buyer information section
   - ORDER SUMMARY table with columns like Product Name, Item Code, Color, Size, Price
   - PRODUCT SPECIFICATIONS section
   - Terms and conditions, shipping info

3. "unknown" - If you cannot determine the document type

Look at the FIRST PAGE carefully. Check for:
- Headers like "Order Confirmation", "Purchase Order" → order_confirmation
- Multiple product photos in catalog layout → linesheet
- ORDER SUMMARY table → order_confirmation
- Wholesale/retail price lists with many products → linesheet

Return ONLY valid JSON:
{
  "pdf_type": "linesheet" or "order_confirmation" or "unknown",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation of why you classified it this way"
}"""

# =============================================================================
# Prompt for Order Confirmation extraction
# =============================================================================

ORDER_CONFIRMATION_PROMPT = """You are an expert product data extractor for fashion order confirmations.

Look at this PDF page image and extract ALL products visible in the ORDER SUMMARY table.

FIRST: Determine if this page contains product information.
- If the page is a cover page, terms & conditions, shipping info, or any page WITHOUT actual product listings in ORDER SUMMARY, return: {"products": [], "page_notes": "No product information on this page", "has_products": false}
- If the page HAS product information in ORDER SUMMARY table, extract all products below.

For EACH product in the ORDER SUMMARY table, extract:
- product_name: Full product name/title (e.g., "PICA SHIRT")
- sku: Item Code (e.g., "2401-CHA")
- season: Season info if shown (look for "Season:" field)
- wholesale_price: Wholesale Price Per Unit (number only, no $)
- retail_price: Recommended Retail Price (RRP) from PRODUCT SPECIFICATIONS (number only, no $)
- sizes: Size Options as a string (e.g., "XS/S, M/L" or "10")
- quantity: Quantity ordered (look for "Qty", "Quantity", "Units", or similar columns - number only). Default to 1 if not visible.
- colors: Color Options as array (e.g., ["Black", "Natural"])
- colorway: null (not typically in order confirmations)
- material: Composition from PRODUCT SPECIFICATIONS (e.g., "100% Cotton")
- description: Description from PRODUCT SPECIFICATIONS
- certifications: Certifications if shown (e.g., "OEKO-TEX Certified, Fairtrade")
- origin: Origin/Made in info (e.g., "Made in Portugal")
- image_bboxes: Array of bounding boxes for product images if visible. Each bbox is [x_percent, y_percent, width_percent, height_percent] as percentages of page dimensions (0-100).

ALSO extract order metadata if visible:
- order_id: Order ID, Order Number, PO Number, Confirmation Number, or similar identifier
- currency: Currency (e.g., "USD")
- buyer_name: Buyer name
- order_type: Order type (e.g., "Internal / Sample Order")

IMPORTANT RULES:
1. Extract ALL products from the ORDER SUMMARY table - don't skip any
2. Match PRODUCT SPECIFICATIONS to the correct product (they appear after the table)
3. For image_bboxes, estimate the position and size of each product image as percentage of page dimensions
4. If a field is not visible, set it to null
5. Return prices as numbers without currency symbols
6. Be precise with Item Codes - copy exactly as shown

Return ONLY valid JSON in this format:
{
  "products": [
    {
      "product_name": "PICA SHIRT",
      "sku": "2401-CHA",
      "season": null,
      "wholesale_price": 125.00,
      "retail_price": 313.00,
      "sizes": "XS/S, M/L, 10",
      "quantity": 5,
      "colors": ["Black", "Natural"],
      "colorway": null,
      "material": "100% Cotton",
      "description": "Oversize cotton shirt dress.",
      "certifications": "OEKO-TEX Certified, Fairtrade",
      "origin": "Made in Portugal",
      "image_bboxes": [[10, 20, 30, 40]]
    }
  ],
  "order_metadata": {
    "order_id": "OC-2024-001234",
    "currency": "USD",
    "buyer_name": "Rita Row",
    "order_type": "Internal / Sample Order"
  },
  "page_notes": "any relevant notes about the page",
  "has_products": true
}"""

# =============================================================================
# Prompt for Vision extraction (Linesheet)
# =============================================================================

VISION_PROMPT = """You are an expert product data extractor for fashion linesheets.

Look at this PDF page image and extract ALL products visible on the page.

FIRST: Determine if this page contains product information.
- If the page is a cover page, table of contents, brand story, contact info, or any page WITHOUT actual product listings (no product name, SKU, prices), return: {"products": [], "page_notes": "No product information on this page", "has_products": false}
- If the page HAS product information, extract all products below.

For EACH product, extract:
- product_name: Full product name/title
- sku: Style number, SKU, or product code (e.g., "2053-3041")
- season: Season info if shown (e.g., "fall 2023")
- wholesale_price: Wholesale/WS price (number only, no $)
- retail_price: MSRP/retail price (number only, no $)
- sizes: Available sizes as a string (e.g., "23-33" or "S, M, L, XL")
- colors: Color name(s) as array
- colorway: Colorway code if different from color name
- material: Material/fabric info if shown
- description: Any additional description text
- image_bboxes: Array of bounding boxes for ALL product images belonging to this product. Each bbox is [x_percent, y_percent, width_percent, height_percent] as percentages of page dimensions (0-100). Include ALL images for this product (main photo, alternate angles, color swatches if they show the product).

IMPORTANT RULES:
1. Extract ALL products on the page - don't skip any
2. For image_bboxes, estimate the position and size of each product image as percentage of page dimensions
3. If a product has multiple images (front/back views, different colors), include ALL their bboxes
4. If a field is not visible, set it to null
5. Return prices as numbers without currency symbols
6. Be precise with SKU/style numbers - copy exactly as shown

Return ONLY valid JSON in this format:
{
  "products": [
    {
      "product_name": "...",
      "sku": "...",
      "season": "...",
      "wholesale_price": 131.00,
      "retail_price": 288.00,
      "sizes": "23-33",
      "colors": ["brielle"],
      "colorway": "med/dk ind",
      "material": "...",
      "description": "...",
      "image_bboxes": [[10, 20, 30, 40], [50, 20, 30, 40]]
    }
  ],
  "page_notes": "any relevant notes about the page",
  "has_products": true
}"""

# =============================================================================
# Utilities
# =============================================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

# =============================================================================
# PDF to Image conversion
# =============================================================================

def render_page_to_base64(page: fitz.Page, dpi: int = 150) -> str:
    """Render a PDF page to base64-encoded PNG."""
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("utf-8")

def render_page_to_file(page: fitz.Page, output_path: Path, dpi: int = 150) -> str:
    """Render a PDF page to PNG file and return base64."""
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pix.save(str(output_path))
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("utf-8")


# =============================================================================
# Extract product images from PDF
# =============================================================================

def is_likely_product_image(
    width: int,
    height: int,
    bbox: Optional[List[float]],
    page_width: float,
    page_height: float,
) -> bool:
    """
    Filter out non-product images (logos, headers, footers, icons).
    
    Product images typically:
    - Have reasonable aspect ratio (not too wide/narrow like banners)
    - Are not at the very top of page (headers/logos)
    - Are not tiny icons
    - Have minimum size for product photos
    """
    # Minimum size for product images (pixels)
    MIN_PRODUCT_WIDTH = 100
    MIN_PRODUCT_HEIGHT = 100
    
    if width < MIN_PRODUCT_WIDTH or height < MIN_PRODUCT_HEIGHT:
        return False
    
    # Aspect ratio check - product images usually between 0.5 and 2.0
    aspect_ratio = width / max(height, 1)
    if aspect_ratio < 0.3 or aspect_ratio > 3.0:
        # Too wide (banner) or too tall (sidebar)
        return False
    
    # Position check - skip images at very top of page (likely headers/logos)
    if bbox:
        y_top = bbox[1]
        # If image top is in the top 8% of page, likely a header/logo
        if y_top < page_height * 0.08:
            # But allow if it's a large image (might be product at top)
            img_height_on_page = bbox[3] - bbox[1]
            if img_height_on_page < page_height * 0.15:
                return False
    
    # Size relative to page - product images are usually substantial
    if bbox:
        img_width_on_page = bbox[2] - bbox[0]
        img_height_on_page = bbox[3] - bbox[1]
        
        # Skip if too small relative to page (likely icons/decorations)
        if img_width_on_page < page_width * 0.1 and img_height_on_page < page_height * 0.1:
            return False
    
    return True


def extract_images_from_page(
    doc: fitz.Document,
    page: fitz.Page,
    images_dir: Path,
    page_index: int,
    min_width: int = 50,
    min_height: int = 50,
) -> Tuple[List[Dict[str, Any]], float, float]:
    """
    Extract product images from a PDF page.
    Filters out logos, headers, icons, and other non-product images.
    Returns (images_list, page_width, page_height).
    """
    images = []
    image_list = page.get_images(full=True)
    page_width = page.rect.width
    page_height = page.rect.height
    
    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        
        try:
            base_image = doc.extract_image(xref)
            if not base_image:
                continue
            
            image_bytes = base_image["image"]
            image_ext = base_image.get("ext", "png")
            width = base_image.get("width", 0)
            height = base_image.get("height", 0)
            
            # Basic size filter
            if width < min_width or height < min_height:
                continue
            
            # Get image position on page
            bbox = None
            for img_rect in page.get_image_rects(xref):
                bbox = [img_rect.x0, img_rect.y0, img_rect.x1, img_rect.y1]
                break
            
            # Smart filter - skip non-product images
            if not is_likely_product_image(width, height, bbox, page_width, page_height):
                print(f"[FILTER] Skipping non-product image: {width}x{height} at {bbox}")
                continue
            
            # Save image
            image_filename = f"page_{page_index + 1:03d}_img_{img_index + 1:03d}.{image_ext}"
            image_path = images_dir / image_filename
            
            with open(image_path, "wb") as f:
                f.write(image_bytes)
            
            images.append({
                "image_path": str(image_path),
                "image_filename": image_filename,
                "bbox": bbox,
                "width": width,
                "height": height,
                "page_index": page_index,
            })
            
        except Exception as e:
            print(f"[WARN] Failed to extract image {img_index} from page {page_index + 1}: {e}")
            continue
    
    return images, page_width, page_height


def calculate_iou(bbox1: List[float], bbox2: List[float]) -> float:
    """
    Calculate Intersection over Union (IoU) between two bboxes.
    bbox format: [x0, y0, x1, y1] (absolute coordinates)
    """
    x1 = max(bbox1[0], bbox2[0])
    y1 = max(bbox1[1], bbox2[1])
    x2 = min(bbox1[2], bbox2[2])
    y2 = min(bbox1[3], bbox2[3])
    
    if x2 <= x1 or y2 <= y1:
        return 0.0
    
    intersection = (x2 - x1) * (y2 - y1)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0


def percent_bbox_to_absolute(
    percent_bbox: List[float],
    page_width: float,
    page_height: float
) -> List[float]:
    """
    Convert percentage bbox [x%, y%, w%, h%] to absolute [x0, y0, x1, y1].
    """
    x_pct, y_pct, w_pct, h_pct = percent_bbox
    x0 = (x_pct / 100.0) * page_width
    y0 = (y_pct / 100.0) * page_height
    x1 = x0 + (w_pct / 100.0) * page_width
    y1 = y0 + (h_pct / 100.0) * page_height
    return [x0, y0, x1, y1]


def match_images_by_bbox(
    product_bboxes: List[List[float]],
    extracted_images: List[Dict[str, Any]],
    page_width: float,
    page_height: float,
    iou_threshold: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Match GPT-predicted bboxes with extracted images using IoU.
    Returns list of matched images with path and bbox.
    """
    matched_images = []
    used_image_indices = set()
    
    for pct_bbox in product_bboxes:
        if not pct_bbox or len(pct_bbox) != 4:
            continue
            
        # Convert percentage bbox to absolute
        abs_bbox = percent_bbox_to_absolute(pct_bbox, page_width, page_height)
        
        best_match = None
        best_iou = iou_threshold
        best_idx = -1
        
        for idx, img in enumerate(extracted_images):
            if idx in used_image_indices:
                continue
                
            img_bbox = img.get("bbox")
            if not img_bbox:
                continue
            
            iou = calculate_iou(abs_bbox, img_bbox)
            if iou > best_iou:
                best_iou = iou
                best_match = img
                best_idx = idx
        
        if best_match:
            used_image_indices.add(best_idx)
            matched_images.append({
                "path": best_match["image_path"],
                "bbox": best_match["bbox"]
            })
    
    return matched_images


def match_products_with_images(
    products: List[Dict[str, Any]],
    all_images: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Match extracted products with images based on page and position.
    Groups multiple images for the same product into an 'images' array.
    Each image has 'path' and 'bbox' fields.
    """
    # Group images by page
    images_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for img in all_images:
        page_idx = img.get("page_index", 0)
        if page_idx not in images_by_page:
            images_by_page[page_idx] = []
        images_by_page[page_idx].append(img)
    
    # Sort images on each page by vertical position (top to bottom)
    for page_idx in images_by_page:
        images_by_page[page_idx].sort(key=lambda x: (x.get("bbox") or [0, 0, 0, 0])[1])
    
    # Group products by page
    products_by_page: Dict[int, List[Dict[str, Any]]] = {}
    for p in products:
        page_num = p.get("_page", 1)
        page_idx = page_num - 1  # Convert to 0-indexed
        if page_idx not in products_by_page:
            products_by_page[page_idx] = []
        products_by_page[page_idx].append(p)
    
    # Match products with images on same page
    for page_idx, page_products in products_by_page.items():
        page_images = images_by_page.get(page_idx, [])
        
        # Simple 1:1 matching by order - add to images array
        for i, product in enumerate(page_products):
            if "images" not in product:
                product["images"] = []
            
            if i < len(page_images):
                img = page_images[i]
                product["images"].append({
                    "path": img["image_path"],
                    "bbox": img["bbox"]
                })
    
    return products


def group_images_by_product(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group products by SKU or product name.
    Merges images from same product across pages into single product entry.
    """
    grouped: Dict[str, Dict[str, Any]] = {}
    
    for product in products:
        # Use sku as primary key, fallback to product_name
        group_id = product.get("sku") or product.get("product_name", "unknown")
        
        if group_id not in grouped:
            # First occurrence - copy product data
            grouped[group_id] = {**product}
            if "images" not in grouped[group_id]:
                grouped[group_id]["images"] = []
            # Remove image_bboxes from final output (already processed)
            grouped[group_id].pop("image_bboxes", None)
        else:
            # Merge images from duplicate product entries
            existing = grouped[group_id]
            new_images = product.get("images", [])
            existing["images"].extend(new_images)
            
            # Keep track of all pages this product appears on
            if "_pages" not in existing:
                existing["_pages"] = [existing.get("_page", 1)]
            existing["_pages"].append(product.get("_page", 1))
    
    return list(grouped.values())

# =============================================================================
# Retry/backoff helpers
# =============================================================================

RETRYABLE_SUBSTRINGS = [
    "rate limit", "timeout", "temporarily unavailable",
    "connection", "server error", "502", "503", "504",
]

def is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in RETRYABLE_SUBSTRINGS)

def backoff_sleep(attempt: int, base: float, cap: float) -> None:
    sleep_s = min(cap, base * (2 ** attempt))
    sleep_s = sleep_s * (0.7 + 0.6 * random.random())
    time.sleep(sleep_s)

# =============================================================================
# OpenAI Vision API call
# =============================================================================

def call_vision_api(
    client: OpenAI,
    model: str,
    image_base64: str,
    prompt: str,
    max_output_tokens: int,
    max_retries: int,
    backoff_base_s: float,
    backoff_cap_s: float,
) -> Tuple[str, Dict[str, Any]]:
    """
    Call OpenAI Vision API with image.
    Returns (raw_text, usage_dict).
    """
    last_exc: Optional[Exception] = None
    usage: Dict[str, Any] = {}

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=max_output_tokens,
            )

            # Extract usage
            if response.usage:
                usage = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            # Extract response text
            raw = response.choices[0].message.content or ""
            return raw, usage

        except Exception as ex:
            last_exc = ex
            if attempt < max_retries and is_retryable(ex):
                backoff_sleep(attempt, backoff_base_s, backoff_cap_s)
                continue
            raise

    raise RuntimeError(f"Vision API call failed after retries: {last_exc}")


# =============================================================================
# PDF Type Detection
# =============================================================================

def detect_pdf_type(
    client: OpenAI,
    pdf_path: Path,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect PDF type by analyzing the first page.
    Returns dict with pdf_type, confidence, reason.
    """
    doc = fitz.open(pdf_path)
    
    try:
        # Render first page
        page = doc.load_page(0)
        image_base64 = render_page_to_base64(page, dpi=cfg["image_dpi"])
        
        # Call Vision API for detection
        raw, usage = call_vision_api(
            client=client,
            model=cfg["model"],
            image_base64=image_base64,
            prompt=PDF_TYPE_DETECTION_PROMPT,
            max_output_tokens=500,
            max_retries=cfg["max_retries"],
            backoff_base_s=cfg["backoff_base_s"],
            backoff_cap_s=cfg["backoff_cap_s"],
        )
        
        # Parse response
        parsed = parse_json_response(raw)
        
        if parsed and "pdf_type" in parsed:
            return {
                "pdf_type": parsed.get("pdf_type", "unknown"),
                "confidence": parsed.get("confidence", 0.0),
                "reason": parsed.get("reason", ""),
                "detection_usage": usage,
            }
        
        return {
            "pdf_type": "unknown",
            "confidence": 0.0,
            "reason": "Failed to parse detection response",
            "detection_usage": usage,
        }
        
    finally:
        doc.close()


# =============================================================================
# JSON parsing and validation
# =============================================================================

def parse_json_response(raw: str) -> Optional[Dict[str, Any]]:
    """Parse JSON from response, handling markdown code blocks."""
    text = raw.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def validate_products(obj: Any) -> List[Dict[str, Any]]:
    """Validate extracted products and return issues."""
    issues: List[Dict[str, Any]] = []
    
    if not isinstance(obj, dict):
        return [{"index": None, "error": "not a dict"}]
    
    products = obj.get("products")
    if not isinstance(products, list):
        return [{"index": None, "error": "no products array"}]
    
    for i, p in enumerate(products):
        if not isinstance(p, dict):
            issues.append({"index": i, "error": "not a dict"})
            continue
        
        missing = [k for k in REQUIRED_KEYS if k not in p or p[k] is None]
        if missing:
            issues.append({"index": i, "missing": missing})
    
    return issues

# =============================================================================
# Cost estimation
# =============================================================================

def estimate_cost(usage: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Estimate API cost from usage."""
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    
    cost_in = (inp / 1_000_000) * cfg.get("price_in_per_million", 0)
    cost_out = (out / 1_000_000) * cfg.get("price_out_per_million", 0)
    
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cost_in_usd": round(cost_in, 6),
        "cost_out_usd": round(cost_out, 6),
        "cost_total_usd": round(cost_in + cost_out, 6),
    }

# =============================================================================
# Page result dataclass
# =============================================================================

@dataclass
class PageResult:
    page_index: int
    status: str  # ok | error
    products_count: int
    raw_path: str
    json_path: Optional[str]
    image_path: str
    usage: Dict[str, Any]
    cost: Dict[str, Any]
    duration_seconds: float
    error: Optional[str] = None

@dataclass
class PreparedPage:
    """Pre-rendered page data ready for API call."""
    page_index: int
    image_base64: str
    page_image_path: Path
    product_images: List[Dict[str, Any]]
    page_width: float
    page_height: float
    raw_path: Path
    json_path: Path

# =============================================================================
# Phase 1: Render all pages to images
# =============================================================================

def prepare_all_pages(
    doc: fitz.Document,
    page_images_dir: Path,
    product_images_dir: Path,
    responses_dir: Path,
    cfg: Dict[str, Any],
) -> List[PreparedPage]:
    """Render all PDF pages to images. Returns list of PreparedPage."""
    prepared: List[PreparedPage] = []
    page_count = doc.page_count
    
    print(f"[RENDER] Converting {page_count} pages to images...")
    render_start = time.perf_counter()
    
    for page_index in range(page_count):
        page = doc.load_page(page_index)
        
        # Render page to image
        page_image_path = page_images_dir / f"page_{page_index + 1:03d}.png"
        image_base64 = render_page_to_file(page, page_image_path, dpi=cfg["image_dpi"])
        
        # Extract product images from this page (now returns page dimensions too)
        product_images, page_width, page_height = extract_images_from_page(
            doc=doc,
            page=page,
            images_dir=product_images_dir,
            page_index=page_index,
            min_width=50,
            min_height=50,
        )
        
        prepared.append(PreparedPage(
            page_index=page_index,
            image_base64=image_base64,
            page_image_path=page_image_path,
            product_images=product_images,
            page_width=page_width,
            page_height=page_height,
            raw_path=responses_dir / f"page_{page_index + 1:03d}.raw.txt",
            json_path=responses_dir / f"page_{page_index + 1:03d}.json",
        ))
    
    render_duration = round(time.perf_counter() - render_start, 2)
    print(f"[RENDER] Done in {render_duration}s")
    
    return prepared

# =============================================================================
# Phase 2: Process single page via API (for concurrent execution)
# =============================================================================

def process_prepared_page(
    client: OpenAI,
    prepared: PreparedPage,
    pdf_name: str,
    cfg: Dict[str, Any],
    prompt: str = VISION_PROMPT,
) -> Tuple[PageResult, List[Dict[str, Any]]]:
    """Process a pre-rendered page via API. Returns (PageResult, products)."""
    page_started = time.perf_counter()
    page_index = prepared.page_index
    
    try:
        # Call Vision API
        raw, usage = call_vision_api(
            client=client,
            model=cfg["model"],
            image_base64=prepared.image_base64,
            prompt=prompt,
            max_output_tokens=cfg["max_output_tokens"],
            max_retries=cfg["max_retries"],
            backoff_base_s=cfg["backoff_base_s"],
            backoff_cap_s=cfg["backoff_cap_s"],
        )
        
        # Save raw response
        write_text(prepared.raw_path, raw)
        
        # Parse response
        parsed = parse_json_response(raw)
        
        if parsed is None:
            return PageResult(
                page_index=page_index,
                status="error",
                products_count=0,
                raw_path=str(prepared.raw_path),
                json_path=None,
                image_path=str(prepared.page_image_path),
                usage=usage,
                cost=estimate_cost(usage, cfg),
                duration_seconds=round(time.perf_counter() - page_started, 3),
                error="JSON parse failed",
            ), []
        
        # Check if page has products
        has_products = parsed.get("has_products", True)
        products = parsed.get("products", [])
        
        if not has_products or not products:
            print(f"[SKIP] Page {page_index + 1}: No product information found")
            return PageResult(
                page_index=page_index,
                status="skipped",
                products_count=0,
                raw_path=str(prepared.raw_path),
                json_path=None,
                image_path=str(prepared.page_image_path),
                usage=usage,
                cost=estimate_cost(usage, cfg),
                duration_seconds=round(time.perf_counter() - page_started, 3),
                error=None,
            ), []
        
        # Add metadata to products
        for p in products:
            p["_page"] = page_index + 1
            p["_source_pdf"] = pdf_name
            # Default quantity to 1 if not present or null
            if p.get("quantity") is None:
                p["quantity"] = 1
        
        # Match images with products using GPT-provided bboxes
        for p in products:
            image_bboxes = p.get("image_bboxes", [])
            if image_bboxes:
                # Use IoU matching with GPT bboxes
                matched = match_images_by_bbox(
                    image_bboxes,
                    prepared.product_images,
                    prepared.page_width,
                    prepared.page_height,
                    iou_threshold=0.05  # Lower threshold for flexibility
                )
                p["images"] = matched
            else:
                p["images"] = []
            
            # Remove image_bboxes from output (already processed)
            p.pop("image_bboxes", None)
        
        # Save with matched images
        parsed["products"] = products
        write_json(prepared.json_path, parsed)
        
        # Attach order_metadata to products if present (for order confirmations)
        order_metadata = parsed.get("order_metadata")
        if order_metadata:
            for p in products:
                p["_order_metadata"] = order_metadata
        
        # Validate
        issues = validate_products(parsed)
        
        print(f"[OK] Page {page_index + 1}: {len(products)} products extracted")
        
        return PageResult(
            page_index=page_index,
            status="ok" if not issues else "ok_with_issues",
            products_count=len(products),
            raw_path=str(prepared.raw_path),
            json_path=str(prepared.json_path),
            image_path=str(prepared.page_image_path),
            usage=usage,
            cost=estimate_cost(usage, cfg),
            duration_seconds=round(time.perf_counter() - page_started, 3),
            error=None if not issues else f"{len(issues)} validation issues",
        ), products
        
    except Exception as ex:
        write_text(prepared.raw_path, f"[ERROR]\n{str(ex)}")
        print(f"[ERROR] Page {page_index + 1}: {ex}")
        return PageResult(
            page_index=page_index,
            status="error",
            products_count=0,
            raw_path=str(prepared.raw_path),
            json_path=None,
            image_path=str(prepared.page_image_path),
            usage={},
            cost={},
            duration_seconds=round(time.perf_counter() - page_started, 3),
            error=str(ex),
        ), []

# =============================================================================
# Main extraction function
# =============================================================================

def process_pdf(
    client: OpenAI,
    pdf_path: Path,
    out_dir: Path,
    cfg: Dict[str, Any],
    prompt: str = VISION_PROMPT,
) -> Dict[str, Any]:
    """Process a single PDF file with 2-phase processing."""
    
    # Create output directories
    responses_dir = ensure_dir(out_dir / "responses")
    page_images_dir = ensure_dir(out_dir / "page_images")
    product_images_dir = ensure_dir(out_dir / "product_images")
    
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    max_workers = cfg.get("max_workers", 5)
    
    started = time.perf_counter()
    
    # Phase 1: Render all pages to images (fast, CPU-bound)
    prepared_pages = prepare_all_pages(
        doc, page_images_dir, product_images_dir, responses_dir, cfg
    )
    
    # Collect all extracted images
    all_extracted_images: List[Dict[str, Any]] = []
    for pp in prepared_pages:
        all_extracted_images.extend(pp.product_images)
    
    doc.close()
    
    # Phase 2: Process all pages via API concurrently
    print(f"[API] Processing {page_count} pages with {max_workers} workers...")
    
    all_products: List[Dict[str, Any]] = []
    page_results: List[PageResult] = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_prepared_page,
                client, pp, pdf_path.name, cfg, prompt
            ): pp.page_index
            for pp in prepared_pages
        }
        
        for future in as_completed(futures):
            page_result, products = future.result()
            page_results.append(page_result)
            all_products.extend(products)
    
    # Sort results by page index
    page_results.sort(key=lambda x: x.page_index)
    all_products.sort(key=lambda x: x.get("_page", 0))
    
    # Group products by image_group_id (merge same products across pages)
    grouped_products = group_images_by_product(all_products)
    
    duration = round(time.perf_counter() - started, 3)
    
    # Calculate total usage
    total_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for pr in page_results:
        for k in total_usage:
            total_usage[k] += pr.usage.get(k, 0)
    
    # Write merged results with grouped products
    merged_path = out_dir / "merged.json"
    write_json(merged_path, {"products": grouped_products})
    
    # Write extracted images info
    images_info_path = out_dir / "extracted_images.json"
    write_json(images_info_path, {"images": all_extracted_images})
    
    # Calculate totals
    total_cost = estimate_cost(total_usage, cfg)
    ok_pages = sum(1 for r in page_results if r.status.startswith("ok"))
    skipped_pages = sum(1 for r in page_results if r.status == "skipped")
    products_with_images = sum(1 for p in grouped_products if p.get("images"))
    total_images_matched = sum(len(p.get("images", [])) for p in grouped_products)
    
    result = {
        "pdf": str(pdf_path),
        "pdf_name": pdf_path.name,
        "page_count": page_count,
        "duration_seconds": duration,
        "counts": {
            "pages_total": page_count,
            "pages_ok": ok_pages,
            "pages_skipped": skipped_pages,
            "pages_error": page_count - ok_pages - skipped_pages,
            "products_total": len(grouped_products),
            "products_raw": len(all_products),
            "products_with_images": products_with_images,
            "images_extracted": len(all_extracted_images),
            "images_matched": total_images_matched,
        },
        "usage": total_usage,
        "cost": total_cost,
        "paths": {
            "run_dir": str(out_dir),
            "merged_json": str(merged_path),
            "page_images_dir": str(page_images_dir),
            "product_images_dir": str(product_images_dir),
            "responses_dir": str(responses_dir),
        },
        "page_results": [asdict(r) for r in page_results],
        "products": grouped_products,
        "extracted_images": all_extracted_images,
    }
    
    # Write metadata
    write_json(out_dir / "run-metadata.json", result)
    
    return result


# =============================================================================
# Type definitions for return values
# =============================================================================

class VisionProductImage(TypedDict):
    """Image matched to a product."""
    path: str  # Local file path to the image
    bbox: List[float]  # Bounding box [x0, y0, x1, y1] in absolute coordinates


class OrderMetadata(TypedDict, total=False):
    """Order metadata for order confirmation documents."""
    order_id: Optional[str]
    currency: Optional[str]
    buyer_name: Optional[str]
    order_type: Optional[str]


class VisionProduct(TypedDict, total=False):
    """Product extracted from PDF using Vision API.
    
    This represents the structure of products returned from extract_products_from_pdf.
    All fields are optional except those marked as required in REQUIRED_KEYS.
    """
    # Core product fields (from API response)
    product_name: Optional[str]
    sku: Optional[str]
    season: Optional[str]
    wholesale_price: Optional[float]
    retail_price: Optional[float]
    sizes: Optional[str]
    colors: Optional[List[str]]  # Array of color names
    colorway: Optional[str]
    material: Optional[str]
    description: Optional[str]
    certifications: Optional[str]
    origin: Optional[str]
    quantity: Optional[int]  # Defaults to 1 if not present
    
    # Image bounding boxes (percentage format from API, removed after matching)
    image_bboxes: Optional[List[List[float]]]  # [[x%, y%, w%, h%], ...]
    
    # Matched images (added after image matching)
    images: Optional[List[VisionProductImage]]  # List of matched images with path and bbox
    
    # Metadata fields (added during processing)
    _page: Optional[int]  # Page number where product was found (1-indexed)
    _source_pdf: Optional[str]  # PDF filename
    _order_metadata: Optional[OrderMetadata]  # Order metadata for order confirmations
    pdf_type: Optional[str]  # "linesheet" or "order_confirmation"
    _pages: Optional[List[int]]  # All pages this product appears on (after grouping)


class ExtractionCounts(TypedDict):
    """Counts from PDF extraction."""
    pages_total: int
    pages_ok: int
    pages_skipped: int
    pages_error: int
    products_total: int
    products_raw: int
    products_with_images: int
    images_extracted: int
    images_matched: int


class ExtractionUsage(TypedDict):
    """Token usage from API calls."""
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ExtractionCost(TypedDict):
    """Cost estimation from API usage."""
    input_tokens: int
    output_tokens: int
    cost_in_usd: float
    cost_out_usd: float
    cost_total_usd: float


class ExtractionPaths(TypedDict):
    """Paths to output files and directories."""
    run_dir: str
    merged_json: str
    page_images_dir: str
    product_images_dir: str
    responses_dir: str


class DetectionInfo(TypedDict, total=False):
    """PDF type detection information."""
    pdf_type: str
    confidence: float
    reason: str
    detection_usage: Dict[str, Any]


class ExtractionResult(TypedDict):
    """Return type for extract_products_from_pdf function."""
    pdf: str
    pdf_name: str
    pdf_type: str  # "linesheet" or "order_confirmation"
    page_count: int
    duration_seconds: float
    counts: ExtractionCounts
    usage: ExtractionUsage
    cost: ExtractionCost
    paths: ExtractionPaths
    page_results: List[Dict[str, Any]]
    products: List[VisionProduct]  # List of VisionProduct dictionaries
    extracted_images: List[Dict[str, Any]]  # List of extracted image dictionaries
    order_metadata: Optional[OrderMetadata]  # Order metadata for order confirmations (None for linesheets)


class ExtractionResultWithDetection(ExtractionResult, total=False):
    """ExtractionResult with optional detection_info."""
    detection_info: DetectionInfo


# =============================================================================
# Public API
# =============================================================================

def extract_products_from_pdf(
    pdf_path: str,
    out_dir: str,
    config_overrides: Optional[Dict[str, Any]] = None,
    create_run_subdir: bool = True,
    doc_type: str = "auto",
) -> ExtractionResultWithDetection:
    """
    Extract products from a PDF using GPT-4o Vision.
    
    Args:
        pdf_path: Path to the PDF file
        out_dir: Output directory
        config_overrides: Override default config values
        create_run_subdir: Create timestamped subdirectory
        doc_type: Document type - "auto", "linesheet", or "order_confirmation"
                  If "auto", will detect type from first page
        
    Returns:
        Dict with extraction results including pdf_type field
    """
    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    # Merge config
    cfg = {**CONFIG}
    if config_overrides:
        cfg.update(config_overrides)
    
    # Resolve paths - use separate variables to avoid type conflicts
    pdf_path_resolved = Path(pdf_path).expanduser().resolve()
    if not pdf_path_resolved.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path_resolved}")
    
    out_dir_resolved = Path(out_dir).expanduser().resolve()
    
    # Create run directory
    if create_run_subdir:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir: Path = out_dir_resolved / f"run_{run_id}"
    else:
        run_dir = out_dir_resolved
    
    ensure_dir(run_dir)
    
    # Create client - ensure timeout is float
    timeout_value: Any = cfg.get("timeout_s", 120.0)
    if isinstance(timeout_value, str):
        timeout_float = float(timeout_value)
    elif isinstance(timeout_value, (int, float)):
        timeout_float = float(timeout_value)
    else:
        timeout_float = 120.0
    client = OpenAI(timeout=timeout_float)
    
    # Auto-detect PDF type if needed
    detection_info = None
    if doc_type == "auto":
        print(f"[DETECT] Auto-detecting PDF type...")
        detection_info = detect_pdf_type(client, pdf_path_resolved, cfg)
        detected_type = detection_info["pdf_type"]
        confidence = detection_info["confidence"]
        reason = detection_info["reason"]
        print(f"[DETECT] Type: {detected_type} (confidence: {confidence:.0%})")
        print(f"[DETECT] Reason: {reason}")
        doc_type = detected_type if detected_type != "unknown" else "linesheet"
    
    # Select prompt based on document type
    if doc_type == "order_confirmation":
        prompt = ORDER_CONFIRMATION_PROMPT
    else:
        prompt = VISION_PROMPT
    
    # Process PDF
    result = process_pdf(client, pdf_path_resolved, run_dir, cfg, prompt)
    
    # Add pdf_type to result (at the top level)
    result["pdf_type"] = doc_type
    if detection_info:
        result["detection_info"] = detection_info
        # Add detection usage to total
        det_usage = detection_info.get("detection_usage", {})
        result["usage"]["input_tokens"] += det_usage.get("input_tokens", 0)
        result["usage"]["output_tokens"] += det_usage.get("output_tokens", 0)
        result["usage"]["total_tokens"] += det_usage.get("total_tokens", 0)
        # Recalculate cost
        result["cost"] = estimate_cost(result["usage"], cfg)
    
    # Update metadata file with pdf_type
    write_json(run_dir / "run-metadata.json", result)
    
    # Update merged.json with pdf_type at the top
    merged_data = {
        "pdf_type": doc_type,
        "products": result["products"],
    }
    
    # Extract order_metadata from products if order_confirmation
    order_metadata: Optional[OrderMetadata] = None
    if doc_type == "order_confirmation":
        for p in result.get("products", []):
            if "_order_metadata" in p:
                order_metadata = cast(OrderMetadata, p["_order_metadata"])
                break
        if order_metadata:
            merged_data["order_metadata"] = order_metadata
            result["order_metadata"] = order_metadata
            # Remove _order_metadata from products (already at top level)
            for p in result["products"]:
                p.pop("_order_metadata", None)
        else:
            result["order_metadata"] = None
    else:
        result["order_metadata"] = None
    
    if detection_info:
        merged_data["detection_reason"] = detection_info.get("reason", "")
    write_json(run_dir / "merged.json", merged_data)
    
    return cast(ExtractionResultWithDetection, result)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    ap = argparse.ArgumentParser(description="PDF Extraction Service (GPT-4o Vision)")
    ap.add_argument("--pdf", required=True, help="Path to PDF file")
    ap.add_argument("--out_dir", default="./outputs", help="Output directory")
    ap.add_argument("--dpi", type=int, default=150, help="Image DPI (default: 150)")
    ap.add_argument("--type", choices=["auto", "linesheet", "order_confirmation"], default="auto",
                    help="Document type: auto (detect), linesheet, or order_confirmation (default: auto)")
    
    args = ap.parse_args()
    
    result = extract_products_from_pdf(
        pdf_path=args.pdf,
        out_dir=args.out_dir,
        config_overrides={"image_dpi": args.dpi},
        doc_type=args.type,
    )
    
    print(f"\n✅ Done!")
    print(f"📄 PDF Type: {result.get('pdf_type', 'unknown')}")
    print(f"Run dir: {result['paths']['run_dir']}")
    print(f"\n📊 Results:")
    print(f"   Pages processed: {result['counts']['pages_ok']}/{result['counts']['pages_total']}")
    print(f"   Pages skipped (no products): {result['counts']['pages_skipped']}")
    print(f"   Products found: {result['counts']['products_total']}")
    print(f"   Duration: {result['duration_seconds']}s")
    print(f"\n💰 Cost:")
    print(f"   Input tokens: {result['usage']['input_tokens']}")
    print(f"   Output tokens: {result['usage']['output_tokens']}")
    print(f"   Estimated cost: ${result['cost']['cost_total_usd']:.4f}")
    
    print(f"\n📦 Products extracted:")
    for p in result["products"][:5]:  # Show first 5
        img_status = "✅" if p.get("image_path") else "❌"
        print(f"   {img_status} {p.get('product_name')} | SKU: {p.get('sku')} | WS: ${p.get('wholesale_price')} | MSRP: ${p.get('retail_price')}")
    
    if len(result["products"]) > 5:
        print(f"   ... and {len(result['products']) - 5} more")
    
    print(f"\n�️  ImDages:")
    print(f"   Extracted: {result['counts']['images_extracted']}")
    print(f"   Matched to products: {result['counts']['products_with_images']}/{result['counts']['products_total']}")
