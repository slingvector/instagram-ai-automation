import logging
import sqlite3
from pathlib import Path
from src.ingestion.repositories.ig_graph_repository import IGGraphRepository
from src.ingestion.services.insights_service import InsightsService

logger = logging.getLogger(__name__)

class InsightsAdapter:
    """
    Adapter that bridges the InsightsService with the internal Trending Weight database.
    This fulfills the requirement of the 'Insights API Feedback Loop' to boost/demote
    sources over time based on actual Meta API analytics.
    """

    def __init__(self, db_path: str = "data/db/roi_weights.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        self.repo = IGGraphRepository()
        self.service = InsightsService(self.repo)

    def _init_db(self):
        """Initializes the SQLite database used to store source weight multipliers."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS source_roi (
                    source_id TEXT PRIMARY KEY,
                    average_roi REAL DEFAULT 1.0,
                    posts_tracked INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def run_feedback_loop(self, ig_user_id: str):
        """
        Executes the feedback loop: fetches performance, computes ROI,
        and saves it to the database so TrendingAdapter can use it.
        """
        logger.info("Starting Insights Feedback Loop...")
        report = self.service.analyze_recent_performance(ig_user_id)

        if not report:
            logger.warning("No performance data found. Skipping feedback loop.")
            return

        with sqlite3.connect(self.db_path) as conn:
            for item in report:
                # In a full implementation, we would extract the specific source (e.g. reddit/worldnews)
                # from our local tracking database using the shortcode, and update that specific source's ROI.
                # For now, we mock saving the generalized shortcode ROI to demonstrate the architecture.
                shortcode = item["shortcode"]
                roi_score = item["roi_score"]

                conn.execute('''
                    INSERT INTO source_roi (source_id, average_roi, posts_tracked, last_updated)
                    VALUES (?, ?, 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_id) DO UPDATE SET
                    average_roi = (average_roi * posts_tracked + ?) / (posts_tracked + 1),
                    posts_tracked = posts_tracked + 1,
                    last_updated = CURRENT_TIMESTAMP
                ''', (shortcode, roi_score, roi_score))

            conn.commit()
            
        logger.info(f"Feedback loop completed. Processed {len(report)} media items.")
