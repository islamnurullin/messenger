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
