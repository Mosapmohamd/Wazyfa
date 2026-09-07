"""Local Hugging Face text-generation pipeline loading and caching."""

from __future__ import annotations

import logging
from typing import Any

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    torch = None
    _TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)

_llm_pipeline: Any | None = None
_llm_model_name: str | None = None
_llm_use_4bit: bool | None = None


def _get_device() -> str:
    """Return the available inference device."""

    if not _TORCH_AVAILABLE:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_llm(model_name: str, use_4bit: bool) -> Any:
    """Load and cache a local Hugging Face text-generation pipeline."""

    global _llm_pipeline, _llm_model_name, _llm_use_4bit
    if not _TORCH_AVAILABLE:
        raise RuntimeError("PyTorch is not installed; local LLM inference is unavailable")
    if _llm_pipeline is not None and (
        _llm_model_name != model_name or _llm_use_4bit != use_4bit
    ):
        _llm_pipeline = None
    if _llm_pipeline is not None:
        return _llm_pipeline

    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, pipeline

    device = _get_device()
    logger.info("Loading local LLM %s on %s", model_name, device)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    base_kwargs: dict[str, Any] = {
        "torch_dtype": torch.float16 if device == "cuda" else torch.float32,
    }
    if device == "cuda":
        base_kwargs["device_map"] = "auto"

    model = None
    if use_4bit and device == "cuda":
        try:
            quant_kwargs = dict(base_kwargs)
            quant_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
            )
            model = AutoModelForCausalLM.from_pretrained(model_name, **quant_kwargs)
        except Exception:
            logger.exception("4-bit model loading failed; retrying without quantization")

    if model is None:
        model = AutoModelForCausalLM.from_pretrained(model_name, **base_kwargs)

    _llm_pipeline = pipeline("text-generation", model=model, tokenizer=tokenizer)
    _llm_model_name = model_name
    _llm_use_4bit = use_4bit
    return _llm_pipeline
