"""
Market classifier for categorizing prediction markets.
"""
from typing import List, Dict, Tuple
from dataclasses import dataclass
import re


@dataclass
class ClassifiedMarket:
    """A classified market with categories."""
    market_id: str
    question: str
    primary_category: str
    secondary_categories: List[str]
    entities: List[str]  # Countries, companies, people mentioned
    keywords: List[str]


class MarketClassifier:
    """
    Classifies prediction markets into categories.

    Categories:
    - geopolitical: Wars, conflicts, international relations
    - election: Elections, voting, political appointments
    - crypto: Cryptocurrency prices and events
    - economic: Fed, interest rates, GDP, employment
    - corporate: Earnings, mergers, company events
    - sports: Sports outcomes
    - entertainment: Awards, shows, celebrity events
    - science: Scientific discoveries, space, climate
    - other: Everything else
    """

    def __init__(self):
        """Initialize classifier with keyword patterns."""
        self.category_patterns = {
            "geopolitical": [
                r"\b(war|invasion|attack|military|conflict|sanction|treaty|missile)\b",
                r"\b(nato|un|united nations|eu|european union)\b",
                r"\b(russia|ukraine|china|taiwan|iran|israel|north korea|gaza|hamas|hezbollah)\b",
            ],
            "election": [
                r"\b(election|vote|ballot|poll|primary|caucus)\b",
                r"\b(president|senator|governor|mayor|congress|parliament)\b",
                r"\b(democrat|republican|gop|dnc|rnc)\b",
                r"\b(trump|biden|harris|desantis)\b",
            ],
            "crypto": [
                r"\b(bitcoin|btc|ethereum|eth|crypto|token|blockchain)\b",
                r"\b(binance|coinbase|defi|nft|altcoin|stablecoin)\b",
                r"\b(\$[0-9,]+k?\s*(btc|eth|sol))\b",
            ],
            "economic": [
                r"\b(fed|federal reserve|interest rate|inflation|cpi|ppi)\b",
                r"\b(gdp|unemployment|recession|economic|economy)\b",
                r"\b(tariff|trade war|import|export)\b",
                r"\b(dollar|euro|yen|currency)\b",
            ],
            "corporate": [
                r"\b(earnings|revenue|profit|ipo|merger|acquisition)\b",
                r"\b(ceo|layoff|bankruptcy|stock split)\b",
                r"\b(tesla|apple|google|amazon|microsoft|meta|nvidia)\b",
            ],
            "sports": [
                r"\b(nfl|nba|mlb|nhl|soccer|football|basketball|baseball)\b",
                r"\b(championship|playoffs|super bowl|world cup|olympics)\b",
                r"\b(win|lose|score|game|match|tournament)\b",
            ],
            "entertainment": [
                r"\b(oscar|emmy|grammy|golden globe|award)\b",
                r"\b(movie|film|album|song|concert|tour)\b",
                r"\b(celebrity|actor|actress|singer|artist)\b",
            ],
            "science": [
                r"\b(nasa|spacex|rocket|mars|moon|satellite)\b",
                r"\b(climate|temperature|carbon|emission)\b",
                r"\b(ai|artificial intelligence|gpt|llm|robot)\b",
                r"\b(vaccine|virus|pandemic|disease)\b",
            ],
        }

        self.entity_patterns = {
            "countries": [
                r"\b(united states|usa|america|u\.s\.)\b",
                r"\b(china|russia|ukraine|taiwan|japan|korea|india)\b",
                r"\b(germany|france|uk|britain|italy|spain)\b",
                r"\b(brazil|mexico|canada|australia)\b",
                r"\b(iran|israel|saudi arabia|turkey|egypt)\b",
            ],
            "companies": [
                r"\b(apple|google|microsoft|amazon|meta|tesla|nvidia)\b",
                r"\b(goldman|jpmorgan|morgan stanley|blackrock)\b",
                r"\b(exxon|chevron|shell|bp)\b",
            ],
            "people": [
                r"\b(trump|biden|harris|obama|clinton)\b",
                r"\b(putin|xi jinping|zelensky|netanyahu)\b",
                r"\b(musk|bezos|zuckerberg|cook|nadella)\b",
            ],
        }

    def classify(self, market_id: str, question: str, description: str = "") -> ClassifiedMarket:
        """
        Classify a market.

        Args:
            market_id: Market identifier
            question: Market question
            description: Optional market description

        Returns:
            ClassifiedMarket with categories and entities
        """
        text = f"{question} {description}".lower()

        # Find matching categories
        category_scores: Dict[str, int] = {}
        for category, patterns in self.category_patterns.items():
            score = sum(len(re.findall(p, text, re.IGNORECASE)) for p in patterns)
            if score > 0:
                category_scores[category] = score

        # Sort by score
        sorted_categories = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)

        primary = sorted_categories[0][0] if sorted_categories else "other"
        secondary = [cat for cat, _ in sorted_categories[1:3]]

        # Extract entities
        entities = []
        for entity_type, patterns in self.entity_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                entities.extend(matches)
        entities = list(set(entities))  # Deduplicate

        # Extract key terms
        keywords = self._extract_keywords(text)

        return ClassifiedMarket(
            market_id=market_id,
            question=question,
            primary_category=primary,
            secondary_categories=secondary,
            entities=entities,
            keywords=keywords
        )

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract significant keywords from text."""
        # Simple keyword extraction - words that appear in our patterns
        all_keywords = set()

        for patterns in self.category_patterns.values():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                all_keywords.update(m.lower() if isinstance(m, str) else m for m in matches)

        return list(all_keywords)[:10]  # Limit to 10

    def classify_batch(self, markets: List[Dict]) -> List[ClassifiedMarket]:
        """
        Classify multiple markets.

        Args:
            markets: List of market dictionaries

        Returns:
            List of classified markets
        """
        results = []
        for market in markets:
            market_id = market.get('id') or market.get('conditionId', '')
            question = market.get('question', '')
            description = market.get('description', '')

            classified = self.classify(market_id, question, description)
            results.append(classified)

        return results

    def filter_by_category(
        self,
        markets: List[Dict],
        categories: List[str]
    ) -> List[Dict]:
        """
        Filter markets by category.

        Args:
            markets: Markets to filter
            categories: Categories to include

        Returns:
            Filtered markets
        """
        categories_lower = [c.lower() for c in categories]
        results = []

        for market in markets:
            classified = self.classify(
                market.get('id', ''),
                market.get('question', ''),
                market.get('description', '')
            )

            if classified.primary_category in categories_lower:
                results.append(market)
            elif any(cat in categories_lower for cat in classified.secondary_categories):
                results.append(market)

        return results
