"""MoA Ensemble - Mixture of Agents

Based on Hermes mixture_of_agents_tool.py.
Three-layer architecture:
1. Reference models generate diverse initial responses in parallel
2. Aggregator synthesizes into a high-quality final answer
3. Optional multi-layer iteration for refinement

Reference: "Mixture-of-Agents Enhances Large Language Model Capabilities"
by Junlin Wang et al. (arXiv:2406.04692v1)

Usage:
    result = await moa_generate(
        prompt="Solve this complex problem...",
        reference_models=["anthropic/claude-3-5", "openai/gpt-4o", ...],
        aggregator_model="anthropic/claude-3-5",
    )
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_REFERENCE_MODELS = [
    "anthropic/claude-opus-4.6",
    "google/gemini-3-pro-preview",
    "openai/gpt-5.4-pro",
    "deepseek/deepseek-v3.2",
]
DEFAULT_AGGREGATOR_MODEL = "anthropic/claude-opus-4.6"
REFERENCE_TEMPERATURE = 0.6
AGGREGATOR_TEMPERATURE = 0.4
MIN_SUCCESSFUL_REFERENCES = 1

AGGREGATOR_SYSTEM_PROMPT = (
    "You have been provided with a set of responses from various open-source models "
    "to the latest user query. Your task is to synthesize these responses into a "
    "single, high-quality response. It is crucial to critically evaluate the information "
    "provided in these responses, recognizing that some of it may be biased or incorrect. "
    "Your response should not simply replicate the given answers but should offer a "
    "refined, accurate, and comprehensive reply to the instruction. "
    "Ensure your response is well-structured, coherent, and adheres to the highest "
    "standards of accuracy and reliability.\n\n"
    "Responses from models:"
)


def _construct_aggregator_prompt(system_prompt: str, responses: list[str]) -> str:
    response_text = "\n".join([f"{i+1}. {r}" for i, r in enumerate(responses)])
    return f"{system_prompt}\n\n{response_text}"


async def _call_model(
    model: str,
    messages: list[dict],
    temperature: float = 0.6,
    max_tokens: int = 4096,
) -> Optional[str]:
    """Call a model via OpenRouter. Override this for custom providers."""
    try:
        import os
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        )
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        return content if content else None
    except Exception as e:
        logger.warning("Model call failed for %s: %s", model, e)
        return None


async def moa_generate(
    prompt: str,
    reference_models: Optional[list[str]] = None,
    aggregator_model: Optional[str] = None,
    reference_temperature: float = REFERENCE_TEMPERATURE,
    aggregator_temperature: float = AGGREGATOR_TEMPERATURE,
    min_successful: int = MIN_SUCCESSFUL_REFERENCES,
    concurrent: int = 4,
) -> str:
    """
    Generate a response using the Mixture-of-Agents approach.

    Args:
        prompt: User prompt
        reference_models: Models to generate initial responses
        aggregator_model: Model to synthesize final answer
        reference_temperature: Temperature for reference models
        aggregator_temperature: Temperature for aggregator
        min_successful: Minimum successful reference responses needed
        concurrent: Number of concurrent reference model calls

    Returns:
        Aggregated response string
    """
    refs = reference_models or DEFAULT_REFERENCE_MODELS
    agg_model = aggregator_model or DEFAULT_AGGREGATOR_MODEL

    ref_messages = [{"role": "user", "content": prompt}]

    # Phase 1: Parallel reference model responses
    tasks = [
        _call_model(model, ref_messages, temperature=reference_temperature)
        for model in refs
    ]

    responses: list[tuple[int, str]] = []
    for i, coro in enumerate(asyncio.as_completed(tasks)):
        try:
            result = await coro
            if result:
                responses.append((i, result))
        except Exception as e:
            logger.warning("Reference model %s failed: %s", refs[i], e)

    if len(responses) < min_successful:
        logger.warning(
            "Only %d/%d reference models succeeded. Using best available.",
            len(responses), len(refs)
        )

    if not responses:
        return "MoA generation failed: no reference models responded."

    # Sort by original order to preserve diversity
    responses.sort(key=lambda x: x[0])
    ref_texts = [r for _, r in responses]

    # Phase 2: Aggregator synthesizes
    aggregator_prompt = _construct_aggregator_prompt(
        AGREGATOR_SYSTEM_PROMPT, ref_texts
    )
    agg_messages = [
        {"role": "system", "content": aggregator_prompt},
        {"role": "user", "content": prompt},
    ]

    result = await _call_model(
        agg_model,
        agg_messages,
        temperature=aggregator_temperature,
        max_tokens=8192,
    )

    return result or "Aggregator returned empty response."


def moa_generate_sync(
    prompt: str,
    reference_models: Optional[list[str]] = None,
    aggregator_model: Optional[str] = None,
) -> str:
    """Synchronous wrapper for moa_generate."""
    try:
        return asyncio.run(
            moa_generate(prompt, reference_models, aggregator_model)
        )
    except RuntimeError:
        # Already in async context
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            moa_generate(prompt, reference_models, aggregator_model)
        )


# LLM-free version: prompt-only ensemble (no API calls)
def ensemble_prompts(prompts: list[str], aggregator_instruction: str = "") -> list[str]:
    """
    Ensemble multiple prompt variants without model calls.
    Returns all variants for manual comparison.
    """
    return prompts


if __name__ == "__main__":
    async def test():
        result = await moa_generate(
            "What are the key principles of software architecture?",
            reference_models=[
                "anthropic/claude-opus-4.6",
                "google/gemini-3-pro-preview",
            ],
            min_successful=1,
        )
        print(f"Result length: {len(result)} chars")
        print(result[:500])

    asyncio.run(test())
