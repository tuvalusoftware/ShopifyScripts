#!/usr/bin/env python3
import os
import re
import json
import argparse
from typing import Any, Dict, List, Optional, Tuple
from email import message_from_bytes
from email.header import decode_header
from email.utils import parseaddr
from email.message import Message


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_filename(name: str, max_len: int = 180) -> str:
    name = (name or "").strip().replace("\x00", "")
    name = re.sub(r"[^\w\-.() \[\]]+", "_", name)
    if not name:
        return "attachment"
    if len(name) > max_len:
        root, ext = os.path.splitext(name)
        name = root[: max_len - len(ext) - 1] + "_" + ext
    return name


def decode_mime_words(s: Optional[str]) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out: List[str] = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out).strip()


def html_to_text(html: str) -> str:
    # Lightweight HTML -> text (no external deps)
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p\s*>", "\n\n", html)
    html = re.sub(r"(?s)<.*?>", "", html)
    html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def extract_best_body(msg: Message) -> Tuple[str, str]:
    """
    Returns (body_text, body_kind) where body_kind is 'text/plain' or 'text/html' or ''.
    Preference: text/plain, else text/html converted to text.
    """
    text_parts: List[str] = []
    html_parts: List[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()

            # Skip attachments
            if "attachment" in disp:
                continue

            payload = part.get_payload(decode=True)
            if payload is None or not isinstance(payload, bytes):
                continue

            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("utf-8", errors="replace")

            if ctype == "text/plain" and decoded.strip():
                text_parts.append(decoded.strip())
            elif ctype == "text/html" and decoded.strip():
                html_parts.append(decoded.strip())
    else:
        payload = msg.get_payload(decode=True)
        if payload is None:
            payload = b""
        if not isinstance(payload, bytes):
            payload = b""
        
        charset = msg.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except Exception:
            decoded = payload.decode("utf-8", errors="replace")

        ctype = msg.get_content_type()
        if ctype == "text/plain" and decoded.strip():
            text_parts.append(decoded.strip())
        elif ctype == "text/html" and decoded.strip():
            html_parts.append(decoded.strip())

    if text_parts:
        return "\n\n".join(text_parts).strip(), "text/plain"
    if html_parts:
        return html_to_text("\n\n".join(html_parts)), "text/html"
    return "", ""


def save_attachments(msg: Message, out_dir: str, prefix: str) -> List[Dict[str, Any]]:
    """
    Save attachments to disk. Returns list of attachment metadata.
    """
    ensure_dir(out_dir)
    saved: List[Dict[str, Any]] = []
    idx = 0

    for part in msg.walk():
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()

        is_attachment = ("attachment" in disp) or bool(filename)
        if not is_attachment:
            continue

        payload = part.get_payload(decode=True)
        if payload is None or not isinstance(payload, bytes):
            continue

        idx += 1
        fname = safe_filename(decode_mime_words(filename) if filename else f"attachment_{idx}")
        path = os.path.join(out_dir, f"{prefix}_{idx:02d}_{fname}")

        with open(path, "wb") as f:
            f.write(payload)

        saved.append({
            "filename": fname,
            "path": path,
            "content_type": part.get_content_type(),
            "size": len(payload),
        })

    return saved


def parse_eml_file(eml_path: str, attachments_dir: str, prefix: str, save_atts: bool) -> Dict[str, Any]:
    with open(eml_path, "rb") as f:
        raw = f.read()

    msg = message_from_bytes(raw)

    from_raw = decode_mime_words(msg.get("From"))
    subject = decode_mime_words(msg.get("Subject"))
    date_hdr = decode_mime_words(msg.get("Date"))

    sender_name, sender_email = parseaddr(from_raw)
    sender_name = (sender_name or "").strip()
    sender_email = (sender_email or "").strip()

    body_text, body_kind = extract_best_body(msg)

    attachments: List[Dict[str, Any]] = []
    if save_atts:
        attachments = save_attachments(msg, attachments_dir, prefix)

    return {
        "eml_path": eml_path,
        "from_raw": from_raw,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "subject": subject,
        "date": date_hdr,
        "body_kind": body_kind,
        "body_text": body_text,
        "attachments": attachments,
    }


def iter_eml_paths(path: str) -> List[str]:
    if os.path.isfile(path):
        return [path]
    emls: List[str] = []
    for root, _, files in os.walk(path):
        for fn in files:
            if fn.lower().endswith(".eml"):
                emls.append(os.path.join(root, fn))
    emls.sort()
    return emls


def main():
    ap = argparse.ArgumentParser(description="Parse .eml files -> sender/subject/body/attachments + JSON output")
    ap.add_argument("--input", required=True, help="Path to a .eml file or a directory containing .eml files")
    ap.add_argument("--out-json", default="emails.json", help="Output JSON file")
    ap.add_argument("--attachments-dir", default="attachments_from_eml", help="Directory to save attachments")
    ap.add_argument("--no-attachments", action="store_true", help="Do not save attachments")
    args = ap.parse_args()

    eml_paths = iter_eml_paths(args.input)
    print(f"Found {len(eml_paths)} .eml file(s)")

    ensure_dir(args.attachments_dir)

    records: List[Dict[str, Any]] = []
    for i, eml_path in enumerate(eml_paths, start=1):
        # prefix based on filename order (stable). You can change this if you want.
        prefix = f"eml{i:04d}"
        try:
            rec = parse_eml_file(
                eml_path=eml_path,
                attachments_dir=args.attachments_dir,
                prefix=prefix,
                save_atts=(not args.no_attachments),
            )
            records.append(rec)
            print(f"[{i}/{len(eml_paths)}] {rec.get('subject') or '(no subject)'}")
        except Exception as e:
            print(f"[{i}/{len(eml_paths)}] ERROR parsing {eml_path}: {e}")

    out = {"count": len(records), "emails": records}
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {args.out_json}")
    if not args.no_attachments:
        print(f"Attachments saved to: {args.attachments_dir}")


if __name__ == "__main__":
    main()
