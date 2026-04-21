"""
Knowledge base for mapping events to financial instruments.

Contains curated mappings:
- Countries -> Major ETFs and stocks
- Sectors -> Sector ETFs
- Keywords -> Related instruments
- Companies -> Tickers
"""
from typing import Dict, List, Set
from dataclasses import dataclass


@dataclass
class Instrument:
    """A tradeable financial instrument."""
    ticker: str
    name: str
    type: str  # "stock", "etf", "index", "crypto"
    exchange: str
    correlation_direction: str  # "positive", "negative", "neutral"


class KnowledgeBase:
    """
    Knowledge base for event-to-instrument mapping.

    This is a curated database of correlations between prediction market
    events and financial instruments. Should be expanded over time.
    """

    def __init__(self):
        """Initialize knowledge base with default mappings."""
        self._country_etfs = self._build_country_etfs()
        self._sector_etfs = self._build_sector_etfs()
        self._keyword_instruments = self._build_keyword_instruments()
        self._geopolitical_instruments = self._build_geopolitical_instruments()

    def _build_country_etfs(self) -> Dict[str, List[Instrument]]:
        """Build country to ETF mappings."""
        return {
            # Note: "usa" and "united states" are intentionally omitted as country
            # matchers because "US" appears in almost every Polymarket question
            # (e.g. "Will the US confirm aliens exist?"). Context-specific matching
            # is handled via the keyword_instruments (fed, tariff, recession, etc.).

            "china": [
                Instrument("FXI", "iShares China Large-Cap", "etf", "NYSE", "positive"),
                Instrument("MCHI", "iShares MSCI China", "etf", "NASDAQ", "positive"),
                Instrument("KWEB", "KraneShares China Internet", "etf", "NYSE", "positive"),
                Instrument("BABA", "Alibaba", "stock", "NYSE", "positive"),
                Instrument("JD", "JD.com", "stock", "NASDAQ", "positive"),
            ],
            "russia": [
                Instrument("RSX", "VanEck Russia ETF", "etf", "NYSE", "positive"),
                Instrument("ERUS", "iShares MSCI Russia", "etf", "NYSE", "positive"),
            ],
            "ukraine": [
                Instrument("RSX", "VanEck Russia ETF", "etf", "NYSE", "negative"),
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
                Instrument("UNG", "US Natural Gas Fund", "etf", "NYSE", "positive"),
            ],
            "taiwan": [
                Instrument("EWT", "iShares MSCI Taiwan", "etf", "NYSE", "positive"),
                Instrument("TSM", "Taiwan Semiconductor", "stock", "NYSE", "positive"),
            ],
            "korea": [
                Instrument("EWY", "iShares MSCI South Korea", "etf", "NYSE", "positive"),
                Instrument("005930.KS", "Samsung Electronics", "stock", "KRX", "positive"),
            ],
            "south korea": [
                Instrument("EWY", "iShares MSCI South Korea", "etf", "NYSE", "positive"),
            ],
            "north korea": [
                Instrument("EWY", "iShares MSCI South Korea", "etf", "NYSE", "negative"),
                Instrument("LMT", "Lockheed Martin", "stock", "NYSE", "positive"),
                Instrument("RTX", "RTX Corporation", "stock", "NYSE", "positive"),
            ],
            "japan": [
                Instrument("EWJ", "iShares MSCI Japan", "etf", "NYSE", "positive"),
                Instrument("DXJ", "WisdomTree Japan Hedged", "etf", "NYSE", "positive"),
            ],
            "germany": [
                Instrument("EWG", "iShares MSCI Germany", "etf", "NYSE", "positive"),
                Instrument("DAX", "DAX Index", "index", "XETRA", "positive"),
            ],
            "uk": [
                Instrument("EWU", "iShares MSCI UK", "etf", "NYSE", "positive"),
            ],
            "brazil": [
                Instrument("EWZ", "iShares MSCI Brazil", "etf", "NYSE", "positive"),
            ],
            "india": [
                Instrument("INDA", "iShares MSCI India", "etf", "NYSE", "positive"),
                Instrument("INDY", "iShares India 50", "etf", "NASDAQ", "positive"),
            ],
            "mexico": [
                Instrument("EWW", "iShares MSCI Mexico", "etf", "NYSE", "positive"),
            ],
            "israel": [
                Instrument("EIS", "iShares MSCI Israel", "etf", "NYSE", "positive"),
                Instrument("LMT", "Lockheed Martin", "stock", "NYSE", "positive"),
            ],
            "iran": [
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
                Instrument("USO", "US Oil Fund", "etf", "NYSE", "positive"),
                Instrument("LMT", "Lockheed Martin", "stock", "NYSE", "positive"),
            ],
            "saudi arabia": [
                Instrument("KSA", "iShares MSCI Saudi Arabia", "etf", "NYSE", "positive"),
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
            ],
            "europe": [
                Instrument("VGK", "Vanguard FTSE Europe", "etf", "NYSE", "positive"),
                Instrument("EZU", "iShares MSCI Eurozone", "etf", "NYSE", "positive"),
                Instrument("MDIJX", "MFS Intl Diversification", "etf", "NASDAQ", "positive"),
            ],
        }

    def _build_sector_etfs(self) -> Dict[str, List[Instrument]]:
        """Build sector to ETF mappings."""
        return {
            "technology": [
                Instrument("XLK", "Technology Select SPDR", "etf", "NYSE", "positive"),
                Instrument("VGT", "Vanguard IT ETF", "etf", "NYSE", "positive"),
                Instrument("QQQ", "Nasdaq 100", "etf", "NASDAQ", "positive"),
            ],
            "defense": [
                Instrument("ITA", "iShares US Aerospace & Defense", "etf", "NYSE", "positive"),
                Instrument("PPA", "Invesco Aerospace & Defense", "etf", "NYSE", "positive"),
                Instrument("LMT", "Lockheed Martin", "stock", "NYSE", "positive"),
                Instrument("RTX", "RTX Corporation", "stock", "NYSE", "positive"),
                Instrument("NOC", "Northrop Grumman", "stock", "NYSE", "positive"),
                Instrument("GD", "General Dynamics", "stock", "NYSE", "positive"),
                Instrument("BA", "Boeing", "stock", "NYSE", "positive"),
            ],
            "energy": [
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
                Instrument("VDE", "Vanguard Energy ETF", "etf", "NYSE", "positive"),
                Instrument("USO", "US Oil Fund", "etf", "NYSE", "positive"),
                Instrument("UNG", "US Natural Gas Fund", "etf", "NYSE", "positive"),
            ],
            "oil": [
                Instrument("USO", "US Oil Fund", "etf", "NYSE", "positive"),
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
                Instrument("XOM", "Exxon Mobil", "stock", "NYSE", "positive"),
                Instrument("CVX", "Chevron", "stock", "NYSE", "positive"),
            ],
            "healthcare": [
                Instrument("XLV", "Health Care Select SPDR", "etf", "NYSE", "positive"),
                Instrument("VHT", "Vanguard Health Care ETF", "etf", "NYSE", "positive"),
            ],
            "financials": [
                Instrument("XLF", "Financial Select SPDR", "etf", "NYSE", "positive"),
                Instrument("VFH", "Vanguard Financials ETF", "etf", "NYSE", "positive"),
            ],
            "banks": [
                Instrument("KBE", "SPDR S&P Bank ETF", "etf", "NYSE", "positive"),
                Instrument("KRE", "SPDR S&P Regional Bank", "etf", "NYSE", "positive"),
            ],
            "real estate": [
                Instrument("VNQ", "Vanguard Real Estate ETF", "etf", "NYSE", "positive"),
                Instrument("IYR", "iShares US Real Estate", "etf", "NYSE", "positive"),
            ],
            "gold": [
                Instrument("GLD", "SPDR Gold Shares", "etf", "NYSE", "positive"),
                Instrument("GDX", "VanEck Gold Miners", "etf", "NYSE", "positive"),
                Instrument("IAU", "iShares Gold Trust", "etf", "NYSE", "positive"),
            ],
            "crypto": [
                Instrument("BTC-USD", "Bitcoin", "crypto", "CRYPTO", "positive"),
                Instrument("ETH-USD", "Ethereum", "crypto", "CRYPTO", "positive"),
                Instrument("COIN", "Coinbase", "stock", "NASDAQ", "positive"),
                Instrument("MSTR", "MicroStrategy", "stock", "NASDAQ", "positive"),
            ],
            "ev": [
                Instrument("TSLA", "Tesla", "stock", "NASDAQ", "positive"),
                Instrument("RIVN", "Rivian", "stock", "NASDAQ", "positive"),
                Instrument("LCID", "Lucid Motors", "stock", "NASDAQ", "positive"),
                Instrument("LIT", "Global X Lithium", "etf", "NYSE", "positive"),
            ],
            "ai": [
                Instrument("NVDA", "NVIDIA", "stock", "NASDAQ", "positive"),
                Instrument("MSFT", "Microsoft", "stock", "NASDAQ", "positive"),
                Instrument("GOOGL", "Alphabet", "stock", "NASDAQ", "positive"),
                Instrument("META", "Meta", "stock", "NASDAQ", "positive"),
                Instrument("AMD", "AMD", "stock", "NASDAQ", "positive"),
            ],
            "semiconductors": [
                Instrument("SMH", "VanEck Semiconductor", "etf", "NASDAQ", "positive"),
                Instrument("SOXX", "iShares Semiconductor", "etf", "NASDAQ", "positive"),
                Instrument("NVDA", "NVIDIA", "stock", "NASDAQ", "positive"),
                Instrument("TSM", "Taiwan Semiconductor", "stock", "NYSE", "positive"),
            ],
        }

    def _build_keyword_instruments(self) -> Dict[str, List[Instrument]]:
        """Build keyword to instrument mappings."""
        return {
            "trump": [
                Instrument("DJT", "Trump Media", "stock", "NASDAQ", "positive"),
                Instrument("DWAC", "Digital World Acquisition", "stock", "NASDAQ", "positive"),
                Instrument("IWM", "Russell 2000", "etf", "NYSE", "positive"),  # Small caps
            ],
            "fed": [
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "negative"),
                Instrument("SHY", "1-3 Year Treasury", "etf", "NASDAQ", "positive"),
                Instrument("XLF", "Financial Select", "etf", "NYSE", "positive"),
                Instrument("EIGIX", "Eaton Vance Core Bond", "etf", "NASDAQ", "negative"),
                Instrument("IISIX", "Voya Strategic Income", "etf", "NASDAQ", "negative"),
            ],
            "interest rate": [
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "negative"),
                Instrument("IEF", "7-10 Year Treasury", "etf", "NASDAQ", "negative"),
                Instrument("XLF", "Financial Select", "etf", "NYSE", "positive"),
                Instrument("EIGIX", "Eaton Vance Core Bond", "etf", "NASDAQ", "negative"),
                Instrument("IISIX", "Voya Strategic Income", "etf", "NASDAQ", "negative"),
            ],
            "inflation": [
                Instrument("TIP", "iShares TIPS Bond", "etf", "NYSE", "positive"),
                Instrument("GLD", "SPDR Gold", "etf", "NYSE", "positive"),
                Instrument("DBA", "Invesco DB Agriculture", "etf", "NYSE", "positive"),
                Instrument("EIGIX", "Eaton Vance Core Bond", "etf", "NASDAQ", "negative"),
            ],
            "recession": [
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "positive"),
                Instrument("XLU", "Utilities Select", "etf", "NYSE", "positive"),
                Instrument("XLP", "Consumer Staples", "etf", "NYSE", "positive"),
                Instrument("SPY", "S&P 500", "etf", "NYSE", "negative"),
                Instrument("BMCIX", "BlackRock High Equity", "etf", "NASDAQ", "negative"),
                Instrument("GSUTX", "Goldman Sachs US Equity", "etf", "NASDAQ", "negative"),
            ],
            "tariff": [
                Instrument("EWZ", "Brazil ETF", "etf", "NYSE", "negative"),
                Instrument("FXI", "China ETF", "etf", "NYSE", "negative"),
                Instrument("SPY", "S&P 500", "etf", "NYSE", "negative"),
                Instrument("GSUTX", "Goldman Sachs US Equity", "etf", "NASDAQ", "negative"),
                Instrument("MDIJX", "MFS Intl Diversification", "etf", "NASDAQ", "negative"),
            ],
            "war": [
                Instrument("ITA", "Aerospace & Defense", "etf", "NYSE", "positive"),
                Instrument("XLE", "Energy Select", "etf", "NYSE", "positive"),
                Instrument("GLD", "Gold", "etf", "NYSE", "positive"),
            ],
            "missile": [
                Instrument("ITA", "Aerospace & Defense", "etf", "NYSE", "positive"),
                Instrument("LMT", "Lockheed Martin", "stock", "NYSE", "positive"),
                Instrument("RTX", "RTX Corporation", "stock", "NYSE", "positive"),
            ],
            "bitcoin": [
                Instrument("BTC-USD", "Bitcoin", "crypto", "CRYPTO", "positive"),
                Instrument("COIN", "Coinbase", "stock", "NASDAQ", "positive"),
                Instrument("MSTR", "MicroStrategy", "stock", "NASDAQ", "positive"),
                Instrument("GBTC", "Grayscale Bitcoin", "etf", "NYSE", "positive"),
            ],
            "ethereum": [
                Instrument("ETH-USD", "Ethereum", "crypto", "CRYPTO", "positive"),
                Instrument("ETHE", "Grayscale Ethereum", "etf", "NYSE", "positive"),
            ],
            "election": [
                Instrument("SPY", "S&P 500", "etf", "NYSE", "neutral"),
                Instrument("VIX", "Volatility Index", "index", "CBOE", "positive"),
                Instrument("GSUTX", "Goldman Sachs US Equity", "etf", "NASDAQ", "neutral"),
            ],

            # ── Patterns discovered via EDA of 268K historical Polymarket markets ──

            "ceasefire": [
                Instrument("ITA", "iShares Defense ETF", "etf", "NYSE", "negative"),
                Instrument("WEAT", "Wheat ETF", "etf", "NYSE", "negative"),
                Instrument("UNG", "Natural Gas Fund", "etf", "NYSE", "negative"),
                Instrument("GLD", "SPDR Gold", "etf", "NYSE", "negative"),
            ],
            "sanctions": [
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
                Instrument("USO", "US Oil Fund", "etf", "NYSE", "positive"),
                Instrument("GLD", "SPDR Gold", "etf", "NYSE", "positive"),
                Instrument("ERUS", "iShares MSCI Russia", "etf", "NYSE", "negative"),
            ],
            "nuclear": [
                Instrument("URA", "Global X Uranium ETF", "etf", "NYSE", "positive"),
                Instrument("NLR", "VanEck Uranium+Nuclear", "etf", "NYSE", "positive"),
                Instrument("ITA", "iShares Defense ETF", "etf", "NYSE", "positive"),
                Instrument("GLD", "SPDR Gold", "etf", "NYSE", "positive"),
            ],
            "opec": [
                Instrument("USO", "US Oil Fund", "etf", "NYSE", "positive"),
                Instrument("XLE", "Energy Select SPDR", "etf", "NYSE", "positive"),
                Instrument("UAL", "United Airlines", "stock", "NASDAQ", "negative"),
                Instrument("DAL", "Delta Air Lines", "stock", "NYSE", "negative"),
            ],
            "tiktok": [
                Instrument("META", "Meta Platforms", "stock", "NASDAQ", "positive"),
                Instrument("SNAP", "Snap Inc", "stock", "NYSE", "positive"),
                Instrument("GOOGL", "Alphabet", "stock", "NASDAQ", "positive"),
                Instrument("PINS", "Pinterest", "stock", "NYSE", "positive"),
            ],
            "elon musk": [
                Instrument("TSLA", "Tesla", "stock", "NASDAQ", "positive"),
                Instrument("DOGE-USD", "Dogecoin", "crypto", "CRYPTO", "positive"),
            ],
            "ipo": [
                Instrument("IPO", "Renaissance IPO ETF", "etf", "NYSE", "positive"),
                Instrument("XLK", "Technology Select SPDR", "etf", "NYSE", "positive"),
                Instrument("SPY", "S&P 500", "etf", "NYSE", "positive"),
                Instrument("BMCIX", "BlackRock High Equity", "etf", "NASDAQ", "positive"),
            ],
            "debt ceiling": [
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "negative"),
                Instrument("GLD", "SPDR Gold", "etf", "NYSE", "positive"),
                Instrument("SPY", "S&P 500", "etf", "NYSE", "negative"),
                Instrument("BTC-USD", "Bitcoin", "crypto", "CRYPTO", "positive"),
                Instrument("BMCIX", "BlackRock High Equity", "etf", "NASDAQ", "negative"),
            ],
            "shutdown": [
                Instrument("SPY", "S&P 500", "etf", "NYSE", "negative"),
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "positive"),
                Instrument("XLU", "Utilities Select", "etf", "NYSE", "positive"),
            ],
            "nvidia": [
                Instrument("NVDA", "NVIDIA", "stock", "NASDAQ", "positive"),
                Instrument("SMH", "VanEck Semiconductor", "etf", "NASDAQ", "positive"),
            ],
            "apple": [
                Instrument("AAPL", "Apple Inc", "stock", "NASDAQ", "positive"),
                Instrument("QQQ", "Nasdaq 100", "etf", "NASDAQ", "positive"),
            ],
            "microsoft": [
                Instrument("MSFT", "Microsoft", "stock", "NASDAQ", "positive"),
                Instrument("MSFT", "Microsoft", "stock", "NASDAQ", "positive"),
            ],
            "tesla": [
                Instrument("TSLA", "Tesla", "stock", "NASDAQ", "positive"),
                Instrument("LIT", "Global X Lithium", "etf", "NYSE", "positive"),
            ],
            "boeing": [
                Instrument("BA", "Boeing", "stock", "NYSE", "positive"),
                Instrument("ITA", "iShares Defense ETF", "etf", "NYSE", "positive"),
            ],
            "openai": [
                Instrument("MSFT", "Microsoft", "stock", "NASDAQ", "positive"),
                Instrument("NVDA", "NVIDIA", "stock", "NASDAQ", "positive"),
            ],
            "rate cut": [
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "positive"),
                Instrument("VNQ", "Vanguard Real Estate", "etf", "NYSE", "positive"),
                Instrument("XLF", "Financial Select SPDR", "etf", "NYSE", "negative"),
                Instrument("SPY", "S&P 500", "etf", "NYSE", "positive"),
                Instrument("EIGIX", "Eaton Vance Core Bond", "etf", "NASDAQ", "positive"),
                Instrument("IISIX", "Voya Strategic Income", "etf", "NASDAQ", "positive"),
            ],
            "rate hike": [
                Instrument("TLT", "20+ Year Treasury", "etf", "NASDAQ", "negative"),
                Instrument("KRE", "SPDR Regional Banking", "etf", "NYSE", "positive"),
                Instrument("XLF", "Financial Select SPDR", "etf", "NYSE", "positive"),
                Instrument("VNQ", "Vanguard Real Estate", "etf", "NYSE", "negative"),
                Instrument("EIGIX", "Eaton Vance Core Bond", "etf", "NASDAQ", "negative"),
                Instrument("IISIX", "Voya Strategic Income", "etf", "NASDAQ", "negative"),
            ],
        }

    def _build_geopolitical_instruments(self) -> Dict[str, List[Instrument]]:
        """Build geopolitical event mappings."""
        return {
            "russia_ukraine": [
                Instrument("RSX", "Russia ETF", "etf", "NYSE", "negative"),
                Instrument("XLE", "Energy Select", "etf", "NYSE", "positive"),
                Instrument("UNG", "Natural Gas", "etf", "NYSE", "positive"),
                Instrument("WEAT", "Wheat ETF", "etf", "NYSE", "positive"),
                Instrument("ITA", "Defense ETF", "etf", "NYSE", "positive"),
            ],
            "china_taiwan": [
                Instrument("TSM", "Taiwan Semiconductor", "stock", "NYSE", "negative"),
                Instrument("EWT", "Taiwan ETF", "etf", "NYSE", "negative"),
                Instrument("FXI", "China ETF", "etf", "NYSE", "negative"),
                Instrument("SMH", "Semiconductor ETF", "etf", "NASDAQ", "negative"),
                Instrument("ITA", "Defense ETF", "etf", "NYSE", "positive"),
            ],
            "iran_israel": [
                Instrument("USO", "Oil Fund", "etf", "NYSE", "positive"),
                Instrument("XLE", "Energy Select", "etf", "NYSE", "positive"),
                Instrument("ITA", "Defense ETF", "etf", "NYSE", "positive"),
                Instrument("EIS", "Israel ETF", "etf", "NYSE", "negative"),
                Instrument("GLD", "Gold", "etf", "NYSE", "positive"),
            ],
            "north_korea": [
                Instrument("EWY", "South Korea ETF", "etf", "NYSE", "negative"),
                Instrument("EWJ", "Japan ETF", "etf", "NYSE", "negative"),
                Instrument("ITA", "Defense ETF", "etf", "NYSE", "positive"),
                Instrument("LMT", "Lockheed Martin", "stock", "NYSE", "positive"),
            ],
        }

    def get_country_instruments(self, country: str) -> List[Instrument]:
        """
        Get instruments for a country.

        Args:
            country: Country name (case insensitive)

        Returns:
            List of related instruments
        """
        return self._country_etfs.get(country.lower(), [])

    def get_sector_instruments(self, sector: str) -> List[Instrument]:
        """
        Get instruments for a sector.

        Args:
            sector: Sector name (case insensitive)

        Returns:
            List of related instruments
        """
        return self._sector_etfs.get(sector.lower(), [])

    def get_keyword_instruments(self, keyword: str) -> List[Instrument]:
        """
        Get instruments for a keyword.

        Args:
            keyword: Keyword to search (case insensitive)

        Returns:
            List of related instruments
        """
        return self._keyword_instruments.get(keyword.lower(), [])

    def get_geopolitical_instruments(self, event: str) -> List[Instrument]:
        """
        Get instruments for a geopolitical event.

        Args:
            event: Event identifier (e.g., "russia_ukraine")

        Returns:
            List of related instruments
        """
        return self._geopolitical_instruments.get(event.lower(), [])

    def search(self, text: str) -> List[Instrument]:
        """
        Search all mappings for relevant instruments.

        Args:
            text: Text to search (e.g., market question)

        Returns:
            Deduplicated list of relevant instruments
        """
        import re as _re
        text_lower = text.lower()
        found: Dict[str, Instrument] = {}

        def _word_match(keyword: str, text: str) -> bool:
            """Match whole words only to avoid false positives (e.g. 'gold' in 'golden')."""
            pattern = r'\b' + _re.escape(keyword) + r'\b'
            return bool(_re.search(pattern, text))

        # Search countries
        for country, instruments in self._country_etfs.items():
            if _word_match(country, text_lower):
                for inst in instruments:
                    found[inst.ticker] = inst

        # Search sectors
        for sector, instruments in self._sector_etfs.items():
            if _word_match(sector, text_lower):
                for inst in instruments:
                    found[inst.ticker] = inst

        # Search keywords
        for keyword, instruments in self._keyword_instruments.items():
            if _word_match(keyword, text_lower):
                for inst in instruments:
                    found[inst.ticker] = inst

        # Search geopolitical
        for event, instruments in self._geopolitical_instruments.items():
            # Convert underscore to space for matching
            event_words = event.replace("_", " ").split()
            if all(_word_match(word, text_lower) for word in event_words):
                for inst in instruments:
                    found[inst.ticker] = inst

        return list(found.values())

    def get_all_tickers(self) -> Set[str]:
        """Get all known tickers."""
        tickers = set()

        for instruments in self._country_etfs.values():
            tickers.update(i.ticker for i in instruments)

        for instruments in self._sector_etfs.values():
            tickers.update(i.ticker for i in instruments)

        for instruments in self._keyword_instruments.values():
            tickers.update(i.ticker for i in instruments)

        for instruments in self._geopolitical_instruments.values():
            tickers.update(i.ticker for i in instruments)

        return tickers
