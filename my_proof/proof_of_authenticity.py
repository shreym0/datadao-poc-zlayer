from typing import Any, List, Dict

def calculate_authenticity_score(contributions: List[Dict[str, Any]], valid_domains: List[str]) -> float:
    """Calculate authenticity score by verifying if witness URLs contain any valid domain."""
    valid_count = sum(
        1 for contribution in contributions
        if any(domain in contribution.get('witnesses', '') for domain in valid_domains)
    )

    return valid_count / len(contributions) if contributions else 0