<script lang="ts">
	import { page } from '$app/state';
	import { api } from '$lib/api/client';
	import type { Chat, ChatMember, Message } from '$lib/api/types';
	import { auth } from '$lib/auth.svelte';
	import { chatSubtitle, chatTitle } from '$lib/chats.svelte';
	import { realtime } from '$lib/realtime.svelte';
	import { openThread, type Thread } from '$lib/thread.svelte';

	// Параметры маршрута в +page.svelte не приходят пропсами — SvelteKit отдаёт
	// их только через page.params. Из-за этого id был undefined, Number(undefined)
	// давал NaN, и страница навсегда застревала на «Загружаем чат…».
	const numericId = $derived(Number(page.params.id));

	let chat = $state<Chat | null>(null);
	let members = $state<ChatMember[]>([]);
	let thread = $state<Thread | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let inviteName = $state('');
	let inviteError = $state<string | null>(null);
	let inviting = $state(false);

	let draft = $state('');
	let sending = $state(false);
	let sendError = $state<string | null>(null);
	let scroller = $state<HTMLDivElement | null>(null);

	$effect(() => {
		if (!auth.ready || !auth.isAuthenticated) return;
		void load();
	});

	// Сбрасываем состояние при переходе между чатами, иначе на новом чате
	// на мгновение видны сообщения предыдущего.
	$effect(() => {
		void numericId;
		chat = null;
		members = [];
		thread = null;
		draft = '';
		sendError = null;
	});

	// Приходящие сообщения: вставляем по seq, а не по порядку доставки.
	$effect(() => {
		return realtime.onMessage((chatId, payload) => {
			if (chatId !== numericId || !thread) return;
			const message = payload as Message;
			thread.insert(message);
			scrollToBottom();
			// Открытый чат — прочитанный: отмечаем, иначе счётчик растёт вхолостую.
			if (message.sender?.id !== auth.user?.id && chat) {
				void api.markRead(numericId, message.seq);
			}
		});
	});

	async function load() {
		if (!Number.isFinite(numericId)) return;
		loading = true;
		error = null;
		try {
			const [loadedChat, loadedMembers, page] = await Promise.all([
				api.chat(numericId),
				api.chatMembers(numericId),
				api.messages(numericId)
			]);
			chat = loadedChat;
			members = loadedMembers;
			thread = openThread(numericId, page);

			// Отправка и приём идут через websocket, но история — через REST.
			// Подписка нужна до первого сообщения, поэтому не ждём её: чат
			// должен открыться, даже если realtime недоступен.
			void realtime.subscribe(`chat:${numericId}`);

			if (loadedChat.unread > 0) {
				const result = await api.markRead(numericId, loadedChat.last_seq);
				chat = { ...loadedChat, unread: result.unread, last_read_seq: result.last_read_seq };
			}
			scrollToBottom();
		} catch {
			error = 'Чат не найден или у вас нет доступа.';
		} finally {
			loading = false;
		}
	}

	function scrollToBottom(): void {
		// requestAnimationFrame, а не setTimeout: ждём кадр, в котором DOM уже
		// содержит новое сообщение, иначе scrollHeight ещё старый.
		requestAnimationFrame(() => {
			if (scroller) scroller.scrollTop = scroller.scrollHeight;
		});
	}

	async function loadOlder() {
		if (!thread) return;
		const element = scroller;
		const previousHeight = element?.scrollHeight ?? 0;
		await thread.loadOlder();
		// После подгрузки сохраняем позицию чтения: без этого браузер оставляет
		// scrollTop прежним, и пользователя уносит к началу истории.
		requestAnimationFrame(() => {
			if (!element) return;
			element.scrollTop = element.scrollHeight - previousHeight;
		});
	}

	async function send(event: SubmitEvent) {
		event.preventDefault();
		const text = draft.trim();
		if (!text || !thread || sending) return;

		sending = true;
		sendError = null;
		const clientId = crypto.randomUUID();
		try {
			const message = await api.sendMessage(numericId, text, clientId);
			thread.insert(message);
			draft = '';
			scrollToBottom();
			// Если websocket жив, сообщение придёт и оттуда — insert отбросит
			// дубль по id. Если мёртв, оно уже здесь: лента не зависит от realtime.
			if (chat && message.seq > chat.last_seq) {
				chat = { ...chat, last_seq: message.seq, last_read_seq: message.seq };
			}
		} catch (err) {
			// Текст не очищаем: пользователь не должен набирать заново.
			sendError = err instanceof Error ? err.message : 'Не удалось отправить сообщение.';
		} finally {
			sending = false;
		}
	}

	function onKeydown(event: KeyboardEvent) {
		// Enter отправляет, Shift+Enter переносит строку — привычное поведение.
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			void send(new SubmitEvent('submit'));
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

	function fmtTime(iso: string): string {
		const date = new Date(iso);
		return date.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
	}

	function fmtDay(iso: string): string {
		const date = new Date(iso);
		const today = new Date();
		const sameDay =
			date.getFullYear() === today.getFullYear() &&
			date.getMonth() === today.getMonth() &&
			date.getDate() === today.getDate();
		if (sameDay) return 'Сегодня';
		return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
	}

	function showDay(index: number): boolean {
		if (!thread) return false;
		if (index === 0) return true;
		const current = thread.messages[index];
		const previous = thread.messages[index - 1];
		return fmtDay(current.created_at) !== fmtDay(previous.created_at);
	}

	function isMine(message: Message): boolean {
		return message.sender?.id === auth.user?.id;
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
{:else if chat && thread}
	<nav class="crumbs">
		<a href="/chats">← Чаты</a>
		{#if !realtime.connected}
			<span class="offline" title="Сообщения придут при обновлении страницы">нет связи</span>
		{/if}
	</nav>

	<header class="head">
		<div>
			<h1>{chatTitle(chat)}</h1>
			<p class="sub">{chatSubtitle(chat)}</p>
		</div>
	</header>

	<section class="card feed">
		<div class="scroller" bind:this={scroller}>
			{#if thread.hasMore}
				<button class="load-more" onclick={loadOlder} disabled={thread.loadingMore}>
					{thread.loadingMore ? 'Загружаем…' : 'Загрузить историю'}
				</button>
			{/if}

			{#if thread.messages.length === 0}
				<p class="empty">Здесь пока пусто. Напишите первое сообщение.</p>
			{/if}

			{#each thread.messages as message, index (message.id)}
				{#if showDay(index)}
					<div class="day"><span>{fmtDay(message.created_at)}</span></div>
				{/if}
				<article class="message" class:mine={isMine(message)}>
					{#if !isMine(message)}
						<span class="author">{message.sender?.name ?? 'Пользователь'}</span>
					{/if}
					<p class="text">{message.body}</p>
					<span class="time">{fmtTime(message.created_at)}</span>
				</article>
			{/each}
		</div>

		<form class="composer" onsubmit={send}>
			<textarea
				bind:value={draft}
				onkeydown={onKeydown}
				placeholder="Написать сообщение…"
				rows="1"
				maxlength="4096"
			></textarea>
			<button type="submit" class="button" disabled={sending || !draft.trim()}>
				{sending ? 'Отправляем…' : 'Отправить'}
			</button>
		</form>
		{#if sendError}<p class="error">{sendError}</p>{/if}
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
		display: flex;
		gap: 12px;
		align-items: center;
	}

	.crumbs a {
		color: var(--text-muted);
	}

	.offline {
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 999px;
		color: var(--warn);
		font-size: 11px;
		padding: 2px 8px;
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

	.feed {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 12px;
	}

	.scroller {
		display: flex;
		flex-direction: column;
		gap: 8px;
		max-height: 60vh;
		overflow-y: auto;
		padding: 4px;
	}

	.empty {
		color: var(--text-muted);
		margin: 24px 0;
		text-align: center;
	}

	.load-more {
		align-self: center;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text-muted);
		cursor: pointer;
		font: inherit;
		font-size: 13px;
		padding: 6px 14px;
	}

	.day {
		align-self: center;
		color: var(--text-muted);
		font-size: 11px;
		margin: 8px 0;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.day span {
		background: var(--bg);
		border-radius: 999px;
		padding: 2px 10px;
	}

	.message {
		align-self: flex-start;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 12px;
		max-width: 78%;
		padding: 8px 12px;
	}

	.message.mine {
		align-self: flex-end;
		background: var(--accent);
		border-color: transparent;
	}

	.author {
		color: var(--accent);
		display: block;
		font-size: 12px;
		font-weight: 600;
		margin-bottom: 2px;
	}

	.mine .author {
		color: #fff;
	}

	.text {
		margin: 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.mine .text {
		color: #fff;
	}

	.time {
		color: var(--text-muted);
		display: block;
		font-size: 10px;
		margin-top: 4px;
		text-align: right;
	}

	.mine .time {
		color: rgba(255, 255, 255, 0.75);
	}

	.composer {
		display: flex;
		gap: 8px;
		align-items: flex-end;
	}

	.composer textarea {
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text);
		flex: 1;
		font: inherit;
		max-height: 140px;
		min-height: 40px;
		padding: 9px 12px;
		resize: vertical;
	}

	.composer textarea:focus {
		border-color: var(--accent);
		outline: none;
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
