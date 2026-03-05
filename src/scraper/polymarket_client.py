"""
Polymarket API Client.

Connects to Polymarket's Gamma API to fetch market data.
Documentation: https://docs.polymarket.com/
"""
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json

from ..utils import config, logger


@dataclass
class Market:
    """Represents a Polymarket market."""
    id: str
    question: str
    description: str
    outcome_prices: Dict[str, float]  # {"Yes": 0.65, "No": 0.35}
    volume_24h: float
    volume_total: float
    liquidity: float
    end_date: Optional[str]
    category: str
    slug: str
    active: bool
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class PolymarketClient:
    """
    Client for interacting with Polymarket API.

    Uses the Gamma API for market data:
    - GET /markets - List all markets
    - GET /markets/{id} - Get specific market
    - GET /events - List events
    """

    def __init__(self, base_url: str = None):
        """
        Initialize the client.

        Args:
            base_url: API base URL (defaults to config)
        """
        self.base_url = base_url or config.polymarket_base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "PolymarketInvestmentAdviser/1.0"
        })
        logger.info(f"PolymarketClient initialized with base URL: {self.base_url}")

    def _request(self, endpoint: str, params: Dict = None) -> Dict:
        """
        Make a request to the API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response as dict
        """
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise

    def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False
    ) -> List[Dict]:
        """
        Fetch markets from Polymarket.

        Args:
            limit: Max number of markets to return
            offset: Pagination offset
            active: Include active markets
            closed: Include closed markets
            order: Sort field (volume24hr, liquidity, startDate, endDate)
            ascending: Sort direction

        Returns:
            List of market dictionaries
        """
        params = {
            "limit": min(limit, config.max_markets_per_fetch),
            "offset": offset,
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "order": order,
            "ascending": str(ascending).lower()
        }

        logger.info(f"Fetching markets with params: {params}")
        data = self._request("/markets", params)

        # The API returns a list directly or wrapped in a data field
        markets = data if isinstance(data, list) else data.get("data", [])
        logger.info(f"Fetched {len(markets)} markets")

        return markets

    def get_market(self, market_id: str) -> Dict:
        """
        Get a specific market by ID.

        Args:
            market_id: Market condition ID

        Returns:
            Market data dictionary
        """
        logger.info(f"Fetching market: {market_id}")
        return self._request(f"/markets/{market_id}")

    def get_events(self, limit: int = 100, active: bool = True) -> List[Dict]:
        """
        Fetch events (groups of related markets).

        Args:
            limit: Max number of events
            active: Include only active events

        Returns:
            List of event dictionaries
        """
        params = {
            "limit": limit,
            "active": str(active).lower()
        }

        logger.info(f"Fetching events with params: {params}")
        data = self._request("/events", params)

        events = data if isinstance(data, list) else data.get("data", [])
        logger.info(f"Fetched {len(events)} events")

        return events

    def get_trending_markets(
        self,
        min_volume_24h: float = None,
        min_liquidity: float = 1000,
        limit: int = 50
    ) -> List[Market]:
        """
        Get trending markets based on volume and activity.

        Args:
            min_volume_24h: Minimum 24h volume (defaults to config threshold)
            min_liquidity: Minimum liquidity
            limit: Max markets to return

        Returns:
            List of Market objects
        """
        min_volume = min_volume_24h or config.trending_volume_threshold

        # Fetch markets sorted by 24h volume
        raw_markets = self.get_markets(
            limit=limit * 2,  # Fetch extra to filter
            order="volume24hr",
            ascending=False
        )

        trending = []
        for m in raw_markets:
            volume_24h = float(m.get("volume24hr", 0) or 0)
            liquidity = float(m.get("liquidity", 0) or 0)

            if volume_24h >= min_volume and liquidity >= min_liquidity:
                market = self._parse_market(m)
                if market:
                    trending.append(market)

            if len(trending) >= limit:
                break

        logger.info(f"Found {len(trending)} trending markets")
        return trending

    def _parse_market(self, data: Dict) -> Optional[Market]:
        """
        Parse raw API response into Market object.

        Args:
            data: Raw market data from API

        Returns:
            Market object or None if parsing fails
        """
        try:
            # Parse outcome prices
            outcome_prices = {}
            outcomes = data.get("outcomes", [])
            prices = data.get("outcomePrices", [])

            # API returns these as JSON strings, parse them
            if isinstance(outcomes, str):
                import json as _json
                try:
                    outcomes = _json.loads(outcomes)
                except Exception:
                    outcomes = []
            if isinstance(prices, str):
                import json as _json
                try:
                    prices = _json.loads(prices)
                except Exception:
                    prices = []

            if outcomes and prices:
                # Prices might be strings or floats
                for outcome, price in zip(outcomes, prices):
                    try:
                        outcome_prices[outcome] = float(price) if price else 0.0
                    except (ValueError, TypeError):
                        outcome_prices[outcome] = 0.0

            return Market(
                id=data.get("conditionId", data.get("id", "")),
                question=data.get("question", ""),
                description=data.get("description", "")[:500],  # Truncate
                outcome_prices=outcome_prices,
                volume_24h=float(data.get("volume24hr", 0) or 0),
                volume_total=float(data.get("volume", 0) or 0),
                liquidity=float(data.get("liquidity", 0) or 0),
                end_date=data.get("endDate"),
                category=data.get("category", "unknown"),
                slug=data.get("slug", ""),
                active=data.get("active", False),
                created_at=data.get("createdAt", ""),
                updated_at=data.get("updatedAt", "")
            )
        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None

    def save_snapshot(self, markets: List[Market], filepath: str = None) -> str:
        """
        Save markets snapshot to CSV.

        Args:
            markets: List of Market objects
            filepath: Optional custom filepath

        Returns:
            Path to saved file
        """
        import csv
        from datetime import datetime

        if not filepath:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = config.raw_data_dir / f"markets_{date_str}.csv"

        fieldnames = [
            "id", "question", "category", "yes_price", "no_price",
            "volume_24h", "volume_total", "liquidity", "end_date",
            "active", "slug", "snapshot_time"
        ]

        snapshot_time = datetime.now().isoformat()

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for market in markets:
                row = {
                    "id": market.id,
                    "question": market.question[:200],  # Truncate for CSV
                    "category": market.category,
                    "yes_price": market.outcome_prices.get("Yes", 0),
                    "no_price": market.outcome_prices.get("No", 0),
                    "volume_24h": market.volume_24h,
                    "volume_total": market.volume_total,
                    "liquidity": market.liquidity,
                    "end_date": market.end_date,
                    "active": market.active,
                    "slug": market.slug,
                    "snapshot_time": snapshot_time
                }
                writer.writerow(row)

        logger.info(f"Saved {len(markets)} markets to {filepath}")
        return str(filepath)


# Convenience function for quick use
def fetch_daily_snapshot() -> str:
    """
    Fetch and save daily market snapshot.

    Returns:
        Path to saved CSV file
    """
    client = PolymarketClient()
    markets = client.get_trending_markets(limit=100)
    return client.save_snapshot(markets)


if __name__ == "__main__":
    # Quick test
    filepath = fetch_daily_snapshot()
    print(f"Snapshot saved to: {filepath}")
