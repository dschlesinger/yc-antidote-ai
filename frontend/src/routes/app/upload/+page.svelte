<script lang="ts">
	import { onMount } from 'svelte';
	import { supabase } from '$lib/supabase/client';

	interface UploadedDoc {
		name: string;
		jobId: string;
		status: 'processing' | 'ready' | 'error';
	}

	const STORAGE_KEY = 'antidote.uploadedDocs';

	function loadDocsFromStorage(): UploadedDoc[] {
		if (typeof localStorage === 'undefined') return [];
		try {
			const raw = localStorage.getItem(STORAGE_KEY);
			return raw ? (JSON.parse(raw) as UploadedDoc[]) : [];
		} catch {
			return [];
		}
	}

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let uploadedDocs = $state<UploadedDoc[]>(loadDocsFromStorage());
	let dragOver = $state(false);
	let errorMsg = $state('');

	$effect(() => {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(uploadedDocs));
		} catch {
			// localStorage may be unavailable (private mode); ignore.
		}
	});

	onMount(() => {
		// Resume polling for anything that was still in flight when the page was closed.
		uploadedDocs
			.filter((d) => d.status === 'processing')
			.forEach((d) => pollStatus(d.jobId));
	});

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		files = [...files, ...Array.from(e.dataTransfer?.files ?? [])];
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		files = [...files, ...Array.from(input.files ?? [])];
	}

	function removeFile(index: number) {
		files = files.filter((_, i) => i !== index);
	}

	async function authHeader(): Promise<Record<string, string> | null> {
		const { data } = await supabase.auth.getSession();
		if (!data.session) return null;
		return { Authorization: `Bearer ${data.session.access_token}` };
	}

	function pollStatus(jobId: string) {
		let consecutive404 = 0;
		const interval = setInterval(async () => {
			const headers = await authHeader();
			if (!headers) return clearInterval(interval);
			try {
				const res = await fetch(`/api/documents/${jobId}`, { headers });
				// 404 means the backend doesn't know about this job anymore
				// (in-memory job store reset). After a few tries, mark as error.
				if (res.status === 404) {
					if (++consecutive404 >= 2) {
						uploadedDocs = uploadedDocs.map((d) =>
							d.jobId === jobId ? { ...d, status: 'error' } : d
						);
						clearInterval(interval);
					}
					return;
				}
				if (!res.ok) return;
				consecutive404 = 0;
				const data = await res.json();
				uploadedDocs = uploadedDocs.map((d) => (d.jobId === jobId ? { ...d, status: data.status } : d));
				if (data.status === 'ready' || data.status === 'error') clearInterval(interval);
			} catch {
				// transient errors are fine; the next tick retries
			}
		}, 4000);
	}

	async function uploadFiles() {
		if (!files.length) return;
		uploading = true;
		errorMsg = '';

		const headers = await authHeader();
		if (!headers) {
			uploading = false;
			return;
		}

		for (const file of files) {
			try {
				const formData = new FormData();
				formData.append('file', file);
				const res = await fetch('/api/documents/', { method: 'POST', body: formData, headers });
				if (!res.ok) {
					let detail = `Upload failed (${res.status})`;
					try {
						const body = await res.json();
						if (body?.detail) detail = body.detail;
					} catch {
						const txt = await res.text();
						if (txt) detail = txt;
					}
					throw new Error(`${file.name}: ${detail}`);
				}
				const doc = await res.json();
				uploadedDocs = [
					...uploadedDocs,
					{ name: file.name, jobId: doc.unsiloed_job_id, status: 'processing' }
				];
				pollStatus(doc.unsiloed_job_id);
			} catch (e) {
				errorMsg = e instanceof Error ? e.message : 'Upload failed';
			}
		}

		files = [];
		uploading = false;
	}
</script>

<div class="max-w-3xl mx-auto px-6 py-12 w-full">
	<h1 class="text-2xl font-bold mb-2">Due diligence documents</h1>
	<p class="text-slate-400 mb-8">Upload documents to build your fact-checking knowledge base.</p>

	<!-- Drop zone -->
	<div
		role="region"
		aria-label="File upload area"
		class="border-2 border-dashed rounded-2xl p-12 text-center transition-colors mb-6 {dragOver ? 'border-emerald-500 bg-emerald-500/5' : 'border-slate-700 hover:border-slate-500'}"
		ondragover={(e) => { e.preventDefault(); dragOver = true; }}
		ondragleave={() => { dragOver = false; }}
		ondrop={handleDrop}
	>
		<div class="text-4xl mb-4">📄</div>
		<p class="text-slate-300 font-medium mb-2">Drop files here or browse</p>
		<p class="text-slate-500 text-sm mb-6">PDF, DOCX, XLSX, PPTX, PNG, JPG, TIFF</p>
		<label class="px-5 py-2.5 bg-slate-700 hover:bg-slate-600 rounded-xl text-sm font-medium cursor-pointer transition-colors">
			Browse files
			<input
				type="file"
				multiple
				class="hidden"
				accept=".pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tiff,.tif"
				onchange={handleFileInput}
			/>
		</label>
	</div>

	<!-- Errors are persistent (don't disappear when the staged-file list clears) -->
	{#if errorMsg}
		<div class="bg-red-500/10 border border-red-500/30 rounded-xl px-4 py-3 mb-6 flex items-start gap-3">
			<span class="text-red-400 shrink-0">⚠</span>
			<p class="text-red-300 text-sm leading-relaxed flex-1">{errorMsg}</p>
			<button
				onclick={() => (errorMsg = '')}
				class="text-red-400 hover:text-red-200 shrink-0"
				aria-label="Dismiss"
			>✕</button>
		</div>
	{/if}

	<!-- Staged files -->
	{#if files.length > 0}
		<div class="bg-slate-800 border border-slate-700 rounded-xl mb-6">
			<div class="px-4 py-3 border-b border-slate-700 text-sm font-medium text-slate-300">
				{files.length} file{files.length !== 1 ? 's' : ''} ready to upload
			</div>
			<ul class="divide-y divide-slate-700">
				{#each files as file, i}
					<li class="flex items-center justify-between px-4 py-3">
						<span class="text-sm text-slate-200 truncate">{file.name}</span>
						<div class="flex items-center gap-3 ml-4 shrink-0">
							<span class="text-xs text-slate-500">{(file.size / 1024).toFixed(0)} KB</span>
							<button onclick={() => removeFile(i)} class="text-slate-500 hover:text-red-400 transition-colors">✕</button>
						</div>
					</li>
				{/each}
			</ul>
		</div>

		<button
			onclick={uploadFiles}
			disabled={uploading}
			class="w-full py-3 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-900 font-semibold rounded-xl transition-colors"
		>
			{uploading ? 'Uploading…' : 'Upload and index'}
		</button>
	{/if}

	<!-- Uploaded docs -->
	{#if uploadedDocs.length > 0}
		<div class="mt-10">
			<h2 class="text-lg font-semibold mb-4">Indexed documents</h2>
			<div class="bg-slate-800 border border-slate-700 rounded-xl divide-y divide-slate-700">
				{#each uploadedDocs as doc}
					<div class="flex items-center justify-between px-4 py-3">
						<span class="text-sm text-slate-200 truncate">{doc.name}</span>
						<span class="text-xs px-2 py-1 rounded-full ml-4 shrink-0 {
							doc.status === 'ready' ? 'bg-emerald-500/10 text-emerald-400' :
							doc.status === 'error' ? 'bg-red-500/10 text-red-400' :
							'bg-slate-700 text-slate-400'
						}">
							{doc.status}
						</span>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>
