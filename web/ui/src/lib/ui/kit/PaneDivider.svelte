<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const paneDividerVariants = tv({
		slots: {
			separator: [
				'absolute flex items-center justify-center',
				'transition-all duration-300',
				'text-divider hover:text-divider-active'
			],
			line: 'grow stroke-current opacity-[0.85]'
		},
		variants: {
			direction: {
				vertical: {
					separator: 'w-3 flex-col left-1/2 top-0 bottom-0 -translate-x-1/2',
					line: 'w-px'
				},
				horizontal: {
					separator: 'h-3 flex-row top-1/2 left-0 right-0 -translate-y-1/2',
					line: 'h-px'
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
		ondblclick?: () => void;
	}

	let { direction = 'vertical', class: className = '', ondblclick }: Props = $props();

	const styles = $derived(paneDividerVariants({ direction }));
</script>

{#snippet line()}
	{#if direction === 'vertical'}
		<svg class={styles.line()} preserveAspectRatio="none">
			<line x1="50%" y1="0" x2="50%" y2="100%" stroke-width="0.5" />
		</svg>
	{:else}
		<svg class={styles.line()} preserveAspectRatio="none">
			<line x1="0" y1="50%" x2="100%" y2="50%" stroke-width="2" />
		</svg>
	{/if}
{/snippet}

<PaneResizer class="relative z-50" {ondblclick}>
	<div class={styles.separator({ class: className })}>
		{@render line()}
	</div>
</PaneResizer>
