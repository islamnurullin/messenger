<script lang="ts">
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import '../app.css';

	let { children }: { children: Snippet } = $props();

	const navItems = [
		{ href: '/', label: 'Обзор' },
		{ href: '/status', label: 'Состояние' }
	];
</script>

<header>
	<nav>
		<strong>Messenger</strong>
		{#each navItems as item (item.href)}
			<a href={item.href} class:active={page.url.pathname === item.href}>{item.label}</a>
		{/each}
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

	main {
		max-width: 960px;
		margin: 0 auto;
		padding: 32px 20px 64px;
	}
</style>
