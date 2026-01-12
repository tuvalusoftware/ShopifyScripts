#!/usr/bin/env python3
"""Step5Util: Utility functions for extracting images from PDFs near product names."""
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import fitz  # PyMuPDF  # type: ignore

if TYPE_CHECKING:
    from fitz import Page, Rect, Document, Matrix, Pixmap  # type: ignore
else:
    Page = Any
    Rect = Any
    Document = Any
    Matrix = Any
    Pixmap = Any

from utils.logger import get_logger

logger = get_logger(__name__)


def safe_filename(s: str, max_len: int = 140) -> str:
    """Convert string to safe filename."""
    s = (s or "").strip() or "product"
    s = re.sub(r"[^\w\-.() ]+", "_", s)
    s = re.sub(r"\s+", " ", s).strip().replace(" ", "_")
    return s[:max_len]


def normalize_for_search(s: str) -> str:
    """Normalize string for text search."""
    return re.sub(r"\s+", " ", s.strip())


def search_name_rects(page: "Page", name: str) -> List["Rect"]:  # type: ignore
    """Search for product name text in PDF page."""
    rects: List["Rect"] = page.search_for(name)  # type: ignore
    if rects:
        return rects  # type: ignore
    norm = normalize_for_search(name)
    if norm != name:
        rects2: List["Rect"] = page.search_for(norm)  # type: ignore
        return rects2 or []  # type: ignore
    return []  # type: ignore


def get_image_bboxes_from_page(page: "Page") -> List["Rect"]:  # type: ignore
    """Extract image bounding boxes from PDF page."""
    d: Dict[str, Any] = page.get_text("dict")  # type: ignore
    bboxes: List["Rect"] = []  # type: ignore
    for block in d.get("blocks", []):  # type: ignore
        if isinstance(block, dict) and block.get("type") == 1:  # type: ignore
            bbox = block.get("bbox")  # type: ignore
            if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:  # type: ignore
                bboxes.append(fitz.Rect(bbox))  # type: ignore
    return bboxes  # type: ignore


def overlap_1d(a0: float, a1: float, b0: float, b1: float) -> float:
    """Calculate 1D overlap between two intervals."""
    return max(0.0, min(a1, b1) - max(a0, b0))


def overlap_frac_x(text_rect: "Rect", img_rect: "Rect") -> float:  # type: ignore
    """Calculate horizontal overlap fraction."""
    denom = max(1e-6, min(text_rect.width, img_rect.width))  # type: ignore
    return overlap_1d(text_rect.x0, text_rect.x1, img_rect.x0, img_rect.x1) / denom  # type: ignore


def overlap_frac_y(text_rect: "Rect", img_rect: "Rect") -> float:  # type: ignore
    """Calculate vertical overlap fraction."""
    denom = max(1e-6, min(text_rect.height, img_rect.height))  # type: ignore
    return overlap_1d(text_rect.y0, text_rect.y1, img_rect.y0, img_rect.y1) / denom  # type: ignore


def is_banner_like(  # type: ignore
    img_rect: "Rect",  # type: ignore
    page_rect: "Rect",  # type: ignore
    max_w_frac: float = 0.92,
    max_h_frac: float = 0.92,
) -> bool:
    """Check if image is banner-like (too large, likely header/logo)."""
    return (img_rect.width >= page_rect.width * max_w_frac) and (  # type: ignore
        img_rect.height >= page_rect.height * max_h_frac  # type: ignore
    )


def pick_best_image_for_text(  # type: ignore
    text_rect: "Rect",  # type: ignore
    images: List["Rect"],  # type: ignore
    page_rect: "Rect",  # type: ignore
    tolerance: float,
    min_x_overlap_above: float = 0.25,
    min_y_overlap_left: float = 0.20,
) -> Tuple[Optional["Rect"], Optional[str]]:
    """
    Pick best image for text position.
    
    Returns (image_rect, position) where position is "ABOVE" or "LEFT".
    Prefers ABOVE if any qualifying candidate exists, otherwise considers LEFT.
    """
    # ---- ABOVE candidates ----
    above: List[Tuple[float, float, float, "Rect"]] = []  # type: ignore
    for ir in images:  # type: ignore
        if is_banner_like(ir, page_rect):  # type: ignore
            continue
        if ir.y1 <= text_rect.y0 + tolerance:  # type: ignore
            if overlap_frac_x(text_rect, ir) < min_x_overlap_above:  # type: ignore
                continue
            gap = text_rect.y0 - ir.y1  # type: ignore
            area = ir.get_area()  # type: ignore
            above.append((gap, -area, ir.x0, ir))  # type: ignore
    above.sort()  # type: ignore
    if above:
        return above[0][3], "ABOVE"  # type: ignore

    # ---- LEFT candidates ----
    left: List[Tuple[float, float, float, "Rect"]] = []  # type: ignore
    for ir in images:  # type: ignore
        if is_banner_like(ir, page_rect):  # type: ignore
            continue
        if ir.x1 <= text_rect.x0 + tolerance:  # type: ignore
            if overlap_frac_y(text_rect, ir) < min_y_overlap_left:  # type: ignore
                continue
            gap = text_rect.x0 - ir.x1  # type: ignore
            area = ir.get_area()  # type: ignore
            left.append((gap, -area, ir.y0, ir))  # type: ignore
    left.sort()  # type: ignore
    if left:
        return left[0][3], "LEFT"  # type: ignore

    return None, None


def crop_rect_to_png(page: "Page", rect: "Rect", out_path: Path, dpi: int) -> bool:  # type: ignore
    """Crop PDF page region to PNG file."""
    rect = rect & page.rect  # type: ignore
    if rect.is_empty:  # type: ignore
        return False
    zoom = dpi / 72.0
    pix: "Pixmap" = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect, alpha=False)  # type: ignore
    pix.save(str(out_path))  # type: ignore
    return True


def compute_name_color_hash(product_name: str, color: Optional[Any], length: int = 12) -> str:
    """
    Generate deterministic hash from (product_name, color).
    
    Args:
        product_name: Product name string
        color: Color value (may be None, string, or other type)
        length: Length of hash prefix to return
        
    Returns:
        Short lowercase hex prefix
    """
    pn = (product_name or "").strip()
    if color is None:
        c = ""
    elif isinstance(color, str):
        c = color.strip()
    else:
        c = str(color).strip()

    payload = f"{pn}\n{c}".encode("utf-8", errors="replace")
    return hashlib.sha256(payload).hexdigest()[: max(4, int(length))]


def extract_images_for_products(
    products: List[Dict[str, Any]],
    pdf_path: Path,
    output_dir: Path,
    dpi: int = 200,
    tolerance: float = 18.0,
    min_x_overlap_above: float = 0.25,
    min_y_overlap_left: float = 0.20,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Extract images from PDF for given products.
    
    Args:
        products: List of product dictionaries (must have 'product_name' and optionally 'color')
        pdf_path: Path to PDF file
        output_dir: Directory to save extracted images
        dpi: DPI for image extraction
        tolerance: Tolerance for image proximity search
        min_x_overlap_above: Minimum horizontal overlap for ABOVE images
        min_y_overlap_left: Minimum vertical overlap for LEFT images
        
    Returns:
        Tuple of (enriched_products, canary_counts)
        - enriched_products: Products with extracted_image_name, extracted_image_page, extracted_image_position
        - canary_counts: Dict with "ABOVE", "LEFT", "NONE" counts
    """
    if not pdf_path.exists():
        logger.warning(f"PDF file not found: {pdf_path}")
        return products, {"ABOVE": 0, "LEFT": 0, "NONE": len(products)}

    # Create output subdirectory for this PDF
    pdf_stem = pdf_path.stem
    pdf_out_dir = output_dir / pdf_stem
    pdf_out_dir.mkdir(parents=True, exist_ok=True)

    canary_counts = {"ABOVE": 0, "LEFT": 0, "NONE": 0}
    enriched_products: List[Dict[str, Any]] = []

    try:
        doc: "Document" = fitz.open(pdf_path)  # type: ignore
        page_images: List[List["Rect"]] = [  # type: ignore
            get_image_bboxes_from_page(doc[i]) for i in range(len(doc))  # type: ignore
        ]

        for idx, product in enumerate(products, start=1):
            # Create copy of product dict
            enriched_product = dict(product)

            name = product.get("product_name")
            color = product.get("color")

            if not isinstance(name, str) or not name.strip():
                enriched_product["extracted_image_name"] = None
                enriched_product["extracted_image_page"] = None
                enriched_product["extracted_image_position"] = None
                enriched_products.append(enriched_product)
                canary_counts["NONE"] += 1
                continue

            name = name.strip()
            name_safe = safe_filename(name)

            # Generate hash for filename
            h = compute_name_color_hash(name, color)

            saved_image_name: Optional[str] = None
            saved_image_page: Optional[int] = None
            saved_image_position: Optional[str] = None

            # Search for product name in PDF pages
            for page_index in range(len(doc)):  # type: ignore
                page: "Page" = doc[page_index]  # type: ignore
                rects: List["Rect"] = search_name_rects(page, name)  # type: ignore
                if not rects:
                    continue

                images: List["Rect"] = page_images[page_index]  # type: ignore
                if not images:
                    continue

                # Sort text rects by position (top to bottom, left to right)
                rects_sorted: List["Rect"] = sorted(rects, key=lambda r: (r.y0, r.x0))  # type: ignore
                for text_rect in rects_sorted:  # type: ignore
                    img_rect: Optional["Rect"]
                    pos: Optional[str]
                    img_rect, pos = pick_best_image_for_text(  # type: ignore
                        text_rect=text_rect,  # type: ignore
                        images=images,
                        page_rect=page.rect,  # type: ignore
                        tolerance=tolerance,
                        min_x_overlap_above=min_x_overlap_above,
                        min_y_overlap_left=min_y_overlap_left,
                    )
                    if img_rect is None or pos is None:
                        continue

                    # Generate filename
                    filename = (
                        f"{h}__{idx:04d}__p{page_index+1:03d}__{pos}__{name_safe}.png"
                    )
                    out_path = pdf_out_dir / filename

                    # Crop and save image
                    ok = crop_rect_to_png(page, img_rect, out_path, dpi=dpi)  # type: ignore
                    if not ok:
                        continue

                    # Store relative path from output_dir
                    saved_image_name = f"{pdf_stem}/{filename}"
                    saved_image_page = page_index + 1
                    saved_image_position = pos
                    canary_counts[pos] += 1

                    logger.debug(
                        f"Extracted image: {pdf_path.name} p{page_index+1} "
                        f"name='{name}' position={pos} -> {filename}"
                    )

                    # Stop after finding first image for this product
                    break

                # Stop scanning pages if we already saved an image
                if saved_image_name is not None:
                    break

            if saved_image_name is None:
                canary_counts["NONE"] += 1

            enriched_product["extracted_image_name"] = saved_image_name
            enriched_product["extracted_image_page"] = saved_image_page
            enriched_product["extracted_image_position"] = saved_image_position
            enriched_products.append(enriched_product)

        doc.close()  # type: ignore

    except Exception as ex:
        logger.error(f"Error processing PDF {pdf_path}: {ex}")
        # Return products without enrichment on error
        for product in products:
            enriched_product = dict(product)
            enriched_product["extracted_image_name"] = None
            enriched_product["extracted_image_page"] = None
            enriched_product["extracted_image_position"] = None
            enriched_products.append(enriched_product)
        canary_counts["NONE"] = len(products)

    return enriched_products, canary_counts
