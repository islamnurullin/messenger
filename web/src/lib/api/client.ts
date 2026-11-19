import { browser } from '$app/environment';
import { API_URL } from '$lib/config';
import type {
	AuthResponse,
	Chat,
	ChatMember,
	CreateChatBody,
	HealthResponse,
	Message,
	MessagesPage,
	User
} from './types';

/** Ошибка API с кодом статуса: страницам нужно различать 401 и остальное. */
export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
		this.name = 'ApiError';
	}
}

const ACCESS_KEY = 'messenger.access';
const REFRESH_KEY = 'messenger.refresh';

/**
 * Токены живут в localStorage.
 *
 * Альтернатива — httpOnly-cookie: XSS её не читает, но тогда нужны CSRF-токены,
 * SameSite-настройка и прокси для кросс-доменных запросов на этапе разработки
 * (фронт на :5173, бэк на :8000). Для учебного проекта без пользовательского
 * HTML выигрыш не окупает сложность — решение записано в ADR 0004.
 */
export const tokens = {
	get access(): string | null {
		return browser ? localStorage.getItem(ACCESS_KEY) : null;
	},
	get refresh(): string | null {
		return browser ? localStorage.getItem(REFRESH_KEY) : null;
	},
	set(access: string, refresh: string): void {
		if (!browser) return;
		localStorage.setItem(ACCESS_KEY, access);
		localStorage.setItem(REFRESH_KEY, refresh);
		// Событие для синхронизации вкладок: выход в одной закрывает сессию везде.
		window.dispatchEvent(new CustomEvent('messenger:auth', { detail: { loggedIn: true } }));
	},
	clear(): void {
		if (!browser) return;
		localStorage.removeItem(ACCESS_KEY);
		localStorage.removeItem(REFRESH_KEY);
		window.dispatchEvent(new CustomEvent('messenger:auth', { detail: { loggedIn: false } }));
	}
};

async function parseError(response: Response): Promise<string> {
	try {
		const body = await response.json();
		const details = body?.error?.details;
		// Ошибки полей приходят словарём {"username": ["занято"]} — показываем
		// первую, иначе пользователь видит общее «Ошибка запроса».
		if (details && typeof details === 'object') {
			for (const value of Object.values(details)) {
				if (Array.isArray(value) && value.length > 0) return String(value[0]);
				if (typeof value === 'string') return value;
			}
		}
		return body?.error?.message ?? `HTTP ${response.status}`;
	} catch {
		return `HTTP ${response.status}`;
	}
}

let refreshing: Promise<boolean> | null = null;

/**
 * Обновляет access по refresh. Параллельные 401 ждут один общий запрос — иначе
 * десять запросов одновременно дёрнут refresh и часть получит отказ.
 */
async function refreshAccess(): Promise<boolean> {
	const refresh = tokens.refresh;
	if (!refresh) return false;

	refreshing ??= (async () => {
		try {
			const response = await fetch(`${API_URL}/api/auth/refresh`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ refresh })
			});
			if (!response.ok) {
				tokens.clear();
				return false;
			}
			const data = (await response.json()) as { access: string };
			tokens.set(data.access, refresh);
			return true;
		} catch {
			return false;
		} finally {
			refreshing = null;
		}
	})();

	return refreshing;
}

interface RequestOptions extends RequestInit {
	/** Не пытаться обновлять токен: для самих auth-запросов это бессмысленно. */
	skipAuthRetry?: boolean;
}

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
	const { skipAuthRetry, ...rest } = init;
	const isForm = rest.body instanceof FormData;
	const access = tokens.access;

	const send = (): Promise<Response> =>
		fetch(`${API_URL}${path}`, {
			...rest,
			headers: {
				...(isForm ? {} : { 'Content-Type': 'application/json' }),
				...(access ? { Authorization: `Bearer ${access}` } : {}),
				...(rest.headers ?? {})
			}
		});

	let response = await send();

	if (response.status === 401 && !skipAuthRetry && tokens.refresh) {
		if (await refreshAccess()) {
			response = await send();
		}
	}

	if (!response.ok) {
		throw new ApiError(await parseError(response), response.status);
	}

	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

export const api = {
	health: () => request<HealthResponse>('/api/health'),
	// skipAuthRetry: у неверного пароля ответ 400/401, обновлять там нечего.
	register: (body: { username: string; password: string; display_name?: string }) =>
		request<AuthResponse>('/api/auth/register', {
			method: 'POST',
			body: JSON.stringify(body),
			skipAuthRetry: true
		}),
	login: (body: { username: string; password: string }) =>
		request<AuthResponse>('/api/auth/login', {
			method: 'POST',
			body: JSON.stringify(body),
			skipAuthRetry: true
		}),
	me: () => request<User>('/api/me'),
	updateMe: (body: { display_name?: string; bio?: string; avatar?: File | null }) => {
		if (body.avatar instanceof File) {
			const form = new FormData();
			if (body.display_name !== undefined) form.append('display_name', body.display_name);
			if (body.bio !== undefined) form.append('bio', body.bio);
			form.append('avatar', body.avatar);
			return request<User>('/api/me', { method: 'PATCH', body: form });
		}
		return request<User>('/api/me', { method: 'PATCH', body: JSON.stringify(body) });
	},

	chats: () => request<Chat[]>('/api/chats'),
	// Бэкенд отвечает 201 при создании и 200, если личный чат уже есть:
	// повторное «написать пользователю» не должно выглядеть ошибкой.
	createChat: (body: CreateChatBody) =>
		request<Chat>('/api/chats', { method: 'POST', body: JSON.stringify(body) }),
	chat: (id: number) => request<Chat>(`/api/chats/${id}`),
	chatMembers: (id: number) => request<ChatMember[]>(`/api/chats/${id}/members`),
	addChatMember: (id: number, username: string) =>
		request<ChatMember>(`/api/chats/${id}/members`, {
			method: 'POST',
			body: JSON.stringify({ username })
		}),
	markRead: (id: number, lastReadSeq: number) =>
		request<{ last_read_seq: number; unread: number; updated: boolean }>(`/api/chats/${id}/read`, {
			method: 'POST',
			body: JSON.stringify({ last_read_seq: lastReadSeq })
		}),

	messages: (id: number, options: { before?: number; limit?: number } = {}) => {
		const params = new URLSearchParams();
		if (options.before !== undefined) params.set('before', String(options.before));
		if (options.limit !== undefined) params.set('limit', String(options.limit));
		const query = params.toString();
		return request<MessagesPage>(`/api/chats/${id}/messages${query ? `?${query}` : ''}`);
	},
	/**
	 * Отправка. client_msg_id генерирует клиент: без него ретрай после обрыва
	 * связи оставит в переписке два одинаковых сообщения.
	 */
	sendMessage: (id: number, body: string, clientMsgId: string) =>
		request<Message>(`/api/chats/${id}/messages`, {
			method: 'POST',
			body: JSON.stringify({ body, client_msg_id: clientMsgId })
		}),

	realtimeToken: () =>
		request<{ token: string; ws_url: string }>('/api/realtime/token', { method: 'POST' }),
	subscriptionToken: (channel: string) =>
		request<{ token: string }>('/api/realtime/subscribe', {
			method: 'POST',
			body: JSON.stringify({ channel })
		})
};
