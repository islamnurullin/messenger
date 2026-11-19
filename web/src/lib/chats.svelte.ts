import { browser } from '$app/environment';
import { api } from '$lib/api/client';
import type { Chat } from '$lib/api/types';

/**
 * Список чатов. Svelte 5 runes в .svelte.ts — состояние общее на всё приложение,
 * поэтому список и новый чат видят одни и те же данные без ручной синхронизации.
 */
function createChats() {
	let items = $state<Chat[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let loaded = $state(false);

	async function load(force = false): Promise<void> {
		if (!browser) return;
		if (loaded && !force) return;
		loading = true;
		error = null;
		try {
			items = await api.chats();
			loaded = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Не удалось загрузить чаты';
		} finally {
			loading = false;
		}
	}

	/** Сбрасывает кэш — при выходе из аккаунта чужие чаты не должны остаться. */
	function reset(): void {
		items = [];
		loaded = false;
		error = null;
	}

	/** Подставляет свежие данные чата в список, не перезапрашивая весь список. */
	function upsert(chat: Chat): void {
		const index = items.findIndex((c) => c.id === chat.id);
		if (index === -1) {
			items = [chat, ...items];
		} else {
			items = items.map((c) => (c.id === chat.id ? chat : c));
		}
	}

	const totalUnread = $derived(items.reduce((sum, chat) => sum + chat.unread, 0));

	return {
		get items() {
			return items;
		},
		get loading() {
			return loading;
		},
		get error() {
			return error;
		},
		get totalUnread() {
			return totalUnread;
		},
		load,
		reset,
		upsert
	};
}

export const chats = createChats();

/** Как чат показывать в списке: у личного вместо названия — имя собеседника. */
export function chatTitle(chat: Chat): string {
	if (chat.type === 'direct') return chat.peer?.name ?? 'Диалог';
	return chat.title || 'Без названия';
}

export function chatSubtitle(chat: Chat): string {
	if (chat.type === 'direct') return '@' + (chat.peer?.username ?? '—');
	const noun = chat.type === 'channel' ? 'подписчик' : 'участник';
	return `${chat.member_count} ${plural(chat.member_count, noun, noun + 'а', noun + 'ов')}`;
}

/** Русская плюрализация: 1 участник, 2 участника, 5 участников. */
function plural(n: number, one: string, few: string, many: string): string {
	const mod100 = n % 100;
	const mod10 = n % 10;
	if (mod10 === 1 && mod100 !== 11) return one;
	if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
	return many;
}
