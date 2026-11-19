<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError } from '$lib/api/client';
	import { auth } from '$lib/auth.svelte';

	let username = $state('');
	let password = $state('');
	let error = $state<string | null>(null);
	let submitting = $state(false);

	// Куда вернуться после входа: middleware кладёт сюда исходный путь.
	const redirectTo = $derived(page.url.searchParams.get('next') ?? '/profile');

	// Уже вошедшему форма входа не нужна — уводим туда, куда он шёл.
	// Проверяем auth.ready, иначе на первом рендере user ещё null и редиректа не будет.
	$effect(() => {
		if (auth.ready && auth.isAuthenticated && page.url.pathname === '/login') {
			void goto(redirectTo, { replaceState: true });
		}
	});

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = null;
		submitting = true;
		try {
			await auth.login(username.trim(), password);
			await goto(redirectTo, { replaceState: true });
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Не удалось войти. Повторите попытку.';
		} finally {
			submitting = false;
		}
	}
</script>

<svelte:head>
	<title>Вход — Messenger</title>
</svelte:head>

<section class="card">
	<h1>Вход</h1>
	<p class="lead">Используйте имя пользователя и пароль, указанные при регистрации.</p>

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
				bind:value={username}
				disabled={submitting}
			/>
		</label>

		<label>
			Пароль
			<input
				name="password"
				type="password"
				autocomplete="current-password"
				required
				bind:value={password}
				disabled={submitting}
			/>
		</label>

		<button type="submit" disabled={submitting}>
			{submitting ? 'Входим…' : 'Войти'}
		</button>
	</form>

	<p class="alt">Нет учётной записи? <a href="/register">Зарегистрироваться</a></p>
</section>

<style>
	.card {
		max-width: 380px;
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
