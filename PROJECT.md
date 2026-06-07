# Antidote AI

We are building Antidote AI, a realtime agent that sits in on merger and aquisition calls and fact checks claims against due dilligence data.

### Example business use cases

* Providing accountability between parties in merger talks
* Providing context when ground truth is in dispute

## Components

* There will be one **node** per session \- either a phone using a web frontend or a zoom bot that captures the conversation
    * The agent will sit passivley in the conversation until either clarity is requested or it detects a lie
    * In the case of either the agent will make an interjection
        * For the either the zoom bot or website it will make a sound to catch peoples attention, the lie detected and information sounds should be different. It will then say a brief interjection of what happened, either lie or information, example, "The net revenue for Acme Corp was 6 billion not 12 billion, should I provide more information", it should then continue conversationally, 3-4 sentences per turn and then when it has been dimissed ei "Ok thanks, you are no longer need" it should go back to passively listening. If it seems like the agent is no longer being addressed ei nothing is being asked of the agent it should ask "Am I still needed?"
        * For all interjections relivant source material should be provided. For the zoom agent it should be sent in chat. For the website it should send the sources as a message (described later)
    * The frontend will be a multipage application with user login using supabase (Frontend should be mobile and desktop friendly) (Frontend should use **Svelte 5** and **Tailwind 4**)
        * There will be landing page describing the mission and what we provide
        * Once a user signs in there will a page to upload docuements and context (any file type supported by unsiloed and moss)
        * Once the user signs in there will be a page to talk to the agent, there should be a start button and once started there should be a mute and stop button, when the agent make an interjection a summary of the interjection and supporting documents / quotes (from moss retrival) should be provided. The layout should be the agent start and mute as a footer and the chat above that.
        * The goal is to provide a non invasive way to fact check
    * The agent will live on the backend (using python and **Fastapi**), the frontend and zoom bot should stream audio to the backend. The backend should use **livekit** to process the audio stream handle the agent response **Minimax** models should be used with the minimax api, use M3.0 (Specific model used should be configurable in env). All documents uploaded should be stored in supabase, use **Unsiloed** to extract information and **Moss** to retrieve information in realtime for the agent. 


## Layout

Frontend in /frontend
Backend in /backend

## Documentation

* LiveKit  
  * [Documentation](https://docs.livekit.io)  
  * [CLI Documentation](https://docs.livekit.io/intro/basics/cli/)  
  * LiveKit open source repo: [https://github.com/livekit/livekit](https://github.com/livekit/livekit)  
  * [Resources for this hackathon](https://www.livekit.info/conversational-ai-hackathon)  
  * A skill should already be setup in this project for coding agents (e.g. Claude Code) to use  
  * Use case (AI-generated summary from docs)  
     LiveKit would be the realtime backbone of Antidote AI.

    Each call (web frontend or Zoom bot) connects to a LiveKit room. Your backend FastAPI service runs a LiveKit AgentSession that subscribes to audio tracks, transcribes speech, and generates responses using your Minimax-based pipeline. The session lifecycle, turn handling, and agent states (listening, thinking, speaking) are managed by AgentSession as described in the [Agent session guide](https://docs.livekit.io/agents/logic/sessions/).

    For the web app, use LiveKit’s WebRTC transport and SDKs to stream mic audio and receive agent speech and text. For phone/Zoom, use SIP or a bot participant to publish audio into the same room. Telephony support is built into Agents as shown in the [Voice AI quickstart](https://docs.livekit.io/agents/start/voice-ai/).

    LiveKit handles:

    Low-latency audio streaming
    Interruptions and passive listening
    Agent interjections as synthesized speech
    Transcriptions and text output for chat/source citations

  * Realtime Python SDK (RTC): [https://docs.livekit.io/reference/python/livekit/rtc/index.html](https://docs.livekit.io/reference/python/livekit/rtc/index.html)  
  * Server API (Python): [https://docs.livekit.io/reference/python/livekit/api/](https://docs.livekit.io/reference/python/livekit/api/)  
  * Agents SDK (Python): [https://docs.livekit.io/reference/python/livekit/agents/](https://docs.livekit.io/reference/python/livekit/agents/)  
  * Realtime Python SDK (RTC): [https://github.com/livekit/python-sdks](https://github.com/livekit/python-sdks)  
  * Server API SDK (Python): [https://github.com/livekit/python-sdks](https://github.com/livekit/python-sdks)  
     (the same repo contains both `livekit-rtc` and `livekit-api` packages)  
  * Agents SDK (Python): [https://github.com/livekit/agents](https://github.com/livekit/agents)  
* Moss  
  * [Documentation](https://docs.moss.dev/docs) and [repo](https://github.com/usemoss/moss)  
    * Overview & API reference: [/docs/reference/python/api](https://docs.moss.dev/docs/reference/python/api)  
    * Sessions: [/docs/reference/python/sessions](https://docs.moss.dev/docs/reference/python/sessions)  
  * Example project using **LiveKit and Moss together**: [https://github.com/livekit-examples/moss-hacker-starter](https://github.com/livekit-examples/moss-hacker-starter)  
  * Documentation index for **coding agents** (Claude Code should read this): [https://docs.moss.dev/llms.txt](https://docs.moss.dev/llms.txt)  
  * An MCP server is configured in the project for coding agents to interact with Moss and its docs  
  * Use case (AI-generated summary from docs)  
    1. **Real-time fact retrieval** — Moss provides **sub-10ms semantic search**, so when the agent detects a claim mid-conversation, it can instantly query your due diligence documents without noticeable delay.

    2. **LiveKit native integration** — Moss has a dedicated LiveKit integration guide, making it straightforward to plug into your existing LiveKit audio pipeline on the FastAPI backend.

    3. **Per-call session indexing** — Each M&A session can have its own Moss session (local index), so conversation context accumulates in real-time alongside the persistent due diligence knowledge base.

    4. **Document knowledge base** — Uploaded due diligence documents (via Unsiloed) can be stored as a Moss cloud index, enabling hybrid semantic + keyword search to surface exact quotes and sources for interjections.

    5. **Source attribution** — Moss returns matching document chunks with metadata, giving you the supporting quotes to send in Zoom chat or the website UI.

    ```suggestions
    (LiveKit Integration Guide)[/docs/integrations/livekit]
    (Real-time Local Indexing)[/docs/build/real-time-local-indexing]
    (Voice Agents)[/docs/voice-agents/voice-agents]
    ```
    * [Real-time Local Indexing](https://docs.moss.dev/docs/build/real-time-local-indexing)  
    * [Indexing Data](https://docs.moss.dev/docs/integrate/indexing-data)  
    * [Quickstart](https://docs.moss.dev/docs/start/quickstart)   

* OpenAI  
  * Assume you know **nothing** about the current state of these APIs, models, and their capabilities, because it is not reflected in Claude Code’s training data  
  * General [documentation](https://developers.openai.com/api/docs)  
  * [Structured outputs API](https://developers.openai.com/api/docs/guides/structured-outputs)  
  * [Python SDK](https://github.com/openai/openai-python)  
  * We will use OpenAI models for summarization, but **not** for voice, embeddings, or other purposes.  
  * Use minimax models exclusively (which is openai compatible), make then configurable in env default to M2.7
* Claude Code references  
  * .mcp.json docs: [https://code.claude.com/docs/en/mcp](https://code.claude.com/docs/en/mcp) (use if adding more MCPs to the project for developer use)

* Zoom Bot API
    * Assume you know **nothing** about the current state of these APIs, models, and their capabilities, because it is not reflected in Claude Code’s training data
    * General [documentation](https://developers.zoom.us/docs/api/)

* Unsiloed
    * General [docuementation](https://www.unsiloed.ai/docs)
    * API Reference [documentation](https://docs.unsiloed.ai/api-reference/parser/parse-document)

* STT and TTS via **LiveKit Inference**
    * The agent uses `inference.STT(model="deepgram/nova-3")` and `inference.TTS(model="cartesia/sonic-3")` — both proxied through the LiveKit API key, so no separate Deepgram or Cartesia accounts are required.
    * Docs: https://docs.livekit.io/agents/integrations/stt/ and https://docs.livekit.io/agents/integrations/tts/

* [DigitalOcean CLI (`doctl`) docs](https://docs.digitalocean.com/reference/doctl/) and [repo](https://github.com/digitalocean/doctl)
