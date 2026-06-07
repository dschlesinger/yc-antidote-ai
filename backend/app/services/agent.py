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
    "You are Antidote AI, a fact-checking observer on an M&A call. Your\n"
    "purpose is to SURFACE DISCREPANCIES between what participants claim and\n"
    "what the due-diligence documents say. When you find one, you must speak.\n\n"
    "GROUND TRUTH: the due-diligence documents (returned by\n"
    "search_knowledge_base) are your only valid source. Never use training\n"
    "data, world knowledge, news, or memory for any factual statement. If the\n"
    "documents don't address the claim, you don't know the answer.\n\n"
    "TRACKING THE CONVERSATION: speech arrives in short fragments because\n"
    "the speaker pauses. Always read the recent turns together to figure out\n"
    "what's being claimed. Resolve pronouns ('their', 'it', 'they') from\n"
    "earlier turns. A complete claim may span 2-3 fragments.\n\n"
    "WHEN TO INTERJECT (call send_message):\n\n"
    "  (a) CLEAR CONTRADICTION. A participant stated a fact about an entity,\n"
    "      you searched, and a top result names the SAME entity with a\n"
    "      conflicting number/date/name/relationship. Bias toward calling\n"
    "      send_message — that is the whole reason you exist.\n"
    "      Examples:\n"
    "        - Claim 'Acme made five million in revenue' + source 'Acme Corp\n"
    "          revenue $6B in 2025' → CONTRADICTION, call send_message.\n"
    "        - Claim 'they raised fifty billion in Series A' + source 'Series\n"
    "          A: $30M raised' → CONTRADICTION.\n"
    "        - Treat magnitude mismatches (millions vs billions, percent vs\n"
    "          absolute) as contradictions worth flagging.\n"
    "      Speech-to-text drops or garbles entity names ('Acne'/'Acme',\n"
    "      'Android AI'/'Antidote AI'). When the rest of the context makes\n"
    "      the intended entity obvious, treat phonetic variants as a match.\n\n"
    "  (b) DIRECT ADDRESS. Anyone aiming a request at the AI/fact-checker —\n"
    "      'Antidote', 'Antidote AI', 'Antido', 'Android AI', 'fact checker',\n"
    "      'back checker', 'AI', 'hey AI', 'please respond', 'can you check',\n"
    "      'do you have info on', or any equivalent — counts. Be generous.\n"
    "      Search the documents, then call send_message with either the\n"
    "      cited answer or the literal sentence: 'I don't have information\n"
    "      on that in the due diligence documents.' Never stay silent on a\n"
    "      direct question.\n\n"
    "WHEN TO STAY SILENT:\n"
    "  - You weren't addressed AND no source contradicts the claim.\n"
    "  - The search returned only tangentially related results (different\n"
    "    company, different metric not comparable to the claim, etc.).\n"
    "  - The transcript is filler, hesitation, or side-talk ('umm', 'okay',\n"
    "    'wait', '...').\n"
    "  - You'd be confirming, acknowledging, or making small talk.\n\n"
    "HOW TO COMMUNICATE: the send_message tool is the ONLY way to speak or\n"
    "write to the user. Never produce a free-form spoken response.\n\n"
    "Style for send_message:\n"
    "  - Lead with the correction or the answer.\n"
    "  - 1-3 sentences. Cite the source document.\n"
    "  - No closing pleasantries, no follow-up questions, no offers to\n"
    "    elaborate.\n"
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
        """Search the due diligence knowledge base.

        Call this whenever a participant makes a verifiable factual claim, or
        when you are directly addressed about a topic. Results are the ground
        truth — the documents are the only source you should rely on.

        After you see the results, decide:
          - Top result names the SAME entity and CONTRADICTS the claim →
            call send_message with the correction + cited source.
          - You were directly addressed but no result is on the asked-about
            entity → call send_message with: 'I don't have information on
            that in the due diligence documents.'
          - You weren't addressed and nothing contradicts the claim → silent.

        Args:
            query: The claim or topic to verify, in natural language. Use the
                   entity name and the disputed fact (e.g. 'Acme Corp 2025
                   revenue', 'Series A round size for Acme').

        Returns:
            Source-attributed evidence, or a no-results message. The sources
            are attached automatically to the next send_message call.
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

        Before calling this, verify ONE of the following is true:
          1. (unsolicited) Your most recent search_knowledge_base call returned
             a source that explicitly names the SAME entity as the claim AND
             directly contradicts it. If the source is about a different
             company or topic — do NOT call this tool.
          2. (direct address) A participant just addressed you. Then text
             must be either the answer + cited source, or the literal sentence
             'I don't have information on that in the due diligence documents.'

        NEVER use general/world knowledge in `text`. Every fact must come from
        a retrieved source. If you do not have a retrieved source supporting
        your statement, do not call this tool.

        Args:
            text: 1-3 sentences. Cite the source document when applicable.

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
        stt=inference.STT(
            model="deepgram/nova-3",
            extra_kwargs={"diarize": True},
        ),
        llm=openai.LLM(
            model=settings.minimax_model,
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
        ),
        tts=inference.TTS(model="cartesia/sonic-3"),
        vad=silero.VAD.load(),
    )

    # Map raw Deepgram speaker_id ("0", "1", ...) to a friendly "Person N"
    # label assigned in order of first appearance, stable for the session.
    speaker_labels: dict[str, str] = {}

    def label_for_speaker(speaker_id: str | None) -> str | None:
        if speaker_id is None:
            return None
        key = str(speaker_id)
        existing = speaker_labels.get(key)
        if existing:
            return existing
        label = f"Person {len(speaker_labels) + 1}"
        speaker_labels[key] = label
        return label

    @session.on("user_input_transcribed")
    def _on_user_transcript(event) -> None:
        if not getattr(event, "is_final", False):
            return
        text = (event.transcript or "").strip()
        if not text:
            return
        speaker = label_for_speaker(getattr(event, "speaker_id", None))
        payload = json.dumps(
            {"type": "user_transcript", "text": text, "speaker": speaker}
        ).encode()
        asyncio.create_task(ctx.room.local_participant.publish_data(payload, reliable=True))

    @ctx.room.on("data_received")
    def _on_client_data(packet: rtc.DataPacket) -> None:
        """Listen for client-driven control messages (e.g. dismissing an interjection)."""
        try:
            msg = json.loads(bytes(packet.data).decode())
        except Exception:
            return
        if msg.get("type") == "stop_speech":
            # User dismissed the popup — silence the current TTS playout.
            asyncio.create_task(session.interrupt())

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
