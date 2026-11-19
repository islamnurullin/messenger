<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api/client';
	import { auth } from '$lib/auth.svelte';

	let username = $state('');
	let displayName = $state('');
	let password = $state('');
	let confirm = $state('');
	let error = $state<string | null>(null);
	let submitting = $state(false);

	// Уже вошедшему регистрация не нужна.
	$effect(() => {
		if (auth.ready && auth.isAuthenticated && page.url.pathname === '/register') {
			void goto('/profile', { replaceState: true });
		}
	});

	// Те же правила, что в RegisterSerializer: латиница, цифры, подчёркивание.
	const USERNAME_RE = /^[A-Za-z0-9_]{3,32}$/;

	const usernameHint = $derived(
		username.length === 0 || USERNAME_RE.test(username)
			? null
			: 'От 3 до 32 символов: латиница, цифры, подчёркивание'
	);
	const mismatch = $derived(confirm.length > 0 && confirm !== password);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = null;
		if (mismatch) return;
		submitting = true;
		try {
			await auth.register(username.trim(), password, displayName.trim());
			await goto('/profile', { replaceState: true });
		} catch (err) {
			error =
				err instanceof ApiError ? err.message : 'Не удалось зарегистрироваться. Повторите позже.';
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Регистрация — Messenger</title>
</svelte:head>

<section class="card">
	<h1>Регистрация</h1>
	<p class="lead">Имя пользователя понадобится для входа, поменять его потом нельзя.</p>

	{#if error}
		<p class="error" role="alert">{error}</p>
	{/if}

	<form onsubmit={submit}>
		<label>
			Имя пользователя
			<input
				name="username"
				autocomplete="username"
				required
				minlength="3"
				maxlength="32"
				bind:value={username}
				disabled={submitting}
			/>
			{#if usernameHint}
				<span class="hint warn">{usernameHint}</span>
			{:else}
				<span class="hint">Латиница, цифры и _. Например: islam_n</span>
			{/if}
		</label>

		<label>
			Отображаемое имя
			<input name="display_name" maxlength="64" bind:value={displayName} disabled={submitting} />
			<span class="hint">Необязательно. Так вас увидят в чатах.</span>
		</label>

		<label>
			Пароль
			<input
				name="password"
				type="password"
				autocomplete="new-password"
				required
				minlength="8"
				bind:value={password}
				disabled={submitting}
			/>
			<span class="hint">Не короче 8 символов, не из списка частых.</span>
		</label>

		<label>
			Повторите пароль
			<input
				name="confirm"
				type="password"
				autocomplete="new-password"
				required
				bind:value={confirm}
				disabled={submitting}
			/>
			{#if mismatch}
				<span class="hint warn">Пароли не совпадают</span>
			{/if}
		</label>

		<button type="submit" disabled={submitting || mismatch}>
			{submitting ? 'Создаём…' : 'Создать аккаунт'}
		</button>
	</form>

	<p class="alt">Уже есть учётная запись? <a href="/login">Войти</a></p>
</section>

<style>
	.card {
		max-width: 400px;
		margin: 24px auto 0;
	}

	h1 {
		font-size: 24px;
		margin: 0 0 6px;
	}

	.lead {
		color: var(--text-muted);
		font-size: 14px;
		margin: 0 0 22px;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 13px;
		color: var(--text-muted);
	}

	input {
		background: var(--bg-elevated);
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
		font-size: 12px;
		color: var(--text-muted);
	}

	.hint.warn {
		color: var(--warn);
	}

	button {
		background: var(--accent);
		border: 0;
		border-radius: 8px;
		color: #fff;
		cursor: pointer;
		font: inherit;
		font-weight: 600;
		margin-top: 4px;
		padding: 10px;
	}

	button:disabled {
		cursor: default;
		opacity: 0.6;
	}

	.error {
		background: rgb(248 81 73 / 12%);
		border: 1px solid rgb(248 81 73 / 40%);
		border-radius: 8px;
		color: var(--error);
		font-size: 14px;
		margin: 0 0 18px;
		padding: 10px 12px;
	}

	.alt {
		color: var(--text-muted);
		font-size: 14px;
		margin: 20px 0 0;
		text-align: center;
	}
</style>
