#!/usr/bin/env python3
"""
Upload files from a directory and invoke a ChatGPT-style model with a prompt read from a local file.

Enhancements in this refactor:
1) Output directory support:
   - --out_dir specifies where outputs are written (directory is created if missing)
   - Each run creates a unique run folder under out_dir (or you can disable with --no_run_subdir)
2) Per-file outputs:
   - One model call per input file
   - Writes one response file per input file
3) Run metadata:
   - Writes run-metadata.json with run settings + per-file status, file_ids, timings, etc.

API note:
- This script uses the Responses API (recommended) with input_file.
- Requires: pip install openai
- Env: export OPENAI_API_KEY="..."

Usage:
  python ExtractProductsFromLinesheets.py \
    --dir ./docs \
    --prompt_file ./prompt.txt \
    --out_dir ./outputs \
    --model gpt-4.1-mini \
    --ext .pdf .txt .md \
    --response_ext .json

Example prompt.txt:
  Extract product name, sku, sizes, wholesale price, retail price, colors, and full description.
  Return JSON.

"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from openai import OpenAI

from domain.DynamoServiceClient import DynamoServiceClient

 
# -------------------------
# Defaults
# -------------------------
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_OUTPUT_TOKENS = 20000


# -------------------------
# Helpers
# -------------------------
def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise ValueError(f"Prompt file is empty after trimming: {path}")
    return text


def normalize_exts(exts: Optional[List[str]]) -> Optional[set]:
    if not exts:
        return None
    norm = set()
    for e in exts:
        e = e.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        norm.add(e)
    return norm if norm else None


def iter_files(root: Path, exts: Optional[set], recursive: bool) -> Iterable[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    it = root.rglob("*") if recursive else root.iterdir()
    for p in sorted(it):
        if not p.is_file():
            continue
        if exts is not None and p.suffix.lower() not in exts:
            continue
        yield p


def safe_stem(name: str) -> str:
    # Keep it readable and filesystem-safe
    stem = re.sub(r"[^\w\-\.]+", "_", name.strip(), flags=re.UNICODE)
    stem = re.sub(r"_+", "_", stem).strip("._-")
    return stem or "file"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def make_run_dir(out_dir: Path, make_subdir: bool) -> Path:
    out_dir = ensure_dir(out_dir.expanduser().resolve())
    if not make_subdir:
        return out_dir
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = out_dir / f"run_{run_id}"
    ensure_dir(run_dir)
    return run_dir


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


# -------------------------
# OpenAI interactions
# -------------------------
def upload_file(client: OpenAI, path: Path, purpose: str = "assistants") -> str:
    """
    Upload a file and return file_id.
    Note: purpose values can vary; 'assistants' is commonly used for general file usage.
    """
    with path.open("rb") as f:
        resp = client.files.create(file=f, purpose=purpose)
    return resp.id


def call_responses_with_file(
    client: OpenAI,
    model: str,
    prompt: str,
    file_id: str,
    filename: str,
    max_output_tokens: int,
) -> str:
    """
    Use Responses API with an input_file.
    """
    resp = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_text", "text": f"\n\nProcessing file: {filename}"},
                    {"type": "input_file", "file_id": file_id},
                ],
            }
        ],
        max_output_tokens=max_output_tokens,
    )

    # The SDK returns structured output; `output_text` is the easiest plain-text getter if available.
    # Fallback: try to reconstruct from output items.
    if hasattr(resp, "output_text") and resp.output_text:
        return resp.output_text

    # Fallback extraction (best effort)
    chunks: List[str] = []
    try:
        for item in resp.output:
            if getattr(item, "type", None) == "message":
                for c in item.content:
                    if getattr(c, "type", None) in ("output_text", "text"):
                        chunks.append(getattr(c, "text", "") or "")
    except Exception:
        pass

    return "\n".join([c for c in chunks if c]).strip()


def parse_products_from_response(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse products from OpenAI response text.
    Handles JSON wrapped in markdown code blocks or plain JSON.
    
    Args:
        response_text: Response text from OpenAI containing JSON.
        
    Returns:
        List of product dictionaries.
    """
    if not response_text:
        return []
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        response_text = json_match.group(1)
    else:
        # Try to find JSON object directly
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
    
    try:
        result = json.loads(response_text)
        if isinstance(result, dict) and "products" in result:
            return result.get("products", [])
        elif isinstance(result, list):
            return result
        else:
            return []
    except json.JSONDecodeError:
        return []


def create_products_from_list(
    dynamo_client: DynamoServiceClient,
    products: List[Dict[str, Any]],
) -> Tuple[int, int, List[str]]:
    """
    Create products via DynamoServiceClient API.
    
    Args:
        dynamo_client: DynamoServiceClient instance.
        products: List of product dictionaries.
        
    Returns:
        Tuple of (success_count, error_count, error_messages).
    """
    success_count = 0
    error_count = 0
    error_messages = []
    
    for product in products:
        try:
            # Convert product dict to properties format expected by API
            # Remove None values to clean up the payload
            properties = {k: v for k, v in product.items() if v is not None}
            
            # Ensure properties is not empty
            if not properties:
                error_count += 1
                error_messages.append("Product has no properties")
                continue
            
            # Call API to create product
            dynamo_client.create_product(properties=properties)
            success_count += 1
        except Exception as ex:
            error_count += 1
            error_msg = f"Failed to create product '{product.get('product_name', 'unknown')}': {str(ex)}"
            error_messages.append(error_msg)
            eprint(f"ERROR: {error_msg}")
    
    return success_count, error_count, error_messages


# -------------------------
# Metadata structures
# -------------------------
@dataclass
class FileResult:
    input_path: str
    input_name: str
    input_size_bytes: int
    input_sha256: str
    uploaded_file_id: Optional[str] = None
    status: str = "pending"  # pending|ok|skipped|error
    skipped_reason: Optional[str] = None
    started_at_utc: Optional[str] = None
    finished_at_utc: Optional[str] = None
    duration_seconds: Optional[float] = None
    response_path: Optional[str] = None
    error: Optional[str] = None
    products_extracted: int = 0
    products_created_success: int = 0
    products_created_error: int = 0
    product_creation_errors: Optional[List[str]] = None


@dataclass
class RunMetadata:
    run_started_at_utc: str
    run_finished_at_utc: Optional[str]
    duration_seconds: Optional[float]
    model: str
    prompt_file: str
    input_dir: str
    recursive: bool
    exts: Optional[List[str]]
    max_files: int
    max_bytes: int
    max_output_tokens: int
    out_dir: str
    run_dir: str
    response_ext: str
    upload_purpose: str
    files_total_seen: int
    files_uploaded: int
    files_ok: int
    files_skipped: int
    files_error: int
    total_products_extracted: int
    total_products_created_success: int
    total_products_created_error: int
    file_results: List[Dict]


# -------------------------
# Main
# -------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Directory containing files to upload")
    ap.add_argument("--prompt_file", required=True, help="Path to a text file containing the prompt")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    ap.add_argument("--ext", nargs="*", default=None, help="Extensions to include, e.g. .pdf .txt .md (default: all)")
    ap.add_argument("--recursive", action="store_true", help="Recurse into subdirectories")

    ap.add_argument("--max_files", type=int, default=50, help="Max number of files to process (default: 50)")
    default_max_bytes = int(os.getenv("MAX_BYTES", "20000000"))
    ap.add_argument("--max_bytes", type=int, default=default_max_bytes, help=f"Skip files larger than this (default: {default_max_bytes} bytes, configurable via MAX_BYTES env var)")
    ap.add_argument("--max_output_tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS, help="Max output tokens")

    ap.add_argument("--out_dir", default="./outputs", help="Directory where outputs are written")
    ap.add_argument("--no_run_subdir", action="store_true", help="Write outputs directly into --out_dir (no run_*)")
    ap.add_argument("--response_ext", default=".txt", help="Per-file response file extension (.txt/.md/.json)")
    ap.add_argument("--upload_purpose", default="assistants", help="OpenAI file upload purpose (default: assistants)")

    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        eprint("ERROR: OPENAI_API_KEY is not set.")
        return 2

    # Initialize DynamoServiceClient if DYNAMO_SERVICE_API_URL is set
    dynamo_client = None
    try:
        dynamo_client = DynamoServiceClient()
        eprint(f"DynamoServiceClient initialized with API URL: {dynamo_client.get_api_url()}")
    except ValueError:
        eprint("WARNING: DYNAMO_SERVICE_API_URL is not set. Products will be extracted but not created via API.")

    client = OpenAI()

    input_dir = Path(args.dir).expanduser().resolve()
    prompt_path = Path(args.prompt_file).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()

    # Prepare run directory
    run_dir = make_run_dir(out_dir, make_subdir=not args.no_run_subdir)
    responses_dir = ensure_dir(run_dir / "responses")

    # Read prompt
    try:
        prompt = read_text_file(prompt_path)
    except Exception as ex:
        eprint(f"ERROR reading prompt: {ex}")
        return 2

    # Collect files
    exts = normalize_exts(args.ext)
    files: List[Path] = []
    try:
        for p in iter_files(input_dir, exts=exts, recursive=bool(args.recursive)):
            files.append(p)
            if len(files) >= args.max_files:
                break
    except Exception as ex:
        eprint(f"ERROR scanning directory: {ex}")
        return 2

    run_started = time.time()
    run_started_iso = utc_now_iso()

    file_results: List[FileResult] = []
    files_total_seen = len(files)

    # Process each file
    for p in files:
        fr = FileResult(
            input_path=str(p),
            input_name=p.name,
            input_size_bytes=p.stat().st_size,
            input_sha256="",
        )

        fr.started_at_utc = utc_now_iso()
        t0 = time.time()

        try:
            if fr.input_size_bytes > args.max_bytes:
                fr.status = "skipped"
                fr.skipped_reason = f"too_large>{args.max_bytes}"
                file_results.append(fr)
                continue

            fr.input_sha256 = sha256_file(p)

            # Upload
            eprint(f"Uploading: {p.name} ({fr.input_size_bytes} bytes)")
            file_id = upload_file(client, p, purpose=args.upload_purpose)
            fr.uploaded_file_id = file_id

            # Call model (per-file)
            eprint(f"Invoking model for: {p.name}")
            text = call_responses_with_file(
                client=client,
                model=args.model,
                prompt=prompt,
                file_id=file_id,
                filename=p.name,
                max_output_tokens=args.max_output_tokens,
            )

            # Write per-file response
            base = safe_stem(p.stem)
            short_hash = fr.input_sha256[:12] if fr.input_sha256 else "nohash"
            resp_name = f"{base}__{short_hash}{args.response_ext if args.response_ext.startswith('.') else '.'+args.response_ext}"
            resp_path = responses_dir / resp_name
            write_text(resp_path, text)

            fr.response_path = str(resp_path)
            
            # Parse products from response and create them via API
            if dynamo_client:
                products = parse_products_from_response(text)
                fr.products_extracted = len(products)
                
                if products:
                    eprint(f"Found {len(products)} products in {p.name}, creating via API...")
                    success_count, error_count, error_messages = create_products_from_list(
                        dynamo_client, products
                    )
                    fr.products_created_success = success_count
                    fr.products_created_error = error_count
                    if error_messages:
                        fr.product_creation_errors = error_messages
                    eprint(f"Created {success_count} products successfully, {error_count} errors")
                else:
                    eprint(f"No products found in response for {p.name}")
            
            fr.status = "ok"

        except Exception as ex:
            fr.status = "error"
            fr.error = str(ex)

        finally:
            fr.finished_at_utc = utc_now_iso()
            fr.duration_seconds = round(time.time() - t0, 3)
            file_results.append(fr)

    # Aggregate run stats
    files_uploaded = sum(1 for r in file_results if r.uploaded_file_id)
    files_ok = sum(1 for r in file_results if r.status == "ok")
    files_skipped = sum(1 for r in file_results if r.status == "skipped")
    files_error = sum(1 for r in file_results if r.status == "error")
    total_products_extracted = sum(r.products_extracted for r in file_results)
    total_products_created_success = sum(r.products_created_success for r in file_results)
    total_products_created_error = sum(r.products_created_error for r in file_results)

    run_finished_iso = utc_now_iso()
    run_duration = round(time.time() - run_started, 3)

    # Write run metadata
    meta = RunMetadata(
        run_started_at_utc=run_started_iso,
        run_finished_at_utc=run_finished_iso,
        duration_seconds=run_duration,
        model=args.model,
        prompt_file=str(prompt_path),
        input_dir=str(input_dir),
        recursive=bool(args.recursive),
        exts=args.ext,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
        max_output_tokens=args.max_output_tokens,
        out_dir=str(out_dir),
        run_dir=str(run_dir),
        response_ext=args.response_ext if args.response_ext.startswith(".") else "." + args.response_ext,
        upload_purpose=args.upload_purpose,
        files_total_seen=files_total_seen,
        files_uploaded=files_uploaded,
        files_ok=files_ok,
        files_skipped=files_skipped,
        files_error=files_error,
        total_products_extracted=total_products_extracted,
        total_products_created_success=total_products_created_success,
        total_products_created_error=total_products_created_error,
        file_results=[asdict(r) for r in file_results],
    )
    meta_path = run_dir / "run-metadata.json"
    write_json(meta_path, asdict(meta))

    # Also write a short summary to stderr
    eprint(
        f"\nDone.\n"
        f"Run dir: {run_dir}\n"
        f"Responses: {responses_dir}\n"
        f"Metadata: {meta_path}\n"
        f"File counts: seen={files_total_seen} uploaded={files_uploaded} ok={files_ok} skipped={files_skipped} error={files_error}\n"
        f"Product counts: extracted={total_products_extracted} created_success={total_products_created_success} created_error={total_products_created_error}\n"
    )

    # Exit code: 0 if no errors, else 1
    return 0 if files_error == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
