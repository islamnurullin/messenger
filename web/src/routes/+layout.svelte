<script lang="ts">
	import type { Snippet } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { auth } from '$lib/auth.svelte';
	import { chats } from '$lib/chats.svelte';
	import '../app.css';

	let { children }: { children: Snippet } = $props();

	const navItems = [
		{ href: '/', label: 'Обзор' },
		{ href: '/chats', label: 'Чаты' },
		{ href: '/status', label: 'Состояние' }
	];

	// Один раз при загрузке приложения: если в localStorage есть токен,
	// подтягиваем профиль. SSR это не делает — там нет localStorage.
	$effect(() => {
		void auth.load();
	});

	// Выход уводит на страницу входа: остаться на /profile с «войдите в аккаунт»
	// выглядит как поломка, хотя технически всё верно.
	async function signOut() {
		auth.logout();
		chats.reset();
		await goto('/login', { replaceState: true });
	}
</script>

<header>
	<nav>
		<strong>Messenger</strong>
		{#each navItems as item (item.href)}
			{@const active =
				item.href === '/'
					? page.url.pathname === '/'
					: page.url.pathname === item.href || page.url.pathname.startsWith(item.href + '/')}
			<a href={item.href} class:active>{item.label}</a>
		{/each}

		<span class="spacer"></span>

		{#if auth.isAuthenticated && auth.user}
			<a href="/profile" class="who" class:active={page.url.pathname === '/profile'}>
				{auth.user.name}
			</a>
			<button type="button" onclick={signOut}>Выйти</button>
		{:else if auth.ready}
			<a href="/login" class:active={page.url.pathname === '/login'}>Войти</a>
			<a href="/register" class="cta" class:active={page.url.pathname === '/register'}>
				Регистрация
			</a>
		{/if}
	</nav>
</header>

<main>
	{@render children()}
</main>

<style>
	header {
		border-bottom: 1px solid var(--border);
		background: var(--bg-elevated);
		position: sticky;
		top: 0;
		z-index: 10;
	}

	nav {
		max-width: 960px;
		margin: 0 auto;
		padding: 14px 20px;
		display: flex;
		align-items: center;
		gap: 20px;
	}

	nav strong {
		margin-right: 8px;
		color: var(--accent);
		letter-spacing: 0.02em;
	}

	nav a {
		color: var(--text-muted);
		font-size: 14px;
	}

	nav a:hover {
		color: var(--text);
		text-decoration: none;
	}

	nav a.active {
		color: var(--text);
		font-weight: 600;
	}

	.spacer {
		flex: 1;
	}

	.who {
		color: var(--text) !important;
		font-weight: 600;
	}

	nav button {
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text-muted);
		cursor: pointer;
		font: inherit;
		font-size: 13px;
		padding: 5px 12px;
	}

	nav button:hover {
		color: var(--text);
		border-color: var(--text-muted);
	}

	nav a.cta {
		background: var(--accent);
		color: #fff;
		border-radius: 8px;
		padding: 5px 12px;
	}

	nav a.cta:hover {
		filter: brightness(1.1);
		text-decoration: none;
	}

	main {
		max-width: 960px;
		margin: 0 auto;
		padding: 32px 20px 64px;
	}
</style>
