"""Publish a WAV file (or a sine sweep fallback) into a LiveKit room."""

import asyncio
import os
import sys
import wave

from dotenv import load_dotenv
from livekit import api, rtc

load_dotenv()


async def main(room_name: str, wav_path: str | None) -> None:
    url = os.environ["LIVEKIT_URL"]
    token = (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity("dummy-publisher")
        .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=True))
        .to_jwt()
    )

    room = rtc.Room()
    await room.connect(url, token)
    print(f"connected to room={room_name}", flush=True)

    if wav_path:
        with open(wav_path, "rb") as f:
            data = f.read()
        with wave.open(wav_path, "rb") as w:
            sample_rate = w.getframerate()
            num_channels = w.getnchannels()
        # Read raw PCM (skip 44-byte WAV header)
        pcm = data[44:]
        print(f"loaded {wav_path}: sr={sample_rate} ch={num_channels} bytes={len(pcm)}", flush=True)
    else:
        import math
        sample_rate, num_channels = 16000, 1
        samples = []
        for i in range(sample_rate * 3):
            v = int(8000 * math.sin(2 * math.pi * 220 * i / sample_rate))
            samples.append(v.to_bytes(2, "little", signed=True))
        pcm = b"".join(samples)

    source = rtc.AudioSource(sample_rate, num_channels)
    track = rtc.LocalAudioTrack.create_audio_track("dummy", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    await room.local_participant.publish_track(track, options)
    print("audio track published as MICROPHONE", flush=True)

    # Wait for the agent to attach its input stream before sending speech.
    await asyncio.sleep(3)
    print("starting to stream audio", flush=True)

    # 100ms chunks
    samples_per_chunk = sample_rate // 10
    bytes_per_chunk = samples_per_chunk * 2 * num_channels
    for i in range(0, len(pcm), bytes_per_chunk):
        chunk = pcm[i:i + bytes_per_chunk]
        if len(chunk) < bytes_per_chunk:
            break
        frame = rtc.AudioFrame(
            data=chunk,
            sample_rate=sample_rate,
            num_channels=num_channels,
            samples_per_channel=samples_per_chunk,
        )
        await source.capture_frame(frame)
        await asyncio.sleep(0.1)

    duration_s = len(pcm) / (sample_rate * 2 * num_channels)

    # Subscribe to data messages so we can see the agent's interjection
    @room.on("data_received")
    def _on_data(data: rtc.DataPacket) -> None:
        print(f"DATA from {data.participant.identity if data.participant else '?'}: "
              f"{bytes(data.data).decode(errors='replace')}", flush=True)

    print(f"sent {duration_s:.2f}s of audio; idling 25s for agent reply", flush=True)
    await asyncio.sleep(25)
    await room.disconnect()


if __name__ == "__main__":
    room = sys.argv[1] if len(sys.argv) > 1 else "antidote-dummy"
    wav = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(main(room, wav))
