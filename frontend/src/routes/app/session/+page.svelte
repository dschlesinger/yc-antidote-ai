<script lang="ts">
	import { onDestroy } from 'svelte';
	import {
		LocalTrackPublication,
		Room,
		RoomEvent,
		Track,
		TrackEvent,
		type RemoteParticipant
	} from 'livekit-client';
	import { supabase } from '$lib/supabase/client';

	interface Message {
		id: string;
		role: 'agent' | 'system' | 'user';
		content: string;
		speaker?: string | null;
		sources?: { text: string; document: string; page?: number }[];
		timestamp: Date;
	}

	type DataPayload =
		| { type: 'interjection'; text: string; sources?: Message['sources'] }
		| { type: 'user_transcript'; text: string; speaker?: string | null };

	interface ActiveInterjection {
		id: string;
		text: string;
	}

	let sessionActive = $state(false);
	let muted = $state(false);
	let messages = $state<Message[]>([]);
	let loading = $state(false);
	let errorMsg = $state('');
	let audioLevel = $state(0); // 0..1, RMS amplified
	let micActive = $state(false);
	let activeInterjection = $state<ActiveInterjection | null>(null);
	let room: Room | null = null;
	let audioCtx: AudioContext | null = null;
	let levelRaf = 0;

	function addMessage(msg: Omit<Message, 'id' | 'timestamp'>) {
		messages = [
			...messages,
			{ id: crypto.randomUUID(), timestamp: new Date(), ...msg }
		];
	}

	function startLevelMeter(track: MediaStreamTrack) {
		stopLevelMeter();
		audioCtx = new AudioContext();
		const stream = new MediaStream([track]);
		const src = audioCtx.createMediaStreamSource(stream);
		const analyser = audioCtx.createAnalyser();
		analyser.fftSize = 512;
		src.connect(analyser);
		const buf = new Uint8Array(analyser.fftSize);

		const tick = () => {
			analyser.getByteTimeDomainData(buf);
			let sum = 0;
			for (let i = 0; i < buf.length; i++) {
				const v = (buf[i] - 128) / 128;
				sum += v * v;
			}
			const rms = Math.sqrt(sum / buf.length);
			// Amplify since speech RMS is usually 0.02..0.2; cap at 1.
			audioLevel = Math.min(1, rms * 5);
			levelRaf = requestAnimationFrame(tick);
		};
		tick();
	}

	function stopLevelMeter() {
		if (levelRaf) cancelAnimationFrame(levelRaf);
		levelRaf = 0;
		audioCtx?.close().catch(() => {});
		audioCtx = null;
		audioLevel = 0;
		micActive = false;
	}

	function attachMicMeter(pub: LocalTrackPublication) {
		const track = pub.track;
		if (track?.mediaStreamTrack) {
			micActive = true;
			startLevelMeter(track.mediaStreamTrack);
		}
		track?.on(TrackEvent.Ended, stopLevelMeter);
		track?.on(TrackEvent.Muted, () => (audioLevel = 0));
	}

	function playChime() {
		try {
			const ctx = new AudioContext();
			const tone = (freq: number, start: number, duration: number) => {
				const o = ctx.createOscillator();
				const g = ctx.createGain();
				o.type = 'sine';
				o.frequency.value = freq;
				o.connect(g);
				g.connect(ctx.destination);
				const t0 = ctx.currentTime + start;
				g.gain.setValueAtTime(0.0001, t0);
				g.gain.exponentialRampToValueAtTime(0.18, t0 + 0.02);
				g.gain.exponentialRampToValueAtTime(0.0001, t0 + duration);
				o.start(t0);
				o.stop(t0 + duration + 0.02);
			};
			tone(880, 0, 0.18);
			tone(1320, 0.12, 0.26);
			// Let GC close the context after the longest tone finishes.
			setTimeout(() => ctx.close().catch(() => {}), 600);
		} catch {
			// AudioContext unavailable (e.g. test runner) — ignore.
		}
	}

	async function dismissInterjection() {
		activeInterjection = null;
		// Ask the agent to stop the in-flight TTS playout.
		if (!room) return;
		try {
			const data = new TextEncoder().encode(JSON.stringify({ type: 'stop_speech' }));
			await room.localParticipant.publishData(data, { reliable: true });
		} catch {
			// Best-effort; user already dismissed visually.
		}
	}

	function handleData(payload: Uint8Array, _participant?: RemoteParticipant) {
		try {
			const text = new TextDecoder().decode(payload);
			const data = JSON.parse(text) as DataPayload;
			if (data.type === 'interjection') {
				addMessage({ role: 'agent', content: data.text, sources: data.sources });
				playChime();
				activeInterjection = { id: crypto.randomUUID(), text: data.text };
			} else if (data.type === 'user_transcript') {
				addMessage({ role: 'user', content: data.text, speaker: data.speaker });
			}
		} catch (e) {
			console.warn('Failed to parse data message', e);
		}
	}

	async function startSession() {
		loading = true;
		errorMsg = '';

		const { data } = await supabase.auth.getSession();
		if (!data.session) {
			loading = false;
			return;
		}

		try {
			const res = await fetch('/api/session/token', {
				method: 'POST',
				headers: {
					Authorization: `Bearer ${data.session.access_token}`,
					'Content-Type': 'application/json'
				}
			});
			if (!res.ok) throw new Error(`Token request failed: ${res.status}`);
			const body = await res.json();

			room = new Room();
			room.on(RoomEvent.DataReceived, handleData);
			room.on(RoomEvent.Disconnected, () => {
				sessionActive = false;
				room = null;
			});

			await room.connect(body.livekit_url, body.token);
			sessionActive = true;
			muted = false;
			addMessage({
				role: 'system',
				content: 'Antidote AI is now listening. It will interject if a claim contradicts your due diligence data.'
			});

			// Don't block session start on mic permission — handle async.
			room.localParticipant
				.setMicrophoneEnabled(true)
				.then(() => {
					const pub = room?.localParticipant.getTrackPublication(Track.Source.Microphone);
					if (pub) attachMicMeter(pub);
				})
				.catch((e) => {
					errorMsg = `Microphone unavailable: ${e instanceof Error ? e.message : 'permission denied'}`;
					muted = true;
				});
		} catch (e) {
			errorMsg = e instanceof Error ? e.message : 'Failed to start session';
			if (room) await room.disconnect();
			room = null;
		} finally {
			loading = false;
		}
	}

	async function stopSession() {
		stopLevelMeter();
		activeInterjection = null;
		if (room) await room.disconnect();
		room = null;
		sessionActive = false;
		messages = [];
	}

	async function toggleMute() {
		if (!room) return;
		muted = !muted;
		await room.localParticipant.setMicrophoneEnabled(!muted);
		if (muted) {
			audioLevel = 0;
		} else {
			const pub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
			if (pub) attachMicMeter(pub);
		}
	}

	function formatTime(d: Date) {
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	onDestroy(() => {
		stopLevelMeter();
		room?.disconnect();
	});
</script>

<div class="flex flex-col flex-1 h-full relative">
	<!-- Interjection popup (click to dismiss and stop TTS) -->
	{#if activeInterjection}
		<button
			type="button"
			onclick={dismissInterjection}
			class="absolute top-4 left-1/2 -translate-x-1/2 z-20 max-w-xl w-[calc(100%-2rem)] text-left bg-emerald-500/15 border border-emerald-500/40 backdrop-blur-md rounded-2xl px-5 py-4 shadow-2xl shadow-emerald-500/20 hover:bg-emerald-500/20 transition-colors animate-[fadeIn_120ms_ease-out]"
			aria-label="Dismiss interjection"
		>
			<div class="flex items-start gap-3">
				<div class="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-slate-900 font-bold text-sm shrink-0 mt-0.5">A</div>
				<div class="flex-1 min-w-0">
					<div class="text-[11px] uppercase tracking-wider font-semibold text-emerald-400 mb-1">
						Antidote AI · fact check
					</div>
					<p class="text-sm text-white leading-relaxed">{activeInterjection.text}</p>
					<p class="text-[10px] text-emerald-400/70 mt-2">Tap anywhere to dismiss</p>
				</div>
			</div>
		</button>
	{/if}

	<!-- Messages area -->
	<div class="flex-1 overflow-y-auto px-4 py-6 max-w-3xl w-full mx-auto">
		{#if !sessionActive}
			<div class="flex flex-col items-center justify-center h-full text-center py-24">
				<div class="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-6 text-2xl">
					🎙️
				</div>
				<h2 class="text-xl font-semibold mb-2">Ready to start</h2>
				<p class="text-slate-400 text-sm max-w-sm">
					Press Start below. Antidote will passively monitor the conversation and interject when it detects a discrepancy.
				</p>
			</div>
		{:else}
			<div class="space-y-4">
				{#each messages as msg}
					{@const isAgent = msg.role === 'agent'}
					{@const isUser = msg.role === 'user'}
					{@const speakerLabel = isUser ? (msg.speaker ?? 'You') : ''}
					{@const speakerInitials = isUser
						? (msg.speaker ? msg.speaker.replace('Person ', 'P') : 'You')
						: ''}
					<div class="flex gap-3 {isAgent ? '' : isUser ? '' : 'opacity-60'}">
						{#if isAgent}
							<div class="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-slate-900 font-bold text-sm shrink-0 mt-0.5">A</div>
						{:else if isUser}
							<div class="w-8 h-8 rounded-full bg-slate-600 flex items-center justify-center text-slate-200 font-bold text-xs shrink-0 mt-0.5">{speakerInitials}</div>
						{:else}
							<div class="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-slate-400 text-sm shrink-0 mt-0.5">ℹ</div>
						{/if}
						<div class="flex-1">
							<div class="flex items-center gap-2 mb-1">
								<span class="text-xs font-medium {isAgent ? 'text-emerald-400' : isUser ? 'text-slate-300' : 'text-slate-500'}">
									{isAgent ? 'Antidote AI' : isUser ? speakerLabel : 'System'}
								</span>
								<span class="text-xs text-slate-600">{formatTime(msg.timestamp)}</span>
							</div>
							<p class="text-sm leading-relaxed {isUser ? 'text-slate-400 italic' : 'text-slate-200'}">{msg.content}</p>
							{#if msg.sources?.length}
								<div class="mt-3 space-y-2">
									{#each msg.sources as src}
										<div class="bg-slate-800 border border-slate-700 rounded-xl px-4 py-3">
											<div class="text-xs text-slate-500 mb-1">
												{src.document}{src.page != null ? ` · p.${src.page}` : ''}
											</div>
											<p class="text-xs text-slate-300 italic">"{src.text}"</p>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	</div>

	<!-- Footer controls -->
	<div class="border-t border-slate-800 bg-slate-900/80 backdrop-blur px-4 py-4">
		{#if errorMsg}
			<div class="max-w-3xl mx-auto mb-3 text-sm text-red-400">{errorMsg}</div>
		{/if}
		<div class="max-w-3xl mx-auto flex items-center justify-between gap-4">
			{#if sessionActive}
				<div class="flex items-center gap-3 min-w-0">
					<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0"></span>
					<span class="text-sm text-slate-400 shrink-0">Listening</span>
					<div
						class="relative w-32 h-1.5 bg-slate-800 rounded-full overflow-hidden"
						title={micActive ? `Mic level: ${Math.round(audioLevel * 100)}%` : 'Mic not active'}
					>
						<div
							class="absolute inset-y-0 left-0 rounded-full transition-[width] duration-75 ease-out {audioLevel > 0.7 ? 'bg-red-400' : audioLevel > 0.15 ? 'bg-emerald-400' : 'bg-emerald-500/40'}"
							style="width: {Math.round(audioLevel * 100)}%"
						></div>
					</div>
					{#if !micActive && !muted}
						<span class="text-xs text-amber-400 shrink-0">no mic</span>
					{/if}
				</div>
				<div class="flex items-center gap-3">
					<button
						onclick={toggleMute}
						class="px-4 py-2 rounded-xl text-sm font-medium transition-colors {muted ? 'bg-amber-500/10 border border-amber-500/30 text-amber-400' : 'bg-slate-800 border border-slate-700 text-slate-300 hover:text-white'}"
					>
						{muted ? '🔇 Unmute' : '🎙️ Mute'}
					</button>
					<button
						onclick={stopSession}
						class="px-4 py-2 bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 rounded-xl text-sm font-medium transition-colors"
					>
						Stop
					</button>
				</div>
			{:else}
				<div></div>
				<button
					onclick={startSession}
					disabled={loading}
					class="px-8 py-3 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-900 font-semibold rounded-xl transition-colors"
				>
					{loading ? 'Starting…' : '▶ Start session'}
				</button>
			{/if}
		</div>
	</div>
</div>
