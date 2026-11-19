import { api } from '$lib/api/client';
import type { Message, MessagesPage } from '$lib/api/types';

/**
 * Лента одного чата.
 *
 * Держит сообщения в памяти целиком по возрастанию seq и умеет догружать
 * историю назад. Ключевое правило: **все вставки идут по seq**, а не по
 * порядку прихода. Событие из websocket может прийти раньше ответа REST
 * (или наоборот), и наивный `push` показал бы сообщения не по порядку.
 */
function createThread(chatId: number, initial: MessagesPage) {
	let messages = $state<Message[]>(initial.messages);
	let hasMore = $state(initial.has_more);
	let loadingMore = $state(false);

	function insert(message: Message): void {
		if (messages.some((m) => m.id === message.id)) return;

		// Бинарный поиск по seq: лента уже отсортирована, и вставка в середину
		// должна оставаться O(log n), а не O(n) на каждом событии.
		let low = 0;
		let high = messages.length;
		while (low < high) {
			const mid = (low + high) >> 1;
			if (messages[mid].seq < message.seq) low = mid + 1;
			else high = mid;
		}
		messages = [...messages.slice(0, low), message, ...messages.slice(low)];
	}

	async function loadOlder(): Promise<void> {
		if (!hasMore || loadingMore || messages.length === 0) return;
		loadingMore = true;
		try {
			const page = await api.messages(chatId, { before: messages[0].seq });
			const existing = new Set(messages.map((m) => m.id));
			const fresh = page.messages.filter((m) => !existing.has(m.id));
			messages = [...fresh, ...messages];
			hasMore = page.has_more;
		} finally {
			loadingMore = false;
		}
	}

	function replaceAll(page: MessagesPage): void {
		messages = page.messages;
		hasMore = page.has_more;
	}

	return {
		get messages() {
			return messages;
		},
		get hasMore() {
			return hasMore;
		},
		get loadingMore() {
			return loadingMore;
		},
		insert,
		loadOlder,
		replaceAll
	};
}

export type Thread = ReturnType<typeof createThread>;

export function openThread(chatId: number, initial: MessagesPage): Thread {
	return createThread(chatId, initial);
}
