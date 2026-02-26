<script lang="ts" module>
	import { tv, type VariantProps } from 'tailwind-variants';

	export const paneDividerVariants = tv({
		slots: {
			separator: [
				'absolute flex items-center justify-center',
				'transition-all duration-300',
				'text-zinc-700 hover:text-zinc-500'
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
					line: 'h-[2px]'
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

<PaneResizer class="relative z-50" {ondblclick}>
	<div class={styles.separator({ class: className })}>
		<div class={styles.line()}></div>
	</div>
</PaneResizer>
