/** Ответ health-check — совпадает с apps/common/health.py на бэкенде. */
export type HealthStatus = 'ok' | 'degraded' | 'unavailable';

export interface ComponentCheck {
	status: 'ok' | 'error' | 'disabled';
	latency_ms?: number;
	error?: string;
	http_status?: number;
	cluster?: string;
}

export interface HealthResponse {
	status: HealthStatus;
	checks: Record<string, ComponentCheck>;
}

/** Профиль — совпадает с ProfileSerializer на бэкенде. */
export interface User {
	id: number;
	username: string;
	display_name: string;
	/** display_name, а если пусто — username. Считает бэкенд. */
	name: string;
	bio: string;
	avatar: string | null;
	created_at?: string;
	last_seen_at?: string | null;
}

/** Ответ /api/auth/register и /api/auth/login. */
export interface AuthResponse {
	user: User;
	access: string;
	refresh: string;
}

export type ChatType = 'direct' | 'group' | 'channel';
export type ChatRole = 'owner' | 'admin' | 'member';

/** Чат глазами участника — совпадает с ChatSerializer. */
export interface Chat {
	id: number;
	type: ChatType;
	title: string;
	/** Последний seq в чате: он же курсор пагинации и источник unread. */
	last_seq: number;
	/** last_seq - last_read_seq, считает бэкенд. */
	unread: number;
	last_read_seq: number;
	/** Собеседник личного чата; у групп и каналов null. */
	peer: User | null;
	member_count: number;
	created_at: string;
	updated_at: string;
}

export interface ChatMember {
	user: User;
	role: ChatRole;
	last_read_seq: number;
	joined_at: string;
}

export type CreateChatBody =
	| { type: 'direct'; username: string }
	| { type: 'group' | 'channel'; title: string; usernames?: string[] };

/** Сообщение — совпадает с MessageSerializer. */
export interface Message {
	id: number;
	/** Монотонный номер внутри чата: по нему сортировка и пагинация. */
	seq: number;
	sender: User | null;
	body: string;
	created_at: string;
}

/** Страница истории — совпадает с build_page_data. */
export interface MessagesPage {
	messages: Message[];
	has_more: boolean;
	oldest_seq: number | null;
	newest_seq: number | null;
}
