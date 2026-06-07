"""LiveKit agent — passive listener with fact-checking interjections."""

import logging

from livekit.agents import (
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import silero
from openai import AsyncOpenAI

from app.config import settings
from app.services import moss_service

logger = logging.getLogger(__name__)

# Minimax via OpenAI-compatible client
_openai = AsyncOpenAI(
    api_key=settings.minimax_api_key,
    base_url=settings.minimax_base_url,
)

SYSTEM_PROMPT = (
    "You are Antidote AI, a passive fact-checking agent in an M&A call.\n\n"
    "Your job:\n"
    "1. Listen to the conversation silently.\n"
    "2. When a participant makes a quantitative or factual claim (revenue, margins,\n"
    "   headcount, contracts, etc.), silently query your knowledge base to verify it.\n"
    "3. If the claim contradicts your data, interject briefly: state the discrepancy\n"
    "   and the correct figure, e.g. 'The net revenue for Acme Corp was $6B not $12B.\n"
    "   Should I provide more detail?'\n"
    "4. If asked for more information, continue conversationally — 3–4 sentences per turn.\n"
    "5. When dismissed ('Ok thanks, you are no longer needed'), return to passive listening.\n"
    "6. If you appear to no longer be addressed, ask: 'Am I still needed?'\n\n"
    "Keep interjections concise. Always cite sources."
)


class AntidoteAgent(llm.FunctionContext):
    """Agent with a Moss-backed fact-retrieval tool."""

    @llm.ai_callable(description="Search the due diligence knowledge base for a claim.")
    async def search_knowledge_base(self, query: str) -> str:
        results = await moss_service.search(query, top_k=5)
        if not results:
            return "No relevant information found in the knowledge base."
        parts = [f"Source ({r['document']} p.{r['page']}): {r['text']}" for r in results]
        return "\n\n".join(parts)


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await moss_service.ensure_index()

    agent = AntidoteAgent()
    session = AgentSession(
        llm=llm.OpenAILLM.with_client(
            client=_openai,
            model=settings.minimax_model,
        ),
        stt=llm.StreamAdapterSTT(
            stt=silero.VAD.load(),
        ),
        fnc_ctx=agent,
        system_prompt=SYSTEM_PROMPT,
    )

    await session.start(ctx.room)


def run_worker() -> None:
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
            ws_url=settings.livekit_url,
        )
    )
