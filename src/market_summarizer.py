"""Market requirement summarization with cache-backed model loading."""

from __future__ import annotations

import gc
import hashlib
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src.cache_manager import system_cache

logger = logging.getLogger(__name__)

_summarizer: Any | None = None
_summarizer_model: str | None = None


def _get_device() -> str:
    try:
        import torch
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_summarizer(model_name: str, device: str) -> Any:
    global _summarizer, _summarizer_model
    if _summarizer is not None and _summarizer_model == model_name:
        return _summarizer

    from transformers import pipeline
    logger.info("Loading summarization model %s on %s", model_name, device)
    _summarizer = pipeline("summarization", model=model_name, device=device)
    _summarizer_model = model_name
    return _summarizer


def _chunk_text(text: str, max_chars: int = 8000) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if current and length + len(word) + 1 > max_chars:
            chunks.append(" ".join(current))
            current = []
            length = 0
        current.append(word)
        length += len(word) + 1
    if current:
        chunks.append(" ".join(current))
    return chunks


def _summarize_with_nvidia(text: str, max_tokens: int, min_tokens: int) -> str | None:
    from config import settings
    
    # BUG-007 Fix: Require explicit opt-in before sending data externally
    if not settings.allow_external_ai:
        return None
        
    if not settings.nvidia_api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    try:
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=settings.nvidia_api_key,
            timeout=45.0, # Add a timeout
        )
        prompt_text = text[:15000]
        completion = client.chat.completions.create(
            model=settings.nvidia_fallback_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert technical recruiter and market analyst. Summarize the key technical, analytical, and soft skill requirements from the provided job descriptions.",
                },
                {"role": "user", "content": f"Summarize the following job descriptions into a cohesive market requirements overview:\n\n{prompt_text}"},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        summary = completion.choices[0].message.content
        if summary:
            return summary
    except Exception:
        logger.exception("NVIDIA API summarization failed; falling back to local model")
    return None


def summarize_market(
    enriched_jobs: list[dict[str, Any]],
    *,
    primary_model: str = "allenai/led-base-16384",
    fallback_model: str = "facebook/bart-large-cnn",
    max_length: int = 400,
    min_length: int = 100,
    max_desc_chars: int = 4000,
) -> str:
    """Summarize valid job descriptions and cache the resulting summary."""

    valid_descriptions = [
        str(job.get("Job_Description", ""))[:max_desc_chars]
        for job in enriched_jobs
        if job.get("Job_Description") not in {None, "", "No Link", "Error fetching description", "Description not found"}
    ]
    if not valid_descriptions:
        return "No valid job descriptions were available."

    merged = "\n".join(valid_descriptions)
    summary_key = hashlib.sha256(merged.encode("utf-8")).hexdigest()
    cached_summary = system_cache.get_market_summary(summary_key, "auto", "auto")
    if cached_summary:
        return cached_summary

    # 1. Attempt NVIDIA API summarization first
    summary = _summarize_with_nvidia(merged, max_length, min_length)

    # 2. Fallback to local models if NVIDIA failed/wasn't configured and HF isn't skipped
    from config import settings
    skip_hf = getattr(settings, "skip_hf_summarizer", False)

    if summary is None and not skip_hf:
        device = _get_device()
        
        # Try Primary
        try:
            summarizer = _load_summarizer(primary_model, device)
            result = summarizer(
                merged,
                max_new_tokens=max_length,
                min_new_tokens=min_length,
                do_sample=False,
                truncation=True,
            )
            summary = result[0]["summary_text"]
        except Exception:
            logger.exception("Primary summarization model failed; using chunked fallback")
        
        # Unload primary BEFORE loading fallback to prevent peak memory pressure
        if summary is None:
            unload_summarizer()
            try:
                summarizer = _load_summarizer(fallback_model, device)
                partial_summaries = []

                for index, chunk in enumerate(
                    _chunk_text(merged, max_chars=3000), start=1
                ):
                    try:
                        result = summarizer(
                            chunk,
                            max_new_tokens=150,
                            min_new_tokens=30,
                            do_sample=False,
                            truncation=True,
                        )
                        partial_summaries.append(result[0]["summary_text"])
                    except Exception:
                        logger.exception(
                            "Fallback summarization failed for chunk %d", index
                        )

                if partial_summaries:
                    summary = " ".join(partial_summaries)
                else:
                    summary = merged[:2000]
            except Exception:
                logger.exception(
                    "Fallback summarization failed; returning source text"
                )
                summary = merged[:2000]
            finally:
                unload_summarizer()

    elif summary is None and skip_hf:
        logger.info("Hugging Face summarization skipped via config. Returning truncated source.")
        summary = merged[:2000]

    system_cache.set_market_summary(summary_key, "auto", "auto", summary)
    return summary

def summarize_from_excel(excel_path: str | Path, **kwargs: Any) -> str:
    try:
        frame = pd.read_excel(excel_path)
    except Exception:
        return ""
    return summarize_market(frame.to_dict(orient="records"), **kwargs)

def unload_summarizer() -> None:
    global _summarizer, _summarizer_model
    if _summarizer is None:
        return

    _summarizer = None
    _summarizer_model = None
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except ImportError:
        pass
    except Exception:
        logger.exception("Unable to clear GPU memory after unloading summarizer")