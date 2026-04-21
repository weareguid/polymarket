"""
Newsletter Parser — extracts stock ticker signals from financial newsletters.

Real financial newsletters DON'T say "BUY AAPL". They use analyst language:
  - "Apple's valuation looks compelling at these levels after the pullback"
  - "Morgan Stanley initiates Nvidia with Overweight, $1000 PT"
  - "Consider trimming your META position ahead of earnings"
  - "We see limited upside in Tesla given the competitive pressure"
  - "Goldman upgrades Boeing to Buy, raises PT to $260"

This parser detects those subtle signals using phrase-level matching with
negation awareness and multi-signal confidence scoring.
"""
import re
import logging
from dataclasses import dataclass
from typing import List, Dict, Tuple

logger = logging.getLogger("polymarket.finsignal")

# ─── Validated ticker universe ──────────────────────────────────────────────
# Reduces false positives from random all-caps words in email bodies
KNOWN_TICKERS = {
    # Big Tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "NFLX",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO", "TSM", "ASML", "ARM", "SMCI", "MU", "AMAT",
    # Finance
    "JPM", "BAC", "GS", "MS", "WFC", "C", "V", "MA", "AXP", "SCHW", "BLK",
    # Energy
    "XOM", "CVX", "BP", "COP", "OXY", "SLB",
    # Pharma/Health
    "JNJ", "PFE", "MRK", "ABBV", "LLY", "BMY", "AMGN", "GILD", "UNH", "HUM",
    # Media/Consumer
    "DIS", "CMCSA", "WBD", "NKE", "SBUX", "MCD", "WMT", "COST", "TGT", "HD",
    # Defense
    "BA", "LMT", "RTX", "NOC", "GD", "LHX",
    # Crypto-adjacent
    "COIN", "MSTR", "HOOD", "RIOT", "MARA",
    # Auto/EV
    "TSLA", "F", "GM", "RIVN", "TM",
    # Airlines
    "UAL", "DAL", "LUV", "AAL",
    # Industrial
    "CAT", "DE", "GE", "HON", "MMM", "EMR",
    # Telecom
    "T", "VZ", "TMUS",
    # ETFs
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "HYG",
    "XLF", "XLE", "XLK", "XLV", "XLI", "XLU",
    "VNQ", "KRE", "ITA", "KWEB", "VGK", "DXJ", "ERUS",
    "WEAT", "UNG", "USO",
    # Other notable
    "UBER", "LYFT", "ABNB", "DASH", "SHOP", "SQ", "PYPL", "SNAP", "PINS",
    "ORCL", "CRM", "ADBE", "NOW", "SNOW", "PLTR", "NET", "DDOG", "ZS",
}

# ─── Company name → ticker mapping ──────────────────────────────────────────
COMPANY_TO_TICKER = {
    # Big Tech
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "meta": "META", "facebook": "META", "nvidia": "NVDA",
    "tesla": "TSLA", "netflix": "NFLX",
    # Semiconductors
    "amd": "AMD", "intel": "INTC", "qualcomm": "QCOM", "broadcom": "AVGO",
    "tsmc": "TSM", "taiwan semiconductor": "TSM", "asml": "ASML",
    # Finance
    "jpmorgan": "JPM", "jp morgan": "JPM", "bank of america": "BAC",
    "goldman sachs": "GS", "morgan stanley": "MS", "wells fargo": "WFC",
    "citigroup": "C", "visa": "V", "mastercard": "MA", "blackrock": "BLK",
    # Energy
    "exxonmobil": "XOM", "exxon mobil": "XOM", "exxon": "XOM",
    "chevron": "CVX", "bp": "BP", "conocophillips": "COP", "schlumberger": "SLB",
    # Pharma
    "johnson & johnson": "JNJ", "pfizer": "PFE", "merck": "MRK",
    "abbvie": "ABBV", "eli lilly": "LLY", "lilly": "LLY",
    "bristol myers": "BMY", "amgen": "AMGN", "gilead": "GILD",
    "unitedhealth": "UNH", "united health": "UNH",
    # Consumer
    "disney": "DIS", "nike": "NKE", "starbucks": "SBUX", "mcdonald": "MCD",
    "walmart": "WMT", "costco": "COST", "target": "TGT", "home depot": "HD",
    # Defense
    "boeing": "BA", "lockheed martin": "LMT", "lockheed": "LMT",
    "raytheon": "RTX", "northrop grumman": "NOC", "general dynamics": "GD",
    # Crypto
    "coinbase": "COIN", "microstrategy": "MSTR", "robinhood": "HOOD",
    # Auto
    "ford": "F", "general motors": "GM", "rivian": "RIVN", "toyota": "TM",
    # Airlines
    "united airlines": "UAL", "delta": "DAL", "southwest": "LUV", "american airlines": "AAL",
    # Other
    "uber": "UBER", "lyft": "LYFT", "airbnb": "ABNB", "doordash": "DASH",
    "shopify": "SHOP", "square": "SQ", "block": "SQ", "paypal": "PYPL",
    "snap": "SNAP", "oracle": "ORCL", "salesforce": "CRM", "adobe": "ADBE",
    "snowflake": "SNOW", "palantir": "PLTR", "cloudflare": "NET",
    "philip morris": "PM", "beyond meat": "BYND",
}

# ─── Ticker detection patterns ───────────────────────────────────────────────
# These locate WHERE a ticker is mentioned in text.
# Direction comes from the sentence context, not these patterns.
_TICKER_PATTERNS = [
    re.compile(r'\$([A-Z]{1,5})\b'),                                           # $AAPL
    re.compile(r'\(([A-Z]{2,5})\)'),                                           # (AAPL)
    re.compile(r'\b([A-Z]{2,5})\s+(?:stock|shares|ETF|calls|puts|options)\b'), # AAPL stock
    re.compile(r'\b([A-Z]{2,5})\s+(?:upgraded|downgraded|reiterated|initiated)\b'),  # AAPL upgraded
]

# ─── Bullish semantic signals (phrase → weight) ──────────────────────────────
# Weight reflects how strongly the phrase implies a bullish view.
# Range 0.40 – 0.90; confidence is derived from summed weights.
_BULLISH_SIGNALS: List[Tuple[re.Pattern, float]] = [
    # Rating actions — strongest signals
    (re.compile(r'initiat\w*\s+(?:with\s+)?(?:buy|overweight|outperform|strong\s+buy)', re.I), 0.90),
    (re.compile(r'upgrad\w*\s+(?:to\s+)?(?:buy|overweight|outperform|strong\s+buy)', re.I), 0.90),
    (re.compile(r'reiterat\w*\s+(?:buy|overweight|outperform|strong\s+buy)', re.I), 0.85),
    (re.compile(r'\b(?:buy|overweight|outperform|strong\s+buy)\s+rating\b', re.I), 0.80),
    (re.compile(r'\bupgraded?\b', re.I), 0.55),   # "AAPL upgraded" without context → mild

    # Price target increases
    (re.compile(r'(?:raises?|increases?|lifts?|hikes?|bumps?)\s+(?:(?:its?|the|our)\s+)?(?:price\s+)?(?:target|pt)\b', re.I), 0.75),
    (re.compile(r'(?:price\s+)?(?:target|pt)\s+(?:raised?|increased?|lifted?|bumped?)\b', re.I), 0.75),
    (re.compile(r'new\s+(?:price\s+)?(?:target|pt)\s+(?:of\s+)?\$\d', re.I), 0.65),

    # Valuation / sentiment
    (re.compile(r'\b(?:compelling|attractive|favorable|cheap)\s+(?:valuation|entry|opportunity|risk.reward)\b', re.I), 0.70),
    (re.compile(r'valuation\s+(?:(?:looks?|seems?|appears?|is)\s+)?(?:compelling|attractive|favorable|cheap)\b', re.I), 0.70),
    (re.compile(r'(?:see[s]?|find[s]?|offer[s]?)\s+(?:significant\s+|meaningful\s+)?upside\b', re.I), 0.65),
    (re.compile(r'\bupside\s+(?:potential|opportunity|case|scenario)\b', re.I), 0.60),
    (re.compile(r'\bundervalued\b|\bunder.?appreciated\b|\bunder.?owned\b', re.I), 0.65),
    (re.compile(r'\btop\s+pick\b|\bhigh.?conviction\b|\bfavorite\s+(?:pick|name|idea|hold)\b', re.I), 0.80),
    (re.compile(r'\bbuy\s+the\s+(?:dip|weakness|pullback)\b', re.I), 0.75),
    (re.compile(r'\bpositive\s+(?:catalyst|momentum|outlook|setup|surprise)\b', re.I), 0.55),
    (re.compile(r'\bstrong\s+(?:growth|earnings|momentum|outlook|demand|execution)\b', re.I), 0.50),
    (re.compile(r'\btailwind[s]?\b', re.I), 0.45),
    (re.compile(r'(?:well|best|ideally).?positioned\s+(?:for|to)\b', re.I), 0.55),
    (re.compile(r'\bdiscount\s+to\s+(?:peers|sector|fair\s+value|intrinsic|history)\b', re.I), 0.55),

    # Action language from the newsletter author
    (re.compile(r'(?:add(?:ing)?|increas(?:ing)?|build(?:ing)?|accumulate?|accumulating)\s+(?:(?:to|our|your|the)\s+)?(?:position|exposure|stake|holdings?)\b', re.I), 0.70),
    (re.compile(r'(?:initiat(?:ing)?\s+(?:a\s+)?|entering\s+(?:a\s+)?|open(?:ing)?\s+(?:a\s+)?)(?:long\s+)?position\b', re.I), 0.70),
    (re.compile(r'\bload(?:ing)?\s+up\b', re.I), 0.65),
]

# ─── Bearish semantic signals ────────────────────────────────────────────────
_BEARISH_SIGNALS: List[Tuple[re.Pattern, float]] = [
    # Rating actions — strongest signals
    (re.compile(r'downgrad\w*\s+(?:to\s+)?(?:sell|underperform|underweight|reduce|avoid)\b', re.I), 0.90),
    (re.compile(r'cuts?\s+(?:to\s+)?(?:sell|underperform|underweight|avoid)\b', re.I), 0.85),
    (re.compile(r'\b(?:sell|underperform|underweight|reduce)\s+rating\b', re.I), 0.80),
    (re.compile(r'\bdowngraded?\b', re.I), 0.55),  # without context → mild

    # Price target cuts
    (re.compile(r'(?:cuts?|reduces?|lowers?|trims?|slashes?)\s+(?:(?:its?|the|our)\s+)?(?:price\s+)?(?:target|pt)\b', re.I), 0.75),
    (re.compile(r'(?:price\s+)?(?:target|pt)\s+(?:cut|reduced|lowered|trimmed|slashed)\b', re.I), 0.75),

    # Action language — selling / reducing
    (re.compile(r'trim(?:ming)?\s+(?:(?:your|our|the|my)\s+)?(?:position|exposure|stake|holdings?)\b', re.I), 0.75),
    (re.compile(r'(?:reduce|reduc(?:ing)?|cut(?:ting)?)\s+(?:(?:your|our|the|my)\s+)?(?:position|exposure|holdings?)\b', re.I), 0.70),
    (re.compile(r'\btake\s+(?:some\s+)?profits?\b|\bbook(?:ing)?\s+(?:profits?|gains?)\b', re.I), 0.70),
    (re.compile(r'\bexit(?:ing)?\s+(?:(?:our|your|the|my)\s+)?(?:long\s+)?(?:position|stake|trade|holding)\b', re.I), 0.75),
    (re.compile(r'\bclose(?:ing|d)?\s+(?:(?:our|the|my)\s+)?(?:long\s+)?position\b', re.I), 0.75),
    (re.compile(r'sell\s+(?:into\s+)?(?:strength|the\s+rally|any\s+bounce)\b', re.I), 0.70),

    # Valuation / sentiment
    (re.compile(r'valuation\s+(?:looks?\s+|seems?\s+|is\s+)?(?:stretched|rich|expensive|full|elevated|demanding)\b', re.I), 0.65),
    (re.compile(r'(?:stretched|rich|expensive|full|elevated)\s+valuation\b', re.I), 0.65),
    (re.compile(r'\bovervalued\b|\bover.?priced\b|\bpriced\s+for\s+perfection\b', re.I), 0.70),
    (re.compile(r'\blimited\s+(?:upside|room\s+to\s+run)\b', re.I), 0.60),
    (re.compile(r'\bdownside\s+risk[s]?\b|\bdownside\s+(?:scenario|case)\b', re.I), 0.55),
    (re.compile(r'risk.reward\s+(?:(?:is|looks?|seems?|appears?)\s+)?(?:unfavorable|unattractive|poor|negative|skewed\s+lower)\b', re.I), 0.70),
    (re.compile(r'\bheadwind[s]?\b', re.I), 0.45),
    (re.compile(r'\bcautious\s+on\b|\bcautious\s+about\b', re.I), 0.60),
    (re.compile(r'\bcrowded\s+trade\b|\btoo\s+crowded\b', re.I), 0.55),
    (re.compile(r'\bavoid(?:ing)?\b', re.I), 0.55),
    (re.compile(r'multiple\s+compression\b', re.I), 0.65),
]

# ─── Hold / neutral signals ──────────────────────────────────────────────────
_HOLD_SIGNALS: List[Tuple[re.Pattern, float]] = [
    (re.compile(r'\bfairly\s+valued\b|\bappropriately\s+valued\b|\bfair\s+value\b', re.I), 0.70),
    (re.compile(r'\bneutral\b|\bequal.?weight\b|\bmarket\s+perform\b', re.I), 0.65),
    (re.compile(r'wait(?:ing)?\s+for\s+(?:a\s+)?better\s+(?:entry|price|level|point)\b', re.I), 0.70),
    (re.compile(r'(?:stay(?:ing)?|sit(?:ting)?|remain(?:ing)?)\s+(?:on\s+the\s+)?sidelines?\b', re.I), 0.70),
    (re.compile(r'watch(?:ing)?\s+from\s+(?:the\s+)?sidelines?\b', re.I), 0.65),
    (re.compile(r'maintain(?:ing)?\s+(?:(?:our|the|my)\s+)?(?:\w+\s+)?(?:position|hold|neutral)\b', re.I), 0.65),
    (re.compile(r'\bhold(?:ing)?\s+(?:(?:our|my)\s+)?(?:\w+\s+)?(?:position|shares|stake)\b', re.I), 0.60),
]

# ─── Negation detector ───────────────────────────────────────────────────────
# Checked in the 60 characters BEFORE each signal match.
_NEGATION = re.compile(
    r"\b(not?|never|no|without|despite|although|though|contrary|despite)\b",
    re.I,
)


# ─── Sentence / context extraction ──────────────────────────────────────────

def _extract_sentence(text: str, pos: int) -> str:
    """Return the single sentence containing position pos (for display)."""
    sentence_starts = [0]
    for m in re.finditer(r'[.!?\n]', text[:pos]):
        sentence_starts.append(m.end())
    start = sentence_starts[-1] if sentence_starts else 0
    m_end = re.search(r'[.!?\n]', text[pos:])
    end = (pos + m_end.end()) if m_end else len(text)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _extract_scoring_window(text: str, pos: int) -> str:
    """
    Return the paragraph containing position pos.

    Paragraphs are separated by double newlines (\\n\\n), which newsletters
    consistently use to separate discussions of different tickers. This avoids
    mixing bearish signals from one ticker's paragraph into a bullish signal
    for the adjacent ticker.

    If no paragraph boundaries exist (plain text block), falls back to a
    3-sentence window centered on pos.
    """
    # Try paragraph split first (separated by blank lines)
    para_starts = [0] + [m.end() for m in re.finditer(r'\n\n+', text)]
    para_ends   = [m.start() for m in re.finditer(r'\n\n+', text)] + [len(text)]

    for p_start, p_end in zip(para_starts, para_ends):
        if p_start <= pos <= p_end:
            return re.sub(r"\s+", " ", text[p_start:p_end]).strip()

    # Fallback: 3-sentence window (collect sentence boundaries)
    boundaries = [0] + [m.end() for m in re.finditer(r'[.!?\n]', text)] + [len(text)]
    containing = [(s, e) for s, e in zip(boundaries, boundaries[1:]) if s <= pos <= e]
    if not containing:
        return re.sub(r"\s+", " ", text[max(0, pos-300):pos+300]).strip()
    sent_idx   = boundaries.index(containing[0][0])
    win_start  = boundaries[max(0, sent_idx - 2)]
    win_end    = boundaries[min(len(boundaries) - 1, sent_idx + 3)]
    return re.sub(r"\s+", " ", text[win_start:win_end]).strip()


# ─── Direction scoring ───────────────────────────────────────────────────────

def _score_sentence(sentence: str) -> Tuple[str, float]:
    """
    Score a sentence using analyst language patterns.
    Returns (direction, confidence).

    Logic:
    - Each matching bullish/bearish phrase adds its weight to the relevant score.
    - Negation within 60 chars before the phrase flips its contribution.
    - Confidence = 0.50 + score * 0.25, capped at 0.95.
    - If no signals → MENTION with 0.30.
    """
    bullish_score = 0.0
    bearish_score = 0.0
    hold_score = 0.0

    for pattern, weight in _BULLISH_SIGNALS:
        for m in pattern.finditer(sentence):
            prefix = sentence[max(0, m.start() - 60): m.start()]
            if _NEGATION.search(prefix):
                bearish_score += weight * 0.4   # negated bullish → mild bearish
            else:
                bullish_score += weight

    for pattern, weight in _BEARISH_SIGNALS:
        for m in pattern.finditer(sentence):
            prefix = sentence[max(0, m.start() - 60): m.start()]
            if _NEGATION.search(prefix):
                bullish_score += weight * 0.4   # negated bearish → mild bullish
            else:
                bearish_score += weight

    for pattern, weight in _HOLD_SIGNALS:
        if pattern.search(sentence):
            hold_score += weight

    if bullish_score == 0 and bearish_score == 0 and hold_score == 0:
        return "MENTION", 0.30

    if bullish_score >= bearish_score and bullish_score >= hold_score:
        if bullish_score > 0:
            confidence = min(0.95, 0.50 + bullish_score * 0.20)
            return "BUY", confidence

    if bearish_score > bullish_score and bearish_score >= hold_score:
        confidence = min(0.95, 0.50 + bearish_score * 0.20)
        return "SELL", confidence

    if hold_score > 0:
        confidence = min(0.80, 0.50 + hold_score * 0.15)
        return "HOLD", confidence

    # Mixed or tied signals
    return "MENTION", 0.35


# ─── Data model ─────────────────────────────────────────────────────────────

@dataclass
class TickerMention:
    ticker: str
    direction: str      # "BUY", "SELL", "HOLD", "MENTION"
    confidence: float   # 0.0–1.0
    context: str        # The sentence containing the mention
    source: str         # Email sender + subject
    date: str


# ─── Main parser ────────────────────────────────────────────────────────────

def parse_email(email_data: Dict) -> List[TickerMention]:
    """
    Extract all ticker mentions from a single email dict.

    Returns deduplicated list (highest confidence kept per ticker).
    Only returns tickers with direction != MENTION and confidence >= 0.45,
    unless the ticker appears with $SYMBOL notation (high-value signal).
    """
    body    = email_data.get("body", "")
    sender  = email_data.get("sender", "")
    subject = email_data.get("subject", "")
    date    = email_data.get("date", "")
    source  = f"{sender[:40]} | {subject[:50]}"

    found: Dict[str, TickerMention] = {}

    for pattern in _TICKER_PATTERNS:
        is_dollar_pattern = pattern.pattern.startswith(r'\$')

        for match in pattern.finditer(body):
            groups = match.groups() or ()
            ticker_candidates = [g for g in groups if g and re.fullmatch(r"[A-Z]{1,5}", g)]
            if not ticker_candidates:
                continue
            ticker = ticker_candidates[-1].upper()

            if ticker not in KNOWN_TICKERS and not is_dollar_pattern:
                continue

            sentence       = _extract_sentence(body, match.start())
            scoring_window = _extract_scoring_window(body, match.start())
            direction, confidence = _score_sentence(scoring_window)

            if direction == "MENTION" and not is_dollar_pattern:
                continue

            if ticker not in found or found[ticker].confidence < confidence:
                found[ticker] = TickerMention(
                    ticker=ticker,
                    direction=direction,
                    confidence=confidence,
                    context=sentence[:300],
                    source=source,
                    date=date,
                )

    # Scan for company names (e.g. "Nike", "ExxonMobil")
    body_lower = body.lower()
    for company, ticker in COMPANY_TO_TICKER.items():
        idx = body_lower.find(company)
        if idx == -1:
            continue
        scoring_window = _extract_scoring_window(body, idx)
        direction, confidence = _score_sentence(scoring_window)
        if direction == "MENTION":
            continue
        if ticker not in found or found[ticker].confidence < confidence:
            sentence = _extract_sentence(body, idx)
            found[ticker] = TickerMention(
                ticker=ticker,
                direction=direction,
                confidence=confidence,
                context=sentence[:300],
                source=source,
                date=date,
            )

    return list(found.values())
