<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const paneDividerVariants = tv({
		slots: {
			separator: [
				'absolute flex items-center justify-center gap-2',
				'transition-all duration-300',
				'text-zinc-800 hover:text-zinc-600'
			],
			line: 'grow bg-current opacity-[0.85]'
		},
		variants: {
			direction: {
				vertical: {
					separator: 'w-3 flex-col left-1/2 top-0 bottom-0 -translate-x-1/2',
					line: 'w-[1px]'
				},
				horizontal: {
					separator: 'h-3 flex-row top-1/2 left-0 right-0 -translate-y-1/2',
					line: 'h-[1px]'
				}
			}
		},
		defaultVariants: {
			direction: 'vertical'
		}
	});

	export type PaneDividerVariants = VariantProps<typeof paneDividerVariants>;
</script>

<script lang="ts">
	import { PaneResizer } from 'paneforge';

	interface Props extends PaneDividerVariants {
		class?: string;
	}

	let { direction = 'vertical', class: className = '' }: Props = $props();

	const styles = $derived(paneDividerVariants({ direction }));
</script>

<PaneResizer class="relative z-50">
	<div class={styles.separator({ class: className })}>
		<div class={styles.line()}></div>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			width="1.2em"
			height="1.2em"
			viewBox="0 0 15 15"
			fill-rule="evenodd"
			fill="currentColor"
			clip-rule="evenodd"
		>
			{#if direction === 'vertical'}
				<path
					d="M8.625 2.5a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0m0 5a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0M7.5 13.625a1.125 1.125 0 1 0 0-2.25a1.125 1.125 0 0 0 0 2.25"
				/>
			{:else}
				<path
					d="M3.625 7.5a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0m5 0a1.125 1.125 0 1 1-2.25 0a1.125 1.125 0 0 1 2.25 0M12.5 8.625a1.125 1.125 0 1 0 0-2.25a1.125 1.125 0 0 0 0 2.25"
				/>
			{/if}
		</svg>
		<div class={styles.line()}></div>
	</div>
</PaneResizer>
