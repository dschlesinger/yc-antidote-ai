<script lang="ts">
	import { supabase } from '$lib/supabase/client';
	import { goto } from '$app/navigation';

	async function handleGetStarted() {
		const { data } = await supabase.auth.getSession();
		goto(data.session ? '/app/session' : '/login');
	}
</script>

<div class="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 text-white">
	<header class="flex items-center justify-between px-8 py-6 max-w-7xl mx-auto">
		<div class="flex items-center gap-3">
			<div class="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center font-bold text-slate-900">A</div>
			<span class="text-xl font-semibold tracking-tight">Antidote AI</span>
		</div>
		<a href="/login" class="text-sm text-slate-300 hover:text-white transition-colors">Sign in</a>
	</header>

	<main class="max-w-4xl mx-auto px-8 pt-24 pb-32 text-center">
		<div class="inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-4 py-1.5 text-emerald-400 text-sm mb-8">
			<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
			Real-time M&amp;A fact checking
		</div>

		<h1 class="text-5xl md:text-6xl font-bold leading-tight mb-6 tracking-tight">
			The truth in every<br />
			<span class="text-emerald-400">acquisition call</span>
		</h1>

		<p class="text-xl text-slate-400 max-w-2xl mx-auto mb-12 leading-relaxed">
			Antidote AI sits silently in your M&amp;A calls and instantly cross-references claims against
			your due diligence data — surfacing discrepancies before they become costly mistakes.
		</p>

		<div class="flex flex-col sm:flex-row gap-4 justify-center">
			<button
				onclick={handleGetStarted}
				class="px-8 py-4 bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-semibold rounded-xl transition-colors text-lg"
			>
				Get started
			</button>
			<a
				href="#how-it-works"
				class="px-8 py-4 border border-slate-600 hover:border-slate-400 rounded-xl transition-colors text-lg text-slate-300 hover:text-white"
			>
				How it works
			</a>
		</div>
	</main>

	<section id="how-it-works" class="max-w-6xl mx-auto px-8 py-24">
		<h2 class="text-3xl font-bold text-center mb-16">How Antidote AI works</h2>
		<div class="grid md:grid-cols-3 gap-8">
			{#each [
				{ step: '01', title: 'Upload due diligence', desc: 'Upload your documents — financials, contracts, data rooms. Antidote processes and indexes them instantly.' },
				{ step: '02', title: 'Join the call', desc: 'Start a session from the browser or add the Zoom bot. Antidote listens passively in the background.' },
				{ step: '03', title: 'Get alerted', desc: 'When a claim contradicts your data, Antidote interjects with the exact source — keeping every party accountable.' }
			] as { step, title, desc }}
				<div class="bg-slate-800/50 border border-slate-700 rounded-2xl p-8">
					<div class="text-emerald-500 text-sm font-mono font-bold mb-4">{step}</div>
					<h3 class="text-xl font-semibold mb-3">{title}</h3>
					<p class="text-slate-400 leading-relaxed">{desc}</p>
				</div>
			{/each}
		</div>
	</section>

	<footer class="border-t border-slate-800 px-8 py-8 text-center text-slate-500 text-sm">
		&copy; {new Date().getFullYear()} Antidote AI. All rights reserved.
	</footer>
</div>
