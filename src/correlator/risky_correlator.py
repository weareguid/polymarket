"""
Risky Correlator — Second-order, non-obvious stock correlations.

Unlike the main StockCorrelator (direct keyword → ETF), this module
identifies instruments that are NOT the obvious play but could be
meaningfully affected through second-order effects:
  - Competitors of winners / losers
  - Supply chain dependencies
  - Currency / repatriation effects
  - Sector rotation consequences
  - Regulatory spillover

These signals are tagged "experimental" and shown separately in the dashboard.
The goal is to surface alpha that a first-order keyword search would miss.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

from .knowledge_base import Instrument
from ..scraper.trending_detector import TrendingSignal


@dataclass
class RiskySignal:
    ticker: str
    name: str
    rationale: str          # Why this non-obvious instrument is affected
    mechanism: str          # How: "competitor", "supply_chain", "currency", "regulatory"
    direction: str          # "positive" or "negative"
    confidence: float       # 0–1, generally lower than primary signals
    source_question: str
    source_volume: float


# ── Second-order mapping ──────────────────────────────────────────────────────
# Format: (regex_pattern, [RiskySignal templates], explanation_of_logic)
#
# Each entry fires when a market question matches the pattern and produces
# non-obvious instrument signals with justification text.

_SECOND_ORDER_RULES = [

    # SpaceX / NASA contracts → Boeing loses, defense subs win
    (
        r"\b(spacex|nasa contract|rocket launch|moon mission|artemis)\b",
        [
            ("BA",   "Boeing",           "negative", "competitor",
             "SpaceX wins → Boeing loses government launch contracts"),
            ("AJRD", "Aerojet Rocketdyne","positive","supply_chain",
             "SpaceX engine/component supplier benefits from higher launch volume"),
        ]
    ),

    # Japan rate hike → yen strengthens → repatriation hits exporters
    (
        r"\b(japan.{0,20}(rate|hike|boj|bank of japan)|yen strength)\b",
        [
            ("TM",   "Toyota",   "negative", "currency",
             "Yen appreciation erodes Toyota's USD earnings on repatriation"),
            ("SONY", "Sony",     "negative", "currency",
             "Sony earns majority of revenue outside Japan; yen rise compresses margins"),
            ("DXJ",  "WisdomTree Japan Hedged", "positive", "currency",
             "USD-hedged Japan ETF benefits when yen rises vs dollar"),
        ]
    ),

    # China tech crackdown / regulation
    (
        r"\b(china.{0,30}(tech|crackdown|regulation|antitrust|ban)|alibaba.{0,20}fine)\b",
        [
            ("BIDU", "Baidu",    "negative", "regulatory",
             "Chinese tech crackdowns historically hit Baidu alongside Alibaba"),
            ("KWEB", "KraneShares China Internet", "negative", "regulatory",
             "Broad China internet ETF sells off on regulatory risk"),
            ("MSFT", "Microsoft","positive", "competitor",
             "Chinese tech weakness opens market share for Western cloud providers"),
        ]
    ),

    # OPEC cuts → oil up → airlines hurt
    (
        r"\b(opec.{0,20}cut|oil production cut|crude supply cut)\b",
        [
            ("UAL", "United Airlines", "negative", "supply_chain",
             "Airlines are massive fuel consumers; oil spike directly compresses margins"),
            ("DAL", "Delta Air Lines", "negative", "supply_chain",
             "Jet fuel is ~25% of operating cost for Delta"),
            ("LUV", "Southwest Airlines", "negative", "supply_chain",
             "Southwest historically hedges fuel less aggressively than peers"),
        ]
    ),

    # Fed pause / no rate change → banks squeezed, real estate rebounds
    (
        r"\bno change.{0,30}(fed|interest rate|march meeting|may meeting)\b",
        [
            ("VNQ", "Vanguard Real Estate ETF", "positive", "regulatory",
             "Rate pause reduces refinancing pressure, supports REIT valuations"),
            ("KRE", "SPDR Regional Banking",    "negative", "regulatory",
             "Regional banks earn less on spread when rates stay flat longer"),
        ]
    ),

    # Nvidia / AI chip export ban to China
    (
        r"\b(nvda|nvidia).{0,40}(china|export ban|chip restriction)\b",
        [
            ("AMD",  "AMD",            "positive", "competitor",
             "NVIDIA losing China market share creates opening for AMD in data centers"),
            ("INTC", "Intel",          "positive", "competitor",
             "Intel's China-compliant chips become more attractive under NVIDIA ban"),
            ("TSM",  "TSMC",           "negative", "supply_chain",
             "Lower NVIDIA China orders reduce TSMC's leading-edge wafer volume"),
        ]
    ),

    # Ukraine ceasefire / peace deal
    (
        r"\b(ukraine.{0,30}(ceasefire|peace|deal|negotiation|end.{0,10}war))\b",
        [
            ("WEAT", "Wheat ETF",   "negative", "supply_chain",
             "Peace restores Ukrainian grain exports, pressuring wheat prices"),
            ("UNG",  "US Natural Gas Fund", "negative", "supply_chain",
             "European energy security improves; US LNG export premium narrows"),
            ("ITA",  "Defense ETF", "negative", "competitor",
             "Peace reduces urgency of NATO defense spending, short-term headwind"),
            ("ERUS", "iShares MSCI Russia", "positive", "regulatory",
             "Sanctions likely to ease post-ceasefire, Russia assets re-rate"),
        ]
    ),

    # Trump tariffs on EU
    (
        r"\b(trump.{0,30}tariff.{0,20}(europe|eu|germany|france)|eu.{0,30}tariff)\b",
        [
            ("VGK",  "Vanguard FTSE Europe", "negative", "regulatory",
             "EU tariffs directly hit European exporters; broad Europe ETF sells off"),
            ("BMW",  "BMW AG",              "negative", "regulatory",
             "German auto exports to US face direct tariff cost increase"),
            ("F",    "Ford",                "positive", "competitor",
             "Domestic automakers gain price advantage as EU imports become costlier"),
        ]
    ),

    # Crypto ETF approval / SEC decision
    (
        r"\b(sec.{0,30}(approve|reject|bitcoin etf|crypto etf|spot etf))\b",
        [
            ("HOOD", "Robinhood",     "positive", "regulatory",
             "Crypto ETF approval drives retail trading volume through platforms"),
            ("CME",  "CME Group",     "positive", "regulatory",
             "Broader crypto legitimacy boosts CME's crypto futures volumes"),
            ("GS",   "Goldman Sachs", "positive", "regulatory",
             "Goldman runs crypto trading desks that benefit from institutional ETF flows"),
        ]
    ),

    # AI model release (GPT-5, Gemini Ultra, Claude 4...)
    (
        r"\b(gpt.5|gemini ultra|claude.{0,10}release|new ai model|frontier model)\b",
        [
            ("SMCI", "Super Micro Computer", "positive", "supply_chain",
             "AI model releases drive demand for GPU servers; SMCI is key hardware supplier"),
            ("ARM",  "Arm Holdings",         "positive", "supply_chain",
             "ARM chips underpin inference hardware for edge AI deployment"),
            ("GOOG", "Alphabet",             "negative", "competitor",
             "OpenAI/Anthropic model releases challenge Google Search ad revenue"),
        ]
    ),
]

# Pre-compile patterns
_COMPILED_RULES = [
    (re.compile(pattern, re.IGNORECASE), instruments, )
    for pattern, instruments in _SECOND_ORDER_RULES
]


class RiskyCorrelator:
    """
    Finds non-obvious (second-order) stock signals from Polymarket trending markets.
    """

    def correlate(self, signals: List[TrendingSignal]) -> List[RiskySignal]:
        results: dict[str, RiskySignal] = {}   # ticker → best signal

        for signal in signals:
            question = signal.market.question
            volume   = signal.market.volume_24h

            for compiled_re, instruments in _COMPILED_RULES:
                if not compiled_re.search(question):
                    continue

                for ticker, name, direction, mechanism, rationale in instruments:
                    # Confidence: base 0.45 (lower than primary), boosted by volume
                    confidence = min(0.70, 0.45 + signal.score * 0.25)

                    if ticker not in results or results[ticker].confidence < confidence:
                        results[ticker] = RiskySignal(
                            ticker=ticker,
                            name=name,
                            rationale=rationale,
                            mechanism=mechanism,
                            direction=direction,
                            confidence=round(confidence, 3),
                            source_question=question[:120],
                            source_volume=volume,
                        )

        return sorted(results.values(), key=lambda s: -s.confidence)
