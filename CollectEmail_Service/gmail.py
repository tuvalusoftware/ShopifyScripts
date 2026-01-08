#!/usr/bin/env python3
import os
import re
import json
import argparse
import imaplib
from email.message import Message
from email.header import decode_header
from email.utils import parseaddr
from datetime import datetime
from typing import Dict, Any, List, Optional
from email import message_from_bytes
try:
    import chardet
except ImportError:
    chardet = None


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


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
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            if enc:
                try:
                    out.append(chunk.decode(enc, errors="replace"))
                except Exception:
                    out.append(chunk.decode("utf-8", errors="replace"))
            else:
                # guess encoding
                if chardet:
                    guess = chardet.detect(chunk).get("encoding") or "utf-8"
                    out.append(chunk.decode(guess, errors="replace"))
                else:
                    out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out).strip()


def extract_text_from_message(msg: Message) -> str:
    """
    Prefer text/plain. If only HTML exists, returns stripped HTML-ish text.
    """
    text_parts: List[str] = []
    html_parts: List[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()

            # skip attachments
            if "attachment" in disp:
                continue

            payload = part.get_payload(decode=True)
            if payload is None:
                continue

            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("utf-8", errors="replace")

            if ctype == "text/plain":
                text_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except Exception:
            decoded = payload.decode("utf-8", errors="replace")
        if msg.get_content_type() == "text/plain":
            text_parts.append(decoded)
        elif msg.get_content_type() == "text/html":
            html_parts.append(decoded)

    if text_parts:
        return "\n".join(t.strip() for t in text_parts if t and t.strip()).strip()

    # very simple HTML-to-text fallback (no external libs)
    if html_parts:
        html = "\n".join(html_parts)
        # remove script/style blocks
        html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
        # replace <br> and </p> with newlines
        html = re.sub(r"(?i)<br\s*/?>", "\n", html)
        html = re.sub(r"(?i)</p\s*>", "\n\n", html)
        # strip tags
        html = re.sub(r"(?s)<.*?>", "", html)
        # unescape minimal entities
        html = html.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        html = re.sub(r"\n{3,}", "\n\n", html)
        return html.strip()

    return ""


def download_attachments(msg: Message, out_dir: str, prefix: str) -> List[Dict[str, Any]]:
    saved: List[Dict[str, Any]] = []
    ensure_dir(out_dir)

    idx = 0
    for part in msg.walk():
        disp = (part.get("Content-Disposition") or "").lower()
        filename = part.get_filename()

        is_attachment = ("attachment" in disp) or bool(filename)
        if not is_attachment:
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue

        idx += 1
        filename_decoded = safe_filename(decode_mime_words(filename) if filename else f"attachment_{idx}")
        path = os.path.join(out_dir, f"{prefix}_{idx:02d}_{filename_decoded}")

        try:
            with open(path, "wb") as f:
                f.write(payload)
        except Exception as e:
            print(f"Failed to save attachment {filename_decoded}: {e}")
            continue

        saved.append({
            "filename": filename_decoded,
            "path": path,
            "content_type": part.get_content_type(),
            "size": len(payload),
        })

    return saved


def imap_connect(email_addr: str, app_password: str) -> imaplib.IMAP4_SSL:
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(email_addr, app_password)
    return imap


def main():
    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="Collect emails from Gmail")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Base output directory (default: current directory)"
    )
    parser.add_argument(
        "--raw-emails-dir",
        type=str,
        default="raw_emails",
        help="Directory for raw .eml files (default: raw_emails)"
    )
    parser.add_argument(
        "--attachments-dir",
        type=str,
        default="attachments",
        help="Directory for attachments (default: attachments)"
    )
    parser.add_argument(
        "--json-file",
        type=str,
        default="emails.json",
        help="Output JSON filename (default: emails.json)"
    )
    args = parser.parse_args()

    # Recommended: do NOT hardcode secrets
    EMAIL_ADDR = os.getenv("GMAIL_EMAIL", "")
    APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

    if not EMAIL_ADDR or not APP_PASSWORD:
        raise SystemExit(
            "Missing credentials.\n"
            "Set env vars:\n"
            "  export GMAIL_EMAIL='you@domain.com'\n"
            "  export GMAIL_APP_PASSWORD='16charapppassword'\n"
        )

    # Build paths relative to output-dir
    output_dir = os.path.abspath(args.output_dir)
    raw_emails_dir = os.path.join(output_dir, args.raw_emails_dir)
    attachments_dir = os.path.join(output_dir, args.attachments_dir)
    out_json = os.path.join(output_dir, args.json_file)
    
    mark_seen = True  # set True if you want to mark as read after processing

    imap = imap_connect(EMAIL_ADDR, APP_PASSWORD)

    # Read-only mode (does not prevent server from setting \Seen if you fetch RFC822,
    # but we will explicitly control flags below)
    imap.select("INBOX")

    # Search unread
    status, data = imap.search(None, "UNSEEN")
    if status != "OK":
        imap.logout()
        raise RuntimeError(f"IMAP search failed: {status}")

    msg_ids = data[0].split()
    print(f"Found {len(msg_ids)} unread messages")

    # Generate timestamp for this batch to ensure unique filenames
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    records: List[Dict[str, Any]] = []
    ensure_dir(attachments_dir)
    ensure_dir(raw_emails_dir)

    for i, msg_id in enumerate(msg_ids, start=1):
        # Fetch full raw email
        status, msg_data = imap.fetch(msg_id, "(RFC822)")
        if status != "OK":
            print(f"[{i}/{len(msg_ids)}] fetch failed for {msg_id!r}")
            continue

        raw = msg_data[0][1]
        msg = message_from_bytes(raw)
        
        prefix = f"msg{timestamp}_{i:04d}"
        raw_email_path = os.path.join(raw_emails_dir, f"{prefix}.eml")
        try:
            with open(raw_email_path, "wb") as f:
                f.write(raw)
        except Exception as e:
            print(f"[{i}/{len(msg_ids)}] Failed to write raw email: {e}")
            continue
        
        subject = decode_mime_words(msg.get("Subject"))
        from_raw = decode_mime_words(msg.get("From"))
        sender_name, sender_email = parseaddr(from_raw)
        sender_email = (sender_email or "").strip()

        date_hdr = decode_mime_words(msg.get("Date"))

        body_text = extract_text_from_message(msg)

        atts = download_attachments(msg, attachments_dir, prefix)

        rec = {
            "imap_id": msg_id.decode("utf-8", errors="replace") if isinstance(msg_id, bytes) else str(msg_id),
            "from_raw": from_raw,
            "sender_email": sender_email,
            "subject": subject,
            "date": date_hdr,
            "body_text": body_text,
            "attachments": atts,
        }
        records.append(rec)

        # Mark read or keep unread
        if mark_seen:
            imap.store(msg_id, "+FLAGS", "\\Seen")
        else:
            # Attempt to keep as unread (some servers still set Seen after RFC822 fetch)
            imap.store(msg_id, "-FLAGS", "\\Seen")

        print(f"[{i}/{len(msg_ids)}] {subject or '(no subject)'} | from {sender_email or from_raw}")

    out = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "count": len(records),
        "emails": records,
    }

    try:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"Wrote {out_json}")
    except Exception as e:
        print(f"Failed to write JSON file: {e}")
        raise
    
    print(f"Attachments saved to: {attachments_dir}")
    print(f"Raw emails saved to: {raw_emails_dir}")

    imap.logout()


if __name__ == "__main__":
    main()
