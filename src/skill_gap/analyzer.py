"""CV-versus-market skill-gap analysis orchestration."""

from __future__ import annotations

import logging

try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:
    torch = None
    _TORCH_AVAILABLE = False

from src.skill_gap.external import _external_api_analysis, _nvidia_fallback_analysis
from src.skill_gap.local_llm import _load_llm
from src.skill_gap.prompts import _PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


def analyze_skill_gap(
    cv_text: str,
    market_summary: str,
    *,
    model_name: str = "mistralai/Mistral-7B-Instruct-v0.2",
    use_4bit: bool = True,
    max_new_tokens: int = 1024,
) -> str:
    """Analyze a CV against the market summary and return JSON text."""


    prompt = (
        _PROMPT_TEMPLATE
        .replace("{market_summary}", market_summary)
        .replace("{cv_text}", cv_text)
    )

    # Try external API first (configured provider: nvidia/openai/anthropic/google/azure/custom)
    result = _external_api_analysis(cv_text, market_summary)
    if result is not None:
        return result
    

    try:
        pipe = _load_llm(model_name, use_4bit)
        messages = [
            {
                "role": "system",
                "content": "You are a precise technical recruiter. Use only the provided evidence.",
            },
            {"role": "user", "content": prompt},
        ]

        if hasattr(pipe.tokenizer, "apply_chat_template"):
            encoded = pipe.tokenizer.apply_chat_template(
                messages,
                return_tensors="pt",
                add_generation_prompt=True,
                return_dict=True,
            )
            input_ids = encoded["input_ids"].to(pipe.model.device)
            attention_mask = encoded.get("attention_mask")
            if attention_mask is not None:
                attention_mask = attention_mask.to(pipe.model.device)
        else:
            encoded = pipe.tokenizer(prompt, return_tensors="pt")
            input_ids = encoded.input_ids.to(pipe.model.device)
            attention_mask = encoded.attention_mask.to(pipe.model.device)

        with torch.no_grad():
            outputs = pipe.model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.1,
                pad_token_id=pipe.tokenizer.eos_token_id,
            )

        generated_tokens = outputs[0][input_ids.shape[-1] :]
        result = pipe.tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()
        if not result:
            raise ValueError("Local LLM returned an empty response")
        return result
    except Exception:
        logger.exception("Local skill-gap analysis failed; attempting NVIDIA fallback")
        return _nvidia_fallback_analysis(cv_text, market_summary)
