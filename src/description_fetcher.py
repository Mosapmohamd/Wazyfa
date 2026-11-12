"""Fetch and cache full job descriptions with checkpoint recovery."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import multiprocessing as mp
import random
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup
from scrapling import StealthyFetcher

from src.cache_manager import system_cache

logger = logging.getLogger(__name__)

_STRIP_TAGS = ("script", "style", "header", "footer", "nav", "aside", "form")


def _extract_description(response: Any, platform: str, max_chars: int) -> str:
    """Extract readable job-description text from a scraper response."""

    raw_html = getattr(response, "body", None) or getattr(response, "html_content", None) or ""
    if not raw_html:
        return ""

    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    if platform == "Wuzzuf":
        target_headers = ("Job Description", "Job Requirements", "Responsibilities:")
        sections = []
        for section in soup.find_all(("section", "div")):
            header = section.find(("h2", "h3"))
            if header and any(
                marker.lower() in header.get_text(" ", strip=True).lower()
                for marker in target_headers
            ):
                sections.append(section.get_text(separator=" ", strip=True))
        text = " \n".join(sections) if sections else soup.get_text(" ", strip=True)
    elif platform == "LinkedIn":
        nodes = soup.select("div.description__text, div.show-more-less-html__markup")
        target = nodes[0] if nodes else soup
        for br in target.find_all("br"):
            br.replace_with(" ")
        for item in target.find_all("li"):
            item.insert_before(" - ")
        text = target.get_text(" ", strip=True)
    else:
        text = soup.get_text(" ", strip=True)

    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _save_checkpoint(
    jobs: list[dict[str, Any]], 
    path: str | Path, 
    is_complete: bool, 
    input_fingerprint: str, 
    total_jobs: int
) -> None:
    """Save Excel checkpoint and JSON manifest."""
    
    checkpoint = Path(path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(jobs).to_excel(checkpoint, index=False)
    
    manifest_path = checkpoint.with_suffix(".json")
    manifest = {
        "input_fingerprint": input_fingerprint,
        "total_jobs": total_jobs,
        "processed_jobs": len(jobs),
        "is_complete": is_complete
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        
    logger.info("Saved checkpoint %s with %d rows (complete=%s)", checkpoint, len(jobs), is_complete)


def _isolated_fetch_worker(
    jobs_subset: list[dict[str, Any]],
    headless: bool,
    network_idle: bool,
    min_delay: float,
    max_delay: float,
    max_chars: int,
    checkpoint_path: str | Path | None,
    checkpoint_interval: int,
    return_dict: Any,
    input_fingerprint: str,
) -> None:
    """Enrich a subset of jobs inside a spawned process."""

    enriched: list[dict[str, Any]] = []
    total_jobs = len(jobs_subset)

    def process_single_job(job: dict[str, Any]) -> dict[str, Any]:
        link = job.get("Link", "")
        platform = job.get("Platform", "")
        if not link or link == "N/A":
            job["Job_Description"] = "No Link"
            return job

        cached_description = system_cache.get_job_description(link)
        if cached_description:
            job["Job_Description"] = cached_description
            return job

        try:
            response = StealthyFetcher.fetch(
                link,
                headless=headless,
                network_idle=network_idle,
            )
            description = _extract_description(response, platform, max_chars)
            job["Job_Description"] = description or "Description not found"
            if description:
                system_cache.set_job_description(link, description)
        except Exception:
            logger.exception("Failed to fetch description for %s", link)
            job["Job_Description"] = "Error fetching description"
            return job

        time.sleep(random.uniform(min_delay, max_delay))
        return job

    worker_count = random.choice((1, 2, 3))
    logger.info("Using %d description workers", worker_count)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        for index, job in enumerate(executor.map(process_single_job, jobs_subset), start=1):
            enriched.append(job)
            if checkpoint_path and checkpoint_interval > 0 and index % checkpoint_interval == 0:
                _save_checkpoint(enriched, checkpoint_path, is_complete=False, input_fingerprint=input_fingerprint, total_jobs=total_jobs)

    if checkpoint_path:
        _save_checkpoint(enriched, checkpoint_path, is_complete=True, input_fingerprint=input_fingerprint, total_jobs=total_jobs)
    return_dict["enriched"] = enriched


def fetch_descriptions(
    jobs: list[dict[str, Any]],
    *,
    headless: bool = True,
    network_idle: bool = True,
    min_delay: float = 4.5,
    max_delay: float = 8.7,
    checkpoint_path: str | Path | None = None,
    checkpoint_interval: int = 5,
    max_chars: int = 4000,
) -> list[dict[str, Any]]:
    """Fetch job descriptions in a spawned process with checkpoint recovery."""

    if not jobs:
        return []

    # BUG-004 Fix: Generate canonical fingerprint of input links
    input_links = sorted([str(job.get("Link", "")) for job in jobs])
    input_fingerprint = hashlib.sha256(json.dumps(input_links).encode("utf-8")).hexdigest()

    # Pre-run validation: delete stale checkpoints from different job sets
    if checkpoint_path:
        cp_file = Path(checkpoint_path)
        manifest_file = cp_file.with_suffix(".json")
        if cp_file.exists() and manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                if manifest.get("input_fingerprint") != input_fingerprint:
                    logger.info("Found stale checkpoint from a different job set. Deleting %s", checkpoint_path)
                    cp_file.unlink(missing_ok=True)
                    manifest_file.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to read checkpoint manifest. Deleting to ensure clean state.")
                cp_file.unlink(missing_ok=True)
                manifest_file.unlink(missing_ok=True)
        elif cp_file.exists() or manifest_file.exists():
            # Orphaned files, clean up
            cp_file.unlink(missing_ok=True)
            manifest_file.unlink(missing_ok=True)

    context = mp.get_context("spawn")
    with context.Manager() as manager:
        return_dict = manager.dict()
        process = context.Process(
            target=_isolated_fetch_worker,
            args=(
                jobs,
                headless,
                network_idle,
                min_delay,
                max_delay,
                max_chars,
                checkpoint_path,
                checkpoint_interval,
                return_dict,
                input_fingerprint,
            ),
        )
        process.start()
        process.join()
        enriched = return_dict.get("enriched")

    if enriched is not None:
        logger.info("Fetched descriptions for %d jobs", len(enriched))
        return list(enriched)

    logger.warning("Description worker exited without returning data (exitcode: %s)", process.exitcode)
    
    # Post-crash recovery validation
    if checkpoint_path and Path(checkpoint_path).exists():
        manifest_file = Path(checkpoint_path).with_suffix(".json")
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                
                # Only recover if fingerprint matches AND it was explicitly marked complete
                if manifest.get("input_fingerprint") == input_fingerprint and manifest.get("is_complete") is True:
                    recovered_df = pd.read_excel(checkpoint_path)
                    recovered = recovered_df.to_dict(orient="records")
                    if len(recovered) == manifest.get("total_jobs"):
                        logger.info("Recovered %d jobs from valid completed checkpoint %s", len(recovered), checkpoint_path)
                        return recovered
                    else:
                        logger.warning("Checkpoint manifest said complete, but row count mismatched. Discarding.")
                else:
                    logger.warning("Checkpoint is stale or incomplete. Discarding partial data to prevent incorrect results.")
            except Exception:
                logger.exception("Failed to recover checkpoint %s", checkpoint_path)
            
            # Clean up partial or invalid checkpoint files
            Path(checkpoint_path).unlink(missing_ok=True)
            manifest_file.unlink(missing_ok=True)
            
    return []


def export_enriched(jobs: list[dict[str, Any]], output_path: str | Path) -> Path:
    """Save enriched job listings to an Excel file."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(jobs).to_excel(path, index=False)
    logger.info("Saved enriched jobs to %s", path)
    return path