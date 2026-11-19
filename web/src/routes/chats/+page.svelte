<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError, api } from '$lib/api/client';
	import type { CreateChatBody } from '$lib/api/types';
	import { auth } from '$lib/auth.svelte';
	import { chatSubtitle, chatTitle, chats } from '$lib/chats.svelte';

	let mode = $state<'direct' | 'group'>('direct');
	let peerUsername = $state('');
	let groupTitle = $state('');
	let groupMembers = $state('');
	let creating = $state(false);
	let formError = $state<string | null>(null);
	let formOpen = $state(false);

	$effect(() => {
		if (auth.isAuthenticated) void chats.load();
	});

	async function createChat(event: SubmitEvent) {
		event.preventDefault();
		formError = null;
		creating = true;
		try {
			const body: CreateChatBody =
				mode === 'direct'
					? { type: 'direct', username: peerUsername.trim() }
					: {
							type: 'group',
							title: groupTitle.trim(),
							usernames: groupMembers
								.split(',')
								.map((s) => s.trim())
								.filter(Boolean)
						};
			const chat = await api.createChat(body);
			chats.upsert(chat);
			formOpen = false;
			peerUsername = '';
			groupTitle = '';
			groupMembers = '';
			await goto(`/chats/${chat.id}`);
		} catch (err) {
			formError = err instanceof ApiError ? err.message : 'Не удалось создать чат.';
		} finally {
			creating = false;
		}
	}
</script>

<svelte:head>
	<title>Чаты — Messenger</title>
</svelte:head>

{#if !auth.ready}
	<p class="muted">Загрузка…</p>
{:else if !auth.isAuthenticated}
	<section class="empty">
		<h1>Чаты</h1>
		<p class="muted">Чтобы видеть переписки, войдите в аккаунт.</p>
		<div class="row">
			<a class="button" href="/login">Войти</a>
			<a class="button ghost" href="/register">Регистрация</a>
		</div>
	</section>
{:else}
	<div class="head">
		<h1>
			Чаты {#if chats.totalUnread > 0}<span class="badge">{chats.totalUnread}</span>{/if}
		</h1>
		<button type="button" class="button" onclick={() => (formOpen = !formOpen)}>
			{formOpen ? 'Отмена' : 'Новый чат'}
		</button>
	</div>

	{#if formOpen}
		<form class="card form" onsubmit={createChat}>
			<div class="tabs">
				<button type="button" class:active={mode === 'direct'} onclick={() => (mode = 'direct')}
					>Личный</button
				>
				<button type="button" class:active={mode === 'group'} onclick={() => (mode = 'group')}
					>Группа</button
				>
			</div>

			{#if mode === 'direct'}
				<label>
					Имя пользователя
					<input
						bind:value={peerUsername}
						placeholder="например, alice"
						autocomplete="off"
						required
					/>
				</label>
				<p class="hint">Если диалог уже есть, откроется существующий — дублей не будет.</p>
			{:else}
				<label>
					Название
					<input bind:value={groupTitle} placeholder="Учёба" required />
				</label>
				<label>
					Участники
					<input bind:value={groupMembers} placeholder="alice, bob" autocomplete="off" />
				</label>
				<p class="hint">Через запятую. Себя добавлять не нужно — вы станете владельцем.</p>
			{/if}

			{#if formError}<p class="error">{formError}</p>{/if}

			<button type="submit" class="button" disabled={creating}>
				{creating ? 'Создаём…' : 'Создать'}
			</button>
		</form>
	{/if}

	{#if chats.error}
		<p class="error">{chats.error}</p>
	{/if}

	{#if chats.loading && chats.items.length === 0}
		<p class="muted">Загружаем чаты…</p>
	{:else if chats.items.length === 0}
		<section class="empty card">
			<p>Пока ни одного чата.</p>
			<p class="muted">Создайте диалог по имени пользователя или соберите группу.</p>
		</section>
	{:else}
		<ul class="list">
			{#each chats.items as chat (chat.id)}
				{@const active = page.url.pathname === `/chats/${chat.id}`}
				<li>
					<a href="/chats/{chat.id}" class:active>
						<span class="avatar" aria-hidden="true">
							{chatTitle(chat).slice(0, 1).toUpperCase()}
						</span>
						<span class="body">
							<span class="title">{chatTitle(chat)}</span>
							<span class="sub">{chatSubtitle(chat)}</span>
						</span>
						{#if chat.unread > 0}
							<span class="badge">{chat.unread > 99 ? '99+' : chat.unread}</span>
						{/if}
					</a>
				</li>
			{/each}
		</ul>
	{/if}
{/if}

<style>
	.head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		margin-bottom: 20px;
	}

	h1 {
		margin: 0;
		font-size: 24px;
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.badge {
		background: var(--accent);
		color: #fff;
		border-radius: 999px;
		font-size: 12px;
		font-weight: 600;
		line-height: 1;
		padding: 4px 8px;
	}

	.card {
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 20px;
	}

	.form {
		display: flex;
		flex-direction: column;
		gap: 14px;
		margin-bottom: 20px;
	}

	.tabs {
		display: flex;
		gap: 8px;
	}

	.tabs button {
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text-muted);
		cursor: pointer;
		font: inherit;
		font-size: 14px;
		padding: 6px 14px;
	}

	.tabs button.active {
		background: var(--bg);
		border-color: var(--accent);
		color: var(--text);
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		color: var(--text-muted);
	}

	input {
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text);
		font: inherit;
		padding: 9px 12px;
	}

	input:focus {
		border-color: var(--accent);
		outline: none;
	}

	.hint {
		color: var(--text-muted);
		font-size: 13px;
		margin: 0;
	}

	.button {
		align-self: flex-start;
		background: var(--accent);
		border: none;
		border-radius: 8px;
		color: #fff;
		cursor: pointer;
		font: inherit;
		font-size: 14px;
		font-weight: 600;
		padding: 9px 18px;
		text-decoration: none;
	}

	.button:hover {
		filter: brightness(1.1);
		text-decoration: none;
	}

	.button:disabled {
		cursor: default;
		opacity: 0.6;
	}

	.button.ghost {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--text-muted);
	}

	.empty {
		text-align: center;
	}

	.empty h1 {
		justify-content: center;
	}

	.row {
		display: flex;
		gap: 10px;
		justify-content: center;
	}

	.list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.list a {
		align-items: center;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 10px;
		display: flex;
		gap: 14px;
		padding: 12px 16px;
		text-decoration: none;
	}

	.list a:hover {
		border-color: var(--text-muted);
		text-decoration: none;
	}

	.list a.active {
		border-color: var(--accent);
	}

	.avatar {
		align-items: center;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 50%;
		color: var(--text-muted);
		display: flex;
		font-size: 15px;
		font-weight: 600;
		height: 38px;
		justify-content: center;
		flex: 0 0 38px;
	}

	.body {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
		flex: 1;
	}

	.title {
		color: var(--text);
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.sub {
		color: var(--text-muted);
		font-size: 13px;
	}

	.muted {
		color: var(--text-muted);
	}

	.error {
		color: var(--error);
		font-size: 14px;
	}
</style>
