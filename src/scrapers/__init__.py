"""Job-board scrapers package (one module per source board)."""

from src.scrapers.bayt import scrape_bayt
from src.scrapers.indeed import scrape_indeed
from src.scrapers.jobzella import scrape_jobzella
from src.scrapers.linkedin import scrape_linkedin
from src.scrapers.unified import extract_search_profile_from_cv, unified_job_scraper
from src.scrapers.wuzzuf import scrape_wuzzuf

__all__ = [
    "extract_search_profile_from_cv",
    "scrape_bayt",
    "scrape_indeed",
    "scrape_jobzella",
    "scrape_linkedin",
    "scrape_wuzzuf",
    "unified_job_scraper",
]
