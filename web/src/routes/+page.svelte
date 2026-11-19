<script lang="ts">
	import { api } from '$lib/api/client';
	import type { HealthResponse } from '$lib/api/types';

	let health = $state<HealthResponse | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	async function load() {
		loading = true;
		error = null;
		try {
			health = await api.health();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			health = null;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void load();
	});

	const labels: Record<string, string> = {
		ok: 'Работает',
		degraded: 'Частично',
		unavailable: 'Недоступен'
	};
</script>

<svelte:head>
	<title>Messenger — обзор</title>
</svelte:head>

<h1>Messenger</h1>
<p class="lead">
	Учебный мессенджер: личные сообщения, группы и каналы. Этап 2 — инфраструктура и аккаунты.
</p>

<section>
	<h2>Состояние системы</h2>

	{#if loading}
		<p class="muted">Проверяю зависимости…</p>
	{:else if error}
		<div class="banner error">
			<strong>Бэкенд не отвечает.</strong>
			<span>{error}</span>
			<p class="hint">
				Запустите <code>docker compose -f infra/docker-compose.yml up -d</code>, затем
				<code>python manage.py runserver</code> в папке <code>backend</code>.
			</p>
		</div>
	{:else if health}
		<div
			class="banner"
			class:ok={health.status === 'ok'}
			class:warn={health.status === 'degraded'}
			class:error={health.status === 'unavailable'}
		>
			<strong>{labels[health.status] ?? health.status}</strong>
		</div>

		<ul class="checks">
			{#each Object.entries(health.checks) as [name, check] (name)}
				<li class:down={check.status === 'error'}>
					<span class="name">{name}</span>
					<span class="status">{check.status}</span>
					{#if check.latency_ms !== undefined}
						<span class="latency">{check.latency_ms} мс</span>
					{/if}
					{#if check.error}
						<span class="reason">{check.error}</span>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}

	<button onclick={load} disabled={loading}>
		{loading ? 'Проверяю…' : 'Проверить снова'}
	</button>
</section>

<style>
	h1 {
		margin: 0 0 8px;
		font-size: 28px;
		letter-spacing: -0.01em;
	}

	.lead {
		color: var(--text-muted);
		max-width: 60ch;
		margin: 0 0 32px;
	}

	h2 {
		font-size: 18px;
		margin: 0 0 16px;
	}

	section {
		border: 1px solid var(--border);
		background: var(--bg-elevated);
		border-radius: var(--radius);
		padding: 20px 22px;
	}

	.muted {
		color: var(--text-muted);
	}

	.banner {
		border-radius: var(--radius);
		padding: 12px 16px;
		margin-bottom: 16px;
		border: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.banner.ok {
		border-color: var(--ok);
		color: var(--ok);
	}

	.banner.warn {
		border-color: var(--warn);
		color: var(--warn);
	}

	.banner.error {
		border-color: var(--error);
		color: var(--error);
	}

	.hint {
		color: var(--text-muted);
		font-size: 13px;
		margin: 4px 0 0;
	}

	.checks {
		list-style: none;
		padding: 0;
		margin: 0 0 20px;
	}

	.checks li {
		display: flex;
		gap: 12px;
		align-items: baseline;
		padding: 8px 0;
		border-bottom: 1px solid var(--border);
		font-size: 14px;
	}

	.checks li:last-child {
		border-bottom: none;
	}

	.name {
		font-family: var(--mono);
		min-width: 130px;
		color: var(--text);
	}

	.status {
		color: var(--ok);
	}

	.down .status {
		color: var(--error);
	}

	.latency {
		color: var(--text-muted);
		font-size: 13px;
	}

	.reason {
		color: var(--error);
		font-size: 13px;
		opacity: 0.8;
		overflow-wrap: anywhere;
	}

	button {
		background: var(--accent);
		color: #fff;
		border: none;
		border-radius: var(--radius);
		padding: 9px 18px;
		font-size: 14px;
		cursor: pointer;
	}

	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
</style>
