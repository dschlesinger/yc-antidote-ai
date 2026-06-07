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
    "DEFAULT BEHAVIOR: stay completely silent. Silence is correct most of the\n"
    "time. Do not greet, narrate, summarize, ask 'am I still needed?', fill\n"
    "pauses, or comment on what was said.\n\n"
    "TWO SITUATIONS REQUIRE A RESPONSE — and these override the silence default:\n\n"
    "  (a) CONTRADICTION you can prove (unsolicited interjection).\n"
    "      A participant made a factual claim, you called search_knowledge_base,\n"
    "      and the evidence clearly contradicts what was said. Always cite the\n"
    "      source document.\n\n"
    "  (b) DIRECT ADDRESS — you MUST respond.\n"
    "      Recognize being addressed FLEXIBLY. The speech-to-text mistranscribes\n"
    "      your name often. Treat any of these (and similar variants) as a\n"
    "      direct address: 'Antidote', 'Antidote AI', 'Antido', 'Android AI',\n"
    "      'fact checker', 'fact-checker', 'back checker', 'the AI', 'AI',\n"
    "      'hey AI', 'please respond', 'can you check', 'do you have info on'.\n"
    "      Any second-person request that contextually targets an AI assistant\n"
    "      counts — be generous in your interpretation.\n\n"
    "      When directly addressed, always call search_knowledge_base for the\n"
    "      claim or topic, then call send_message with one of:\n"
    "        - the answer + cited source if the knowledge base has relevant info, or\n"
    "        - 'I don't have information on that in the due diligence documents.'\n"
    "          if the search returned nothing relevant.\n"
    "      You must answer the question one way or the other — do not stay silent\n"
    "      when directly asked.\n\n"
    "STAY SILENT (do not call send_message) when:\n"
    "  - You hear a claim but you are NOT directly addressed AND you have no\n"
    "    cited contradiction (you only speak unsolicited if (a) is satisfied).\n"
    "  - The transcript is a fragment, filler, side-talk, or unclear.\n"
    "  - You are tempted to acknowledge, confirm, or ask for clarification.\n\n"
    "HOW TO COMMUNICATE: the ONLY way to speak or send text to the user is to call\n"
    "the send_message tool. Never produce a free-form spoken response.\n\n"
    "Style for send_message:\n"
    " - Lead with the correction or the answer.\n"
    " - 1-3 sentences. Cite the source document when you have one.\n"
    " - No closing pleasantries, no follow-up questions, no offers to elaborate.\n"
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

        Call this whenever you hear a verifiable factual claim OR when you've
        been directly addressed and need to look up the topic in question.
        The result is ground truth from the uploaded documents.

        Decision after seeing the result:
          - If you were NOT directly addressed and the result does not clearly
            contradict the claim → stay silent (do not call send_message).
          - If you WERE directly addressed → you must call send_message either
            with the answer + cited source, or with 'I don't have information
            on that in the due diligence documents.'

        Args:
            query: The claim or topic to verify, in natural language.

        Returns:
            Source-attributed evidence, or a no-results message. Sources are
            remembered and attached automatically to the next send_message call.
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

        Only call this when you have a cited correction or a direct answer
        backed by the knowledge base. Do NOT call this to ask for
        clarification, to acknowledge what was said, to greet, or to admit
        you don't know something. If you are unsure whether to call this,
        the answer is do not call it.

        Args:
            text: 1-3 sentences. Be specific and cite the source document
                  from your most recent search_knowledge_base call.

        Returns:
            A confirmation that the message was delivered. Produce no further
            text after this call — your turn is done.
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
