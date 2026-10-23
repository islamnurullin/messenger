import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		// host: true — слушать и на 127.0.0.1, и на адресе в локальной сети.
		// По умолчанию Vite биндится только на localhost (::1), и запрос на
		// http://127.0.0.1:5173 отвергается — а именно этот адрес указан
		// в CORS-настройках Django. Плюс так можно открыть UI с телефона.
		host: true,
		port: 5173,
		strictPort: true
	},
	preview: {
		host: true,
		port: 5173
	}
});
