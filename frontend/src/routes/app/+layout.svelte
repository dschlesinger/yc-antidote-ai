<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { supabase } from '$lib/supabase/client';
	import { page } from '$app/stores';

	let { children } = $props();
	let userEmail = $state<string | null>(null);

	onMount(async () => {
		const { data } = await supabase.auth.getSession();
		if (!data.session) {
			goto('/login');
			return;
		}
		userEmail = data.session.user.email ?? null;

		supabase.auth.onAuthStateChange((_event, session) => {
			if (!session) goto('/login');
		});
	});

	async function signOut() {
		await supabase.auth.signOut();
		goto('/');
	}

	const navLinks = [
		{ href: '/app/upload', label: 'Documents' },
		{ href: '/app/session', label: 'Session' }
	];
</script>

<div class="min-h-screen bg-slate-900 text-white flex flex-col">
	<nav class="border-b border-slate-800 px-6 py-4 flex items-center justify-between">
		<div class="flex items-center gap-6">
			<a href="/" class="flex items-center gap-2">
				<div class="w-7 h-7 rounded-full bg-emerald-500 flex items-center justify-center font-bold text-slate-900 text-sm">A</div>
				<span class="font-semibold tracking-tight">Antidote AI</span>
			</a>
			<div class="hidden sm:flex gap-1">
				{#each navLinks as link}
					<a
						href={link.href}
						class="px-3 py-1.5 rounded-lg text-sm transition-colors {$page.url.pathname.startsWith(link.href) ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'}"
					>
						{link.label}
					</a>
				{/each}
			</div>
		</div>
		<div class="flex items-center gap-4">
			{#if userEmail}
				<span class="text-sm text-slate-400 hidden sm:block">{userEmail}</span>
			{/if}
			<button
				onclick={signOut}
				class="text-sm text-slate-400 hover:text-white transition-colors"
			>
				Sign out
			</button>
		</div>
	</nav>

	<main class="flex-1 flex flex-col">
		{@render children()}
	</main>
</div>
