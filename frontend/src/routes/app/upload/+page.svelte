<script lang="ts">
	import { supabase } from '$lib/supabase/client';

	let files = $state<File[]>([]);
	let uploading = $state(false);
	let uploadedDocs = $state<{ name: string; id: string; status: 'processing' | 'ready' | 'error' }[]>([]);
	let dragOver = $state(false);
	let errorMsg = $state('');

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragOver = false;
		const dropped = Array.from(e.dataTransfer?.files ?? []);
		files = [...files, ...dropped];
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		files = [...files, ...Array.from(input.files ?? [])];
	}

	function removeFile(index: number) {
		files = files.filter((_, i) => i !== index);
	}

	async function uploadFiles() {
		if (!files.length) return;
		uploading = true;
		errorMsg = '';

		const { data: session } = await supabase.auth.getSession();
		if (!session.session) return;

		for (const file of files) {
			try {
				const formData = new FormData();
				formData.append('file', file);

				const res = await fetch('/api/documents', {
					method: 'POST',
					body: formData,
					headers: {
						Authorization: `Bearer ${session.session.access_token}`
					}
				});

				if (!res.ok) throw new Error(await res.text());
				const doc = await res.json();
				uploadedDocs = [...uploadedDocs, { name: file.name, id: doc.id, status: 'processing' }];
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
		<p class="text-slate-500 text-sm mb-6">PDF, DOCX, XLSX, CSV, TXT and more</p>
		<label class="px-5 py-2.5 bg-slate-700 hover:bg-slate-600 rounded-xl text-sm font-medium cursor-pointer transition-colors">
			Browse files
			<input type="file" multiple class="hidden" onchange={handleFileInput} />
		</label>
	</div>

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

		{#if errorMsg}
			<p class="text-red-400 text-sm mb-4">{errorMsg}</p>
		{/if}

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
