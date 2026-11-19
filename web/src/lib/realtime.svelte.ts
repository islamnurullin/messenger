import { browser } from '$app/environment';
import { Centrifuge } from 'centrifuge';
import { api } from '$lib/api/client';

/**
 * Одно websocket-соединение с Centrifugo на всё приложение.
 *
 * Центральная мысль: realtime — ускорение, а не источник правды. Сообщение
 * сначала пишется в Postgres через REST, и только потом приходит сюда. Поэтому
 * при любом расхождении (пропуск, разрыв, повтор) правильная стратегия —
 * перезапросить историю, а не досочинять её из событий.
 *
 * Подключение ленивое: открывается при первом входе в чат, закрывается при
 * выходе из аккаунта. Держать сокет открытым на странице логина незачем.
 */

type MessageHandler = (chatId: number, message: unknown) => void;
type ChatEventHandler = (event: { type: string; chat_id: number; [key: string]: unknown }) => void;

function createRealtime() {
	let client: Centrifuge | null = null;
	let connecting: Promise<boolean> | null = null;
	let connected = $state(false);
	let lastError = $state<string | null>(null);

	const messageHandlers = new Set<MessageHandler>();
	const chatHandlers = new Set<ChatEventHandler>();
	/** Куда мы подписаны: channel -> объект подписки. */
	const subscriptions = new Map<string, ReturnType<Centrifuge['newSubscription']>>();

	async function connect(): Promise<boolean> {
		if (!browser) return false;
		if (client) return true;
		// Параллельные вызовы (список чатов и открытый диалог) должны получить
		// одно и то же соединение, а не два сокета.
		if (connecting) return connecting;

		connecting = (async () => {
			try {
				const { token, ws_url } = await api.realtimeToken();
				client = new Centrifuge(ws_url, {
					token,
					// Centrifuge зовёт getToken, когда токен истёк или соединение
					// переподключилось: токен живёт час, а вкладка может висеть сутками.
					getToken: async () => {
						const fresh = await api.realtimeToken();
						return fresh.token;
					}
				});

				client.on('connected', () => {
					connected = true;
					lastError = null;
				});
				client.on('disconnected', () => {
					connected = false;
				});
				client.on('error', (ctx) => {
					// Не показываем ошибку сразу: Centrifuge сам переподключается,
					// и мигающее «нет связи» раздражает больше, чем помогает.
					lastError = ctx?.error?.message ?? 'Нет соединения в реальном времени';
				});

				client.connect();
				return true;
			} catch (e) {
				lastError = e instanceof Error ? e.message : 'Не удалось подключиться к realtime';
				client = null;
				return false;
			}
		})();

		const result = await connecting;
		connecting = null;
		return result;
	}

	/**
	 * Подписка на канал. Токен выдаёт бэкенд — он же проверяет, что пользователь
	 * состоит в чате. Без этого любой мог бы слушать чужую переписку.
	 */
	async function subscribe(channel: string): Promise<void> {
		if (!browser) return;
		if (subscriptions.has(channel)) return;
		if (!(await connect()) || !client) return;

		const subscription = client.newSubscription(channel, {
			getToken: () => fetchSubscriptionToken(channel)
		});

		subscription.on('publication', (ctx) => {
			const data = ctx.data as Record<string, unknown> | null;
			if (!data) return;

			if (data.type === 'message' && data.message) {
				const chatId = Number(channel.split(':')[1]);
				for (const handler of messageHandlers) {
					handler(chatId, data.message);
				}
				return;
			}

			// Прочие события (новый чат, приглашение) — в общий обработчик.
			for (const handler of chatHandlers) {
				handler(data as { type: string; chat_id: number });
			}
		});

		subscription.subscribe();
		subscriptions.set(channel, subscription);
	}

	/**
	 * Токен подписки запрашивается при каждом подключении заново: он живёт час,
	 * а вкладка может висеть сутками. Centrifuge зовёт этот колбэк сам, когда
	 * токен истёк или соединение переподключилось.
	 */
	async function fetchSubscriptionToken(channel: string): Promise<string> {
		const { token } = await api.subscriptionToken(channel);
		return token;
	}

	function unsubscribe(channel: string): void {
		const subscription = subscriptions.get(channel);
		if (!subscription) return;
		subscription.unsubscribe();
		subscriptions.delete(channel);
	}

	/** Отписка от всех каналов, кроме личного канала пользователя. */
	function leaveChats(): void {
		for (const channel of [...subscriptions.keys()]) {
			if (channel.startsWith('chat:')) unsubscribe(channel);
		}
	}

	function disconnect(): void {
		leaveChats();
		for (const channel of [...subscriptions.keys()]) unsubscribe(channel);
		client?.disconnect();
		client = null;
		connected = false;
	}

	function onMessage(handler: MessageHandler): () => void {
		messageHandlers.add(handler);
		return () => messageHandlers.delete(handler);
	}

	function onChatEvent(handler: ChatEventHandler): () => void {
		chatHandlers.add(handler);
		return () => chatHandlers.delete(handler);
	}

	return {
		get connected() {
			return connected;
		},
		get lastError() {
			return lastError;
		},
		connect,
		subscribe,
		unsubscribe,
		leaveChats,
		disconnect,
		onMessage,
		onChatEvent
	};
}

export const realtime = createRealtime();
