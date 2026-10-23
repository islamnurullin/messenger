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
