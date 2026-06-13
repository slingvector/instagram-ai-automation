import logging
from typing import Dict, Any, List
from src.ingestion.repositories.ig_graph_repository import IGGraphRepository

logger = logging.getLogger(__name__)

class InsightsService:
    """
    Service layer for processing Instagram Insights.
    Follows SRP by orchestrating the calculation of ROI metrics from the raw Repository data.
    """

    def __init__(self, ig_repository: IGGraphRepository):
        self.ig_repo = ig_repository

    def analyze_recent_performance(self, ig_user_id: str) -> List[Dict[str, Any]]:
        """
        Fetches recent media, aggregates their insights, and calculates an ROI score.
        Returns a structured list of performance data.
        """
        logger.info(f"Analyzing recent performance for IG User: {ig_user_id}")
        try:
            media_data = self.ig_repo.get_user_media(ig_user_id)
            media_list = media_data.get("data", [])
        except Exception as e:
            logger.error(f"Failed to fetch media list: {e}")
            return []

        performance_report = []

        for item in media_list:
            if item.get("media_type") != "VIDEO":
                continue # We only care about Reels ROI for the feedback loop

            media_id = item["id"]
            try:
                insights = self.ig_repo.get_media_insights(media_id)
                metrics = self._parse_metrics(insights.get("data", []))
                
                # Formula: (Likes + Comments*2 + Shares*3 + Saves*3) / Reach
                roi_score = self._calculate_roi_score(metrics)

                performance_report.append({
                    "media_id": media_id,
                    "shortcode": item.get("shortcode"),
                    "timestamp": item.get("timestamp"),
                    "metrics": metrics,
                    "roi_score": roi_score
                })
            except Exception as e:
                logger.warning(f"Could not fetch insights for media {media_id}: {e}")
                continue

        return performance_report

    def _parse_metrics(self, data: List[Dict[str, Any]]) -> Dict[str, int]:
        """Parses the raw Graph API metrics array into a usable dictionary."""
        metrics = {"reach": 0, "plays": 0, "likes": 0, "comments": 0, "shares": 0, "saved": 0}
        for metric_obj in data:
            name = metric_obj.get("name")
            if name in metrics:
                # The 'values' array usually contains one object with a 'value' key
                values = metric_obj.get("values", [])
                if values:
                    metrics[name] = values[0].get("value", 0)
        return metrics

    def _calculate_roi_score(self, metrics: Dict[str, int]) -> float:
        """Calculates a normalized ROI score based on engagement weighting."""
        reach = metrics.get("reach", 0)
        if reach == 0:
            return 0.0
            
        likes = metrics.get("likes", 0)
        comments = metrics.get("comments", 0)
        shares = metrics.get("shares", 0)
        saved = metrics.get("saved", 0)

        weighted_engagement = likes + (comments * 2.0) + (shares * 3.0) + (saved * 3.0)
        # Multiply by 100 to get a more readable percentage-like score
        return (weighted_engagement / reach) * 100.0
