"""FinSignal — financial newsletter pipeline.

Reads financial newsletters from Gmail, extracts stock ticker recommendations,
and cross-references them with Polymarket prediction markets.
"""
from .gmail_reader import GmailReader
from .newsletter_parser import parse_email, TickerMention
from .polymarket_matcher import match_ticker_to_markets

__all__ = ["GmailReader", "parse_email", "TickerMention", "match_ticker_to_markets"]
