import tailwindcss from '@tailwindcss/vite';
import Icons from 'unplugin-icons/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, process.cwd(), '');
	const apiTarget = env.VITE_API_URL || 'http://localhost:8000';

	const proxy: Record<string, object> = {};
	for (const path of ['/api', '/config', '/profiles', '/devices', '/roots', '/colormaps', '/session', '/metadata']) {
		proxy[path] = { target: apiTarget, changeOrigin: true };
	}
	// WS proxy disabled — bun's runtime doesn't support http-proxy WebSocket upgrades
	// proxy['/ws'] = { target: apiTarget, ws: true, changeOrigin: true };

	return {
		plugins: [tailwindcss(), Icons({ compiler: 'svelte', autoInstall: true }), sveltekit()],
		server: { proxy }
	};
});
