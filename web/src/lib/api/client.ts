import { API_URL } from '$lib/config';
import type { HealthResponse } from './types';

/**
 * Тонкий клиент API. Никакой логики, кроме запросов и разбора ошибок —
 * авторизация и кэш появятся на этапе 2.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
	const response = await fetch(`${API_URL}${path}`, {
		...init,
		headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) }
	});

	if (!response.ok) {
		let message = `HTTP ${response.status}`;
		try {
			const body = await response.json();
			message = body?.error?.message ?? message;
		} catch {
			// тело не JSON — оставляем код статуса
		}
		throw new Error(message);
	}

	return (await response.json()) as T;
}

export const api = {
	health: () => request<HealthResponse>('/api/health')
};
