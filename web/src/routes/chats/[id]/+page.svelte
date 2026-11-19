<script lang="ts">
	import { page } from '$app/state';
	import { api } from '$lib/api/client';
	import type { Chat, ChatMember } from '$lib/api/types';
	import { auth } from '$lib/auth.svelte';
	import { chatSubtitle, chatTitle } from '$lib/chats.svelte';

	// Параметры маршрута в +page.svelte не приходят пропсами — SvelteKit отдаёт
	// их только через page.params. Из-за этого id был undefined, Number(undefined)
	// давал NaN, и страница навсегда застревала на «Загружаем чат…».
	const numericId = $derived(Number(page.params.id));

	let chat = $state<Chat | null>(null);
	let members = $state<ChatMember[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let inviteName = $state('');
	let inviteError = $state<string | null>(null);
	let inviting = $state(false);

	$effect(() => {
		if (!auth.ready || !auth.isAuthenticated) return;
		void load();
	});

	// Сбрасываем состояние при переходе между чатами, иначе на новом чате
	// на мгновение видны участники предыдущего.
	$effect(() => {
		void numericId;
		chat = null;
		members = [];
	});

	async function load() {
		if (!Number.isFinite(numericId)) return;
		loading = true;
		error = null;
		try {
			const [loadedChat, loadedMembers] = await Promise.all([
				api.chat(numericId),
				api.chatMembers(numericId)
			]);
			chat = loadedChat;
			members = loadedMembers;
			// Открыл чат — значит прочитал. Отметка монотонна на бэкенде,
			// поэтому повторный вызов с тем же seq безопасен.
			if (loadedChat.unread > 0) {
				const result = await api.markRead(numericId, loadedChat.last_seq);
				chat = { ...loadedChat, unread: result.unread, last_read_seq: result.last_read_seq };
			}
		} catch {
			error = 'Чат не найден или у вас нет доступа.';
		} finally {
			loading = false;
		}
	}

	async function invite(event: SubmitEvent) {
		event.preventDefault();
		inviteError = null;
		inviting = true;
		try {
			const member = await api.addChatMember(numericId, inviteName.trim());
			members = [...members, member];
			if (chat) chat = { ...chat, member_count: members.length };
			inviteName = '';
		} catch (err) {
			inviteError = err instanceof Error ? err.message : 'Не удалось добавить участника.';
		} finally {
			inviting = false;
		}
	}
</script>

<svelte:head>
	<title>{chat ? chatTitle(chat) : 'Чат'} — Messenger</title>
</svelte:head>

{#if !auth.ready}
	<p class="muted">Загрузка…</p>
{:else if !auth.isAuthenticated}
	<section class="card">
		<p>Чтобы открыть чат, войдите в аккаунт.</p>
		<a class="button" href="/login?next={page.url.pathname}">Войти</a>
	</section>
{:else if loading}
	<p class="muted">Загружаем чат…</p>
{:else if error}
	<section class="card">
		<p class="error">{error}</p>
		<a class="button ghost" href="/chats">К списку чатов</a>
	</section>
{:else if chat}
	<nav class="crumbs">
		<a href="/chats">← Чаты</a>
	</nav>

	<header class="head">
		<div>
			<h1>{chatTitle(chat)}</h1>
			<p class="sub">{chatSubtitle(chat)}</p>
		</div>
	</header>

	<section class="card placeholder">
		<p class="muted">
			Сообщений пока нет — их отправка появится на следующем этапе. Чат, участники и непрочитанные
			уже работают.
		</p>
	</section>

	{#if chat.type !== 'direct'}
		<section class="card">
			<h2>Участники</h2>
			<ul class="members">
				{#each members as member (member.user.id)}
					<li>
						<span class="name">{member.user.name}</span>
						<span class="muted">@{member.user.username}</span>
						{#if member.role !== 'member'}<span class="tag">{member.role}</span>{/if}
					</li>
				{/each}
			</ul>

			<form class="invite" onsubmit={invite}>
				<input bind:value={inviteName} placeholder="добавить по имени пользователя" />
				<button type="submit" class="button" disabled={inviting}>
					{inviting ? 'Добавляем…' : 'Добавить'}
				</button>
			</form>
			{#if inviteError}<p class="error">{inviteError}</p>{/if}
		</section>
	{/if}
{/if}

<style>
	.crumbs {
		margin-bottom: 12px;
		font-size: 14px;
	}

	.crumbs a {
		color: var(--text-muted);
	}

	.head {
		margin-bottom: 20px;
	}

	h1 {
		font-size: 22px;
		margin: 0 0 4px;
	}

	h2 {
		font-size: 15px;
		margin: 0 0 12px;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.sub {
		color: var(--text-muted);
		font-size: 14px;
		margin: 0;
	}

	.card {
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 20px;
		margin-bottom: 16px;
	}

	.placeholder {
		text-align: center;
		padding: 40px 20px;
	}

	.members {
		list-style: none;
		margin: 0 0 16px;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.members li {
		align-items: center;
		display: flex;
		gap: 8px;
		font-size: 14px;
	}

	.name {
		color: var(--text);
		font-weight: 600;
	}

	.tag {
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 999px;
		color: var(--text-muted);
		font-size: 11px;
		padding: 2px 8px;
	}

	.invite {
		display: flex;
		gap: 8px;
	}

	.invite input {
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text);
		flex: 1;
		font: inherit;
		padding: 8px 12px;
	}

	.invite input:focus {
		border-color: var(--accent);
		outline: none;
	}

	.button {
		background: var(--accent);
		border: none;
		border-radius: 8px;
		color: #fff;
		cursor: pointer;
		display: inline-block;
		font: inherit;
		font-size: 14px;
		font-weight: 600;
		padding: 8px 16px;
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

	.muted {
		color: var(--text-muted);
	}

	.error {
		color: var(--error);
		font-size: 14px;
	}
</style>
