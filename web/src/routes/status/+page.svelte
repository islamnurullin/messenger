<script lang="ts">
	import { api } from '$lib/api/client';
	import type { HealthResponse } from '$lib/api/types';

	const REFRESH_MS = 10_000;

	let health = $state<HealthResponse | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);
	let lastChecked = $state<Date | null>(null);

	async function load() {
		loading = true;
		error = null;
		try {
			health = await api.health();
			lastChecked = new Date();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
			health = null;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		void load();
		const timer = setInterval(() => void load(), REFRESH_MS);
		return () => clearInterval(timer);
	});

	const descriptions: Record<string, string> = {
		database: 'PostgreSQL — источник правды. Без неё сервис не работает.',
		redis: 'Брокер очередей и хранилище Centrifugo. Без него нет доставки.',
		centrifugo: 'WebSocket-сервер. Без него сообщения сохраняются, но не доставляются.',
		elasticsearch: 'Полнотекстовый поиск. Необязателен на этом этапе.'
	};

	function tone(status: string): string {
		if (status === 'ok') return 'ok';
		if (status === 'disabled') return 'muted';
		return 'error';
	}
</script>

<svelte:head>
	<title>Messenger — состояние</title>
</svelte:head>

<h1>Состояние системы</h1>
<p class="lead">
	Страница опрашивает <code>GET /api/health</code> каждые {REFRESH_MS / 1000} секунд. Здесь видно, какая
	зависимость отвалилась, — это первое, что нужно смотреть, если что-то не работает.
</p>

<div class="toolbar">
	<button onclick={load} disabled={loading}>{loading ? 'Проверяю…' : 'Проверить сейчас'}</button>
	{#if lastChecked}
		<span class="muted">Обновлено: {lastChecked.toLocaleTimeString('ru-RU')}</span>
	{/if}
</div>

{#if error}
	<div class="banner error">
		<strong>Бэкенд не отвечает.</strong>
		<span>{error}</span>
	</div>
{:else if health}
	<div
		class="banner"
		class:ok={health.status === 'ok'}
		class:warn={health.status === 'degraded'}
		class:error={health.status === 'unavailable'}
	>
		<strong>{health.status}</strong>
		{#if health.status === 'ok'}
			<span>Все обязательные зависимости живы.</span>
		{:else if health.status === 'degraded'}
			<span>Ядро работает, но часть сервисов недоступна — см. таблицу.</span>
		{:else}
			<span>Недоступна обязательная зависимость. Сервис не может принимать запросы.</span>
		{/if}
	</div>

	<table>
		<thead>
			<tr>
				<th>Компонент</th>
				<th>Статус</th>
				<th>Задержка</th>
				<th>Пояснение</th>
			</tr>
		</thead>
		<tbody>
			{#each Object.entries(health.checks) as [name, check] (name)}
				<tr>
					<td><code>{name}</code></td>
					<td class={tone(check.status)}>{check.status}</td>
					<td>{check.latency_ms !== undefined ? `${check.latency_ms} мс` : '—'}</td>
					<td class="muted">
						{#if check.error}
							<span class="error-text">{check.error}</span>
						{:else}
							{descriptions[name] ?? '—'}
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>

	{#if health.checks.elasticsearch?.status === 'disabled'}
		<p class="hint">
			Elasticsearch выключен. Чтобы включить:
			<code>docker compose -f infra/docker-compose.yml --profile search up -d</code> и
			<code>ELASTICSEARCH_ENABLED=true</code> в <code>.env</code>.
		</p>
	{/if}
{/if}

<style>
	h1 {
		margin: 0 0 8px;
		font-size: 28px;
		letter-spacing: -0.01em;
	}

	.lead {
		color: var(--text-muted);
		max-width: 62ch;
		margin: 0 0 24px;
	}

	.toolbar {
		display: flex;
		align-items: center;
		gap: 14px;
		margin-bottom: 20px;
	}

	.muted {
		color: var(--text-muted);
		font-size: 13px;
	}

	.banner {
		border-radius: var(--radius);
		padding: 14px 16px;
		margin-bottom: 20px;
		border: 1px solid var(--border);
		background: var(--bg-elevated);
		display: flex;
		flex-direction: column;
		gap: 4px;
		font-size: 14px;
	}

	.banner.ok {
		border-color: var(--ok);
	}

	.banner.ok strong {
		color: var(--ok);
	}

	.banner.warn {
		border-color: var(--warn);
	}

	.banner.warn strong {
		color: var(--warn);
	}

	.banner.error {
		border-color: var(--error);
	}

	.banner.error strong {
		color: var(--error);
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 14px;
	}

	th {
		text-align: left;
		font-weight: 600;
		color: var(--text-muted);
		font-size: 12px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		padding: 0 12px 10px 0;
		border-bottom: 1px solid var(--border);
	}

	td {
		padding: 10px 12px 10px 0;
		border-bottom: 1px solid var(--border);
		vertical-align: top;
	}

	tr:last-child td {
		border-bottom: none;
	}

	.ok {
		color: var(--ok);
	}

	.warn {
		color: var(--warn);
	}

	.error {
		color: var(--error);
	}

	.error-text {
		color: var(--error);
		overflow-wrap: anywhere;
	}

	.hint {
		color: var(--text-muted);
		font-size: 13px;
		margin: 20px 0 0;
		line-height: 1.6;
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
