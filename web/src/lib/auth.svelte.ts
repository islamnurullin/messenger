import { browser } from '$app/environment';
import { api, tokens } from '$lib/api/client';
import type { User } from '$lib/api/types';

/**
 * Состояние сессии. Svelte 5 runes в .svelte.ts — общий модуль на всё приложение:
 * шапка, страницы и защита маршрутов читают одно и то же.
 */
function createAuth() {
	let user = $state<User | null>(null);
	let loading = $state(false);
	// Инициализация ленивая: на сервере localStorage нет, а SSR не должен падать.
	let ready = $state(!browser);

	async function load(): Promise<void> {
		if (!browser) return;
		if (!tokens.access && !tokens.refresh) {
			ready = true;
			return;
		}
		loading = true;
		try {
			user = await api.me();
		} catch {
			// Токен протух и обновить не удалось — клиент уже почистил хранилище.
			user = null;
		} finally {
			loading = false;
			ready = true;
		}
	}

	function apply(next: { user: User; access: string; refresh: string }): void {
		tokens.set(next.access, next.refresh);
		user = next.user;
		ready = true;
	}

	async function login(username: string, password: string): Promise<void> {
		apply(await api.login({ username, password }));
	}

	async function register(username: string, password: string, displayName: string): Promise<void> {
		apply(await api.register({ username, password, display_name: displayName }));
	}

	function logout(): void {
		tokens.clear();
		user = null;
	}

	async function updateProfile(patch: {
		display_name?: string;
		bio?: string;
		avatar?: File | null;
	}): Promise<void> {
		user = await api.updateMe(patch);
	}

	return {
		get user() {
			return user;
		},
		get isAuthenticated() {
			return user !== null;
		},
		get loading() {
			return loading;
		},
		get ready() {
			return ready;
		},
		load,
		login,
		register,
		logout,
		updateProfile
	};
}

export const auth = createAuth();
