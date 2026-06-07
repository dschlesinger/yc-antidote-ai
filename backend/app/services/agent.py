"""LiveKit agent — passive listener with Moss-backed fact-checking interjections."""

import asyncio
import json
import logging

from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, cli, function_tool
from livekit.agents.llm.chat_context import ChatMessage
from livekit.plugins import cartesia, deepgram, openai, silero

from app.config import settings
from app.services import moss_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Antidote AI, a passive fact-checking agent in an M&A call.\n\n"
    "Your job:\n"
    "1. Listen silently. Do not speak unless you detect a discrepancy or are addressed.\n"
    "2. When a participant makes a quantitative or factual claim (revenue, margins,\n"
    "   headcount, contracts, dates, etc.), call search_knowledge_base to verify it.\n"
    "3. If the claim contradicts your data, interject briefly with the discrepancy\n"
    "   and the correct figure. Example: 'The net revenue for Acme Corp was $6B,\n"
    "   not $12B. Should I provide more detail?'\n"
    "4. If asked for more information, continue conversationally — 3-4 sentences per turn.\n"
    "5. When dismissed ('Ok thanks, you are no longer needed'), return to passive listening.\n"
    "6. If you appear to no longer be addressed, ask: 'Am I still needed?'\n\n"
    "Keep interjections concise. Always cite sources."
)


class AntidoteAgent(Agent):
    """Passive fact-checking agent for M&A conversations."""

    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        # Sources from the most recent Moss search — consumed when the next
        # assistant message is published to the frontend.
        self.pending_sources: list[dict] = []

    @function_tool
    async def search_knowledge_base(self, query: str) -> str:
        """Search the due diligence knowledge base for a claim.

        Args:
            query: The claim or topic to verify, in natural language.

        Returns:
            Source-attributed evidence from the knowledge base, or a no-results message.
        """
        try:
            results = await moss_service.search(query, top_k=5)
        except Exception as e:
            logger.exception("Moss query failed")
            self.pending_sources = []
            return f"Knowledge base unavailable: {e}"

        self.pending_sources = [
            {"text": r["text"], "document": r["document"], "page": r.get("page")}
            for r in results
        ]
        if not results:
            return "No relevant information found in the knowledge base."
        return "\n\n".join(
            f"[{r['document']} p.{r['page']}] {r['text']}" for r in results
        )


async def entrypoint(ctx: JobContext) -> None:
    """LiveKit agent entrypoint: join the room, wire STT/LLM/TTS, start listening."""
    await ctx.connect()
    await moss_service.ensure_index()

    agent = AntidoteAgent()
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", api_key=settings.deepgram_api_key),
        llm=openai.LLM(
            model=settings.minimax_model,
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
        ),
        tts=cartesia.TTS(api_key=settings.cartesia_api_key),
        vad=silero.VAD.load(),
    )

    @session.on("conversation_item_added")
    def _on_item_added(event) -> None:
        item = event.item
        if not isinstance(item, ChatMessage) or item.role != "assistant":
            return
        text = "".join(c for c in item.content if isinstance(c, str)).strip()
        if not text:
            return
        sources = agent.pending_sources
        agent.pending_sources = []
        payload = json.dumps({"type": "interjection", "text": text, "sources": sources}).encode()
        asyncio.create_task(ctx.room.local_participant.publish_data(payload, reliable=True))

    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )
