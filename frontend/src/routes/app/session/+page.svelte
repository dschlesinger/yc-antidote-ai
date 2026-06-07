<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Room, RoomEvent, type RemoteParticipant } from 'livekit-client';
	import { supabase } from '$lib/supabase/client';

	interface Message {
		id: string;
		role: 'agent' | 'system';
		content: string;
		sources?: { text: string; document: string; page?: number }[];
		timestamp: Date;
	}

	interface InterjectionPayload {
		type: 'interjection';
		text: string;
		sources?: { text: string; document: string; page?: number }[];
	}

	let sessionActive = $state(false);
	let muted = $state(false);
	let messages = $state<Message[]>([]);
	let loading = $state(false);
	let errorMsg = $state('');
	let room: Room | null = null;

	function addMessage(msg: Omit<Message, 'id' | 'timestamp'>) {
		messages = [
			...messages,
			{ id: crypto.randomUUID(), timestamp: new Date(), ...msg }
		];
	}

	function handleData(payload: Uint8Array, _participant?: RemoteParticipant) {
		try {
			const text = new TextDecoder().decode(payload);
			const data = JSON.parse(text) as InterjectionPayload;
			if (data.type === 'interjection') {
				addMessage({ role: 'agent', content: data.text, sources: data.sources });
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
			room.localParticipant.setMicrophoneEnabled(true).catch((e) => {
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
		if (room) await room.disconnect();
		room = null;
		sessionActive = false;
		messages = [];
	}

	async function toggleMute() {
		if (!room) return;
		muted = !muted;
		await room.localParticipant.setMicrophoneEnabled(!muted);
	}

	function formatTime(d: Date) {
		return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	onDestroy(() => {
		room?.disconnect();
	});
</script>

<div class="flex flex-col flex-1 h-full">
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
					<div class="flex gap-3 {msg.role === 'agent' ? '' : 'opacity-60'}">
						{#if msg.role === 'agent'}
							<div class="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center text-slate-900 font-bold text-sm shrink-0 mt-0.5">A</div>
						{:else}
							<div class="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-slate-400 text-sm shrink-0 mt-0.5">ℹ</div>
						{/if}
						<div class="flex-1">
							<div class="flex items-center gap-2 mb-1">
								<span class="text-xs font-medium {msg.role === 'agent' ? 'text-emerald-400' : 'text-slate-500'}">
									{msg.role === 'agent' ? 'Antidote AI' : 'System'}
								</span>
								<span class="text-xs text-slate-600">{formatTime(msg.timestamp)}</span>
							</div>
							<p class="text-slate-200 text-sm leading-relaxed">{msg.content}</p>
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
				<div class="flex items-center gap-2">
					<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
					<span class="text-sm text-slate-400">Listening</span>
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
