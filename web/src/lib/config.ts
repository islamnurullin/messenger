import { browser } from '$app/environment';

/** Базовый URL REST API. В dev-режиме — локальный Django. */
export const API_URL: string =
	(browser && (window as unknown as { __API_URL__?: string }).__API_URL__) ||
	import.meta.env.PUBLIC_API_URL ||
	'http://127.0.0.1:8000';

/** Адрес WebSocket Centrifugo. */
export const CENTRIFUGO_WS_URL: string =
	import.meta.env.PUBLIC_CENTRIFUGO_WS_URL || 'ws://127.0.0.1:8001/connection/websocket';
