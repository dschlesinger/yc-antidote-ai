<script lang="ts">
	import { supabase } from '$lib/supabase/client';
	import { goto } from '$app/navigation';

	let email = $state('');
	let password = $state('');
	let mode: 'login' | 'signup' = $state('login');
	let error = $state('');
	let loading = $state(false);

	async function handleSubmit() {
		error = '';
		loading = true;
		try {
			if (mode === 'login') {
				const { error: err } = await supabase.auth.signInWithPassword({ email, password });
				if (err) throw err;
			} else {
				const { error: err } = await supabase.auth.signUp({ email, password });
				if (err) throw err;
			}
			goto('/app/session');
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'An error occurred';
		} finally {
			loading = false;
		}
	}
</script>

<div class="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center px-4">
	<div class="w-full max-w-md">
		<a href="/" class="flex items-center gap-2 justify-center mb-10">
			<div class="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center font-bold text-slate-900">A</div>
			<span class="text-xl font-semibold text-white tracking-tight">Antidote AI</span>
		</a>

		<div class="bg-slate-800 border border-slate-700 rounded-2xl p-8">
			<h1 class="text-2xl font-bold text-white mb-2">
				{mode === 'login' ? 'Welcome back' : 'Create account'}
			</h1>
			<p class="text-slate-400 mb-8 text-sm">
				{mode === 'login' ? 'Sign in to your workspace' : 'Start fact-checking your M&A calls'}
			</p>

			<form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-4">
				<div>
					<label for="email" class="block text-sm font-medium text-slate-300 mb-1.5">Email</label>
					<input
						id="email"
						type="email"
						bind:value={email}
						required
						placeholder="you@company.com"
						class="w-full bg-slate-900 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
					/>
				</div>
				<div>
					<label for="password" class="block text-sm font-medium text-slate-300 mb-1.5">Password</label>
					<input
						id="password"
						type="password"
						bind:value={password}
						required
						placeholder="••••••••"
						class="w-full bg-slate-900 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
					/>
				</div>

				{#if error}
					<p class="text-red-400 text-sm">{error}</p>
				{/if}

				<button
					type="submit"
					disabled={loading}
					class="w-full py-3 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-900 font-semibold rounded-xl transition-colors"
				>
					{loading ? 'Loading…' : mode === 'login' ? 'Sign in' : 'Create account'}
				</button>
			</form>

			<p class="text-center text-sm text-slate-400 mt-6">
				{mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
				<button
					onclick={() => { mode = mode === 'login' ? 'signup' : 'login'; error = ''; }}
					class="text-emerald-400 hover:text-emerald-300 ml-1 font-medium"
				>
					{mode === 'login' ? 'Sign up' : 'Sign in'}
				</button>
			</p>
		</div>
	</div>
</div>
