"""LiveKit agent — passive listener with Moss-backed fact-checking interjections."""

import asyncio
import json
import logging

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
    inference,
)
from livekit.plugins import openai, silero

from app.config import settings
from app.services import moss_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Antidote AI, a silent fact-checking observer on an M&A call.\n\n"
    "DEFAULT BEHAVIOR: stay completely silent. Do not greet, do not narrate, do not\n"
    "ask if you are still needed, do not summarize. Listen only.\n\n"
    "YOU MAY SPEAK ONLY in these two situations:\n"
    "  (a) You detected a contradiction between a participant's factual claim and\n"
    "      the due-diligence knowledge base. Always run search_knowledge_base first\n"
    "      to confirm the discrepancy. Only interject if the evidence clearly\n"
    "      contradicts what was said.\n"
    "  (b) A participant directly addresses you with a question that requires a\n"
    "      verbal answer.\n\n"
    "HOW TO COMMUNICATE: the ONLY way to speak or send text to the user is to call\n"
    "the send_message tool. Never produce a free-form spoken response — every\n"
    "utterance must go through send_message.\n\n"
    "Style:\n"
    " - Lead with the correction or the answer.\n"
    " - 1-3 sentences. Cite the source document.\n"
    " - Do not add closing pleasantries or follow-up questions.\n"
)


class AntidoteAgent(Agent):
    """Silent fact-checking agent; communicates only via send_message."""

    def __init__(self, room: rtc.Room) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self._room = room
        # Sources from the most recent Moss search — attached to the next
        # send_message call so the UI can show the citation.
        self.pending_sources: list[dict] = []

    @function_tool
    async def search_knowledge_base(self, query: str) -> str:
        """Search the due diligence knowledge base to verify a claim.

        Call this before interjecting on any factual claim. The result tells
        you what the documents actually say so you can decide whether the
        participant's statement is wrong.

        Args:
            query: The claim or topic to verify, in natural language.

        Returns:
            Source-attributed evidence from the knowledge base, or a
            no-results message. The sources are remembered and attached
            automatically to the next send_message call.
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

    @function_tool
    async def send_message(self, context: RunContext, text: str) -> str:
        """Speak to the user and post the text into the on-screen chat.

        This is the ONLY way you may communicate. Use it when you have
        confirmed a discrepancy or when answering a direct question.

        Args:
            text: 1-3 sentences. Be specific and cite the source document
                  if you have one from a recent search_knowledge_base call.

        Returns:
            A confirmation that the message was delivered. Do not produce
            any further text after calling this tool.
        """
        sources = self.pending_sources
        self.pending_sources = []
        payload = json.dumps({
            "type": "interjection",
            "text": text,
            "sources": sources,
        }).encode()
        await self._room.local_participant.publish_data(payload, reliable=True)
        # Speak it aloud as well so the message reaches participants who
        # aren't looking at the screen.
        await context.session.say(text, allow_interruptions=True)
        return "Message delivered."


async def entrypoint(ctx: JobContext) -> None:
    """LiveKit agent entrypoint: join the room, wire STT/LLM/TTS, start listening."""
    await ctx.connect()
    await moss_service.ensure_index()

    # STT and TTS are routed through LiveKit Inference (billed via the LiveKit
    # API key) so we don't need separate Deepgram/Cartesia accounts. The LLM
    # stays direct because Minimax isn't a LiveKit Inference provider.
    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3"),
        llm=openai.LLM(
            model=settings.minimax_model,
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
        ),
        tts=inference.TTS(model="cartesia/sonic-3"),
        vad=silero.VAD.load(),
    )

    @session.on("user_input_transcribed")
    def _on_user_transcript(event) -> None:
        if not getattr(event, "is_final", False):
            return
        text = (event.transcript or "").strip()
        if not text:
            return
        payload = json.dumps({"type": "user_transcript", "text": text}).encode()
        asyncio.create_task(ctx.room.local_participant.publish_data(payload, reliable=True))

    await session.start(agent=AntidoteAgent(ctx.room), room=ctx.room)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            ws_url=settings.livekit_url,
            api_key=settings.livekit_api_key,
            api_secret=settings.livekit_api_secret,
        )
    )
