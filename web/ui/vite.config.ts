import tailwindcss from '@tailwindcss/vite';
import Icons from 'unplugin-icons/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), Icons({ compiler: 'svelte', autoInstall: true }), sveltekit()],
	server: {
		proxy: {
			'/api': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/config': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/profiles': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/devices': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/roots': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/colormaps': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/session': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/metadata': {
				target: 'http://localhost:8000',
				changeOrigin: true
			},
			'/ws': {
				target: 'http://localhost:8000',
				ws: true,
				changeOrigin: true
			}
		}
	}
});
