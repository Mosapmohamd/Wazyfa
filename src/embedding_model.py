"""Small embedding model for semantic job filtering.

This module provides lightweight semantic matching to recover jobs
that were incorrectly filtered out by regex-based filters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Default configuration for the small embedding model
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_THRESHOLD = 0.50
DEFAULT_BATCH_SIZE = 32


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding model."""

    model_name: str = DEFAULT_MODEL_NAME
    threshold: float = DEFAULT_THRESHOLD
    batch_size: int = DEFAULT_BATCH_SIZE
    normalize_embeddings: bool = True


class SmallEmbeddingModel:
    """Lightweight sentence embedding model for job title semantic matching.

    This class wraps a small pre-trained sentence transformer model to provide
    semantic similarity scoring between job titles and target roles/levels.

    The model is loaded lazily on first use to avoid unnecessary memory usage
    when the feature is not needed.
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        """Initialize the embedding model with optional configuration.

        Args:
            config: Optional configuration for the model. Uses defaults if not provided.
        """
        self.config = config or EmbeddingConfig()
        self._model: Any | None = None
        self._load_failed = False

    @property
    def is_available(self) -> bool:
        """Check if the model is available for use."""
        return not self._load_failed

    def _ensure_loaded(self) -> bool:
        """Ensure the model is loaded. Returns False if loading failed."""
        if self._load_failed:
            return False

        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.config.model_name)
                logger.info(
                    "Loaded embedding model: %s",
                    self.config.model_name,
                )
            except Exception as e:
                self._load_failed = True
                logger.warning(
                    "Failed to load embedding model (%s); semantic filtering disabled: %s",
                    self.config.model_name,
                    e,
                )
                return False

        return True

    def encode(self, texts: list[str]) -> list[list[float]] | None:
        """Encode a list of texts into embeddings.

        Args:
            texts: List of text strings to encode.

        Returns:
            List of embedding vectors, or None if encoding failed.
        """
        if not self._ensure_loaded():
            return None

        try:
            embeddings = self._model.encode(
                texts,
                normalize_embeddings=self.config.normalize_embeddings,
                convert_to_numpy=True,
                batch_size=self.config.batch_size,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.warning("Encoding failed: %s", e)
            return None

    def compute_similarity(
        self,
        query: str,
        candidates: list[str],
    ) -> list[float] | None:
        """Compute cosine similarity between a query and candidate texts.

        Args:
            query: The query text (e.g., target role or level).
            candidates: List of candidate texts to compare against.

        Returns:
            List of similarity scores (0-1), or None if computation failed.
        """
        if not candidates:
            return []

        embeddings = self.encode([query, *candidates])
        if embeddings is None:
            return None

        import numpy as np

        query_embedding = np.array(embeddings[0])
        candidate_embeddings = np.array(embeddings[1:])

        # Compute cosine similarity (embeddings are already normalized)
        similarities = candidate_embeddings @ query_embedding
        return similarities.tolist()

    def find_matches(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        text_key: str = "Title",
        threshold: float | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """Find candidates that match the query above a similarity threshold.

        Args:
            query: The query text to match against.
            candidates: List of candidate dictionaries.
            text_key: Key to extract text from candidate dictionaries.
            threshold: Similarity threshold (uses default if not provided).

        Returns:
            List of tuples containing (candidate, similarity_score) for matches.
        """
        threshold = threshold if threshold is not None else self.config.threshold

        if not candidates:
            return []

        texts = [str(candidate.get(text_key, "")).strip() for candidate in candidates]
        # Filter out empty texts
        valid_indices = [i for i, text in enumerate(texts) if text]

        if not valid_indices:
            return []

        valid_texts = [texts[i] for i in valid_indices]
        similarities = self.compute_similarity(query, valid_texts)

        if similarities is None:
            return []

        matches: list[tuple[dict[str, Any], float]] = []
        for idx, score in zip(valid_indices, similarities):
            if score >= threshold:
                candidate = candidates[idx]
                matches.append((candidate, round(float(score), 4)))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def rescue_jobs(
        self,
        target_text: str,
        rejected_jobs: list[dict[str, Any]],
        match_type: str = "role",
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Rescue jobs that were rejected by regex filters but semantically match.

        Args:
            target_text: The target role or level text to match against.
            rejected_jobs: List of jobs that were rejected by regex filters.
            match_type: Type of match ('role' or 'level') for labeling.
            threshold: Similarity threshold (uses default if not provided).

        Returns:
            List of rescued jobs with match metadata added.
        """
        if not target_text.strip() or target_text.lower() in {"any", "all"}:
            return []

        matches = self.find_matches(
            query=target_text,
            candidates=rejected_jobs,
            text_key="Title",
            threshold=threshold,
        )

        rescued: list[dict[str, Any]] = []
        for job, score in matches:
            # Add metadata about the semantic match
            job["seniority_match"] = f"semantic_{match_type}"
            job[f"{match_type}_match_score"] = score
            rescued.append(job)

        if rescued:
            logger.info(
                "Rescued %d jobs via semantic %s matching (threshold: %.2f)",
                len(rescued),
                match_type,
                threshold or self.config.threshold,
            )

        return rescued


# Global instance for backward compatibility with existing code
_embedding_model: SmallEmbeddingModel | None = None


def get_embedding_model(config: EmbeddingConfig | None = None) -> SmallEmbeddingModel:
    """Get or create the global embedding model instance.

    Args:
        config: Optional configuration for the model.

    Returns:
        The global embedding model instance.
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SmallEmbeddingModel(config)
    return _embedding_model


def reset_embedding_model() -> None:
    """Reset the global embedding model instance.

    Useful for testing or reconfiguration.
    """
    global _embedding_model
    _embedding_model = None
