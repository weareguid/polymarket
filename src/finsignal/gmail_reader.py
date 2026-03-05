"""
Gmail reader for FinSignal newsletter pipeline.

Connects via IMAP to Gmail and retrieves financial newsletters.
Requires Gmail App Password (Settings → Security → App Passwords).
"""
import re
import os
import email
import imaplib
import logging
from datetime import datetime, timedelta
from email.header import decode_header
from typing import List, Dict

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("polymarket.finsignal")

GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_PASSWORD = os.getenv("GMAIL_PASSWORD", "")

# Sender patterns that indicate financial newsletters
NEWSLETTER_SENDER_PATTERNS = [
    "morningbrew", "morning brew",
    "seekingalpha", "seeking alpha",
    "motleyfool", "motley fool", "fool.com",
    "briefing.com",
    "thestreet",
    "barron",
    "wsj", "wall street journal",
    "bloomberg",
    "reuters",
    "cnbc",
    "marketwatch",
    "businessinsider", "insider.com",
    "benzinga",
    "zacks",
    "schaeffersresearch",
    "investopedia",
    "alphastreet",
    "the daily upside",
    "finimize",
    "robinhoodsnacks",
    "axios markets",
]

# Finance keywords for unknown senders
FINANCE_KEYWORDS = [
    "stock", "shares", "earnings", "revenue", "portfolio",
    "market cap", "price target", "buy rating", "sell rating",
    "dividend", "analyst", "upgrade", "downgrade", "P/E ratio",
]


def _decode_header_value(raw: str) -> str:
    """Decode MIME-encoded email header value."""
    parts = []
    for chunk, encoding in decode_header(raw or ""):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return " ".join(parts)


def _extract_body(msg) -> str:
    """Extract plain text from email message, stripping HTML tags as fallback."""
    plain = ""
    html = ""

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                plain += text
            elif ctype == "text/html":
                html += text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            ctype = msg.get_content_type()
            text = payload.decode("utf-8", errors="replace")
            if ctype == "text/plain":
                plain = text
            else:
                html = text

    if plain:
        return plain
    # Minimal HTML → text
    return re.sub(r"<[^>]+>", " ", html)


def _is_financial_email(sender: str, subject: str, body: str) -> bool:
    """Heuristic: is this a financial newsletter worth parsing?"""
    sender_lower = sender.lower()
    if any(p in sender_lower for p in NEWSLETTER_SENDER_PATTERNS):
        return True

    # Check body for finance density
    body_lower = body.lower()
    hits = sum(1 for kw in FINANCE_KEYWORDS if kw in body_lower)
    return hits >= 3


class GmailReader:
    """Reads financial newsletters from Gmail via IMAP SSL."""

    def __init__(self, days_back: int = 7, max_emails: int = 200):
        self.address = GMAIL_ADDRESS
        self.password = GMAIL_PASSWORD
        self.days_back = days_back
        self.max_emails = max_emails

    def fetch_newsletters(self) -> List[Dict]:
        """
        Connect to Gmail, fetch recent emails, return those that look like
        financial newsletters.

        Returns list of dicts: uid, sender, subject, date, body.
        """
        if not self.address or not self.password:
            logger.error("GMAIL_ADDRESS or GMAIL_PASSWORD missing in .env")
            return []

        results = []
        try:
            logger.info(f"Connecting to Gmail IMAP as {self.address}…")
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(self.address, self.password)
            mail.select("INBOX")

            since_str = (datetime.now() - timedelta(days=self.days_back)).strftime("%d-%b-%Y")
            _, raw_uids = mail.search(None, f'SINCE "{since_str}"')
            uids = raw_uids[0].split() if raw_uids[0] else []

            # Most recent first
            uids = uids[::-1][: self.max_emails]
            logger.info(f"Scanning {len(uids)} emails from last {self.days_back} days…")

            for uid in uids:
                try:
                    _, data = mail.fetch(uid, "(RFC822)")
                    if not data or not data[0]:
                        continue
                    msg = email.message_from_bytes(data[0][1])

                    sender  = _decode_header_value(msg.get("From", ""))
                    subject = _decode_header_value(msg.get("Subject", ""))
                    date    = msg.get("Date", "")
                    body    = _extract_body(msg)[:6000]

                    if _is_financial_email(sender, subject, body):
                        results.append({
                            "uid":     uid.decode(),
                            "sender":  sender,
                            "subject": subject,
                            "date":    date,
                            "body":    body,
                        })
                except Exception as exc:
                    logger.debug(f"Error reading email {uid}: {exc}")

            mail.logout()

        except imaplib.IMAP4.error as exc:
            logger.error(
                f"IMAP login failed: {exc}\n"
                "Tip: Use a Gmail App Password (not your regular password).\n"
                "Create one at myaccount.google.com → Security → App Passwords."
            )
        except Exception as exc:
            logger.error(f"Gmail reader error: {exc}")

        logger.info(f"Found {len(results)} financial newsletter emails")
        return results
