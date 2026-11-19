<script lang="ts">
	import { goto } from '$app/navigation';
	import { ApiError } from '$lib/api/client';
	import { auth } from '$lib/auth.svelte';

	let displayName = $state('');
	let bio = $state('');
	let avatarFile = $state<File | null>(null);
	let preview = $state<string | null>(null);
	let error = $state<string | null>(null);
	let saved = $state(false);
	let submitting = $state(false);
	// Показываем состояние из auth только до первого редактирования, иначе
	// $effect будет перетирать ввод пользователя при каждом обновлении store.
	let touched = $state(false);

	$effect(() => {
		if (!touched && auth.user) {
			displayName = auth.user.display_name;
			bio = auth.user.bio;
		}
	});

	function onAvatarChange(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0] ?? null;
		avatarFile = file;
		if (preview) URL.revokeObjectURL(preview);
		preview = file ? URL.createObjectURL(file) : null;
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		error = null;
		saved = false;
		submitting = true;
		try {
			await auth.updateProfile({
				display_name: displayName.trim(),
				bio: bio.trim(),
				avatar: avatarFile
			});
			avatarFile = null;
			saved = true;
			touched = false;
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Не удалось сохранить профиль.';
		} finally {
			submitting = false;
		}
	}

	async function signOut() {
		auth.logout();
		await goto('/login', { replaceState: true });
	}
</script>

<svelte:head>
	<title>Профиль — Messenger</title>
</svelte:head>

{#if !auth.ready}
	<p class="muted">Загрузка…</p>
{:else if !auth.isAuthenticated || !auth.user}
	<section class="card">
		<h1>Профиль</h1>
		<p class="muted">Чтобы открыть профиль, войдите в аккаунт.</p>
		<p><a href="/login?next=/profile">Войти</a></p>
	</section>
{:else}
	<section class="card">
		<h1>Профиль</h1>
		<p class="muted">
			Вы вошли как <code>{auth.user.username}</code>
		</p>

		{#if error}
			<p class="error" role="alert">{error}</p>
		{/if}
		{#if saved}
			<p class="ok" role="status">Профиль сохранён</p>
		{/if}

		<form onsubmit={submit}>
			<div class="avatar-row">
				{#if preview ?? auth.user.avatar}
					<img src={preview ?? auth.user.avatar ?? ''} alt="Аватар" width="72" height="72" />
				{:else}
					<div class="avatar-empty">{auth.user.name.slice(0, 1).toUpperCase()}</div>
				{/if}
				<label class="file">
					Аватар
					<input
						type="file"
						accept="image/jpeg,image/png,image/webp"
						onchange={onAvatarChange}
						disabled={submitting}
					/>
					<span class="hint">JPEG, PNG или WebP. Обрезается до квадрата 256×256.</span>
				</label>
			</div>

			<label>
				Отображаемое имя
				<input
					maxlength="64"
					bind:value={displayName}
					oninput={() => (touched = true)}
					disabled={submitting}
				/>
			</label>

			<label>
				О себе
				<textarea
					rows="3"
					maxlength="255"
					bind:value={bio}
					oninput={() => (touched = true)}
					disabled={submitting}
				></textarea>
			</label>

			<div class="actions">
				<button type="submit" disabled={submitting}>
					{submitting ? 'Сохраняем…' : 'Сохранить'}
				</button>
				<button type="button" class="ghost" onclick={signOut}>Выйти из аккаунта</button>
			</div>
		</form>
	</section>
{/if}

<style>
	.card {
		max-width: 440px;
		margin: 24px auto 0;
	}

	h1 {
		font-size: 24px;
		margin: 0 0 6px;
	}

	.muted {
		color: var(--text-muted);
		font-size: 14px;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 16px;
		margin-top: 22px;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 13px;
		color: var(--text-muted);
	}

	input:not([type='file']),
	textarea {
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text);
		font: inherit;
		padding: 9px 12px;
		resize: vertical;
	}

	input:focus,
	textarea:focus {
		border-color: var(--accent);
		outline: none;
	}

	.avatar-row {
		align-items: center;
		display: flex;
		gap: 16px;
	}

	img {
		border-radius: 50%;
		object-fit: cover;
	}

	.avatar-empty {
		align-items: center;
		background: var(--bg-elevated);
		border: 1px solid var(--border);
		border-radius: 50%;
		color: var(--text-muted);
		display: flex;
		font-size: 26px;
		height: 72px;
		justify-content: center;
		width: 72px;
	}

	.file {
		flex: 1;
	}

	.file input {
		color: var(--text-muted);
		font-size: 13px;
	}

	.hint {
		color: var(--text-muted);
		font-size: 12px;
	}

	.actions {
		display: flex;
		gap: 10px;
		margin-top: 4px;
	}

	button {
		background: var(--accent);
		border: 0;
		border-radius: 8px;
		color: #fff;
		cursor: pointer;
		font: inherit;
		font-weight: 600;
		padding: 10px 18px;
	}

	button.ghost {
		background: transparent;
		border: 1px solid var(--border);
		color: var(--text-muted);
		font-weight: 400;
	}

	button.ghost:hover {
		border-color: var(--text-muted);
		color: var(--text);
	}

	button:disabled {
		cursor: default;
		opacity: 0.6;
	}

	.error,
	.ok {
		border-radius: 8px;
		font-size: 14px;
		padding: 10px 12px;
	}

	.error {
		background: rgb(248 81 73 / 12%);
		border: 1px solid rgb(248 81 73 / 40%);
		color: var(--error);
	}

	.ok {
		background: rgb(63 185 80 / 12%);
		border: 1px solid rgb(63 185 80 / 40%);
		color: var(--ok);
	}
</style>
