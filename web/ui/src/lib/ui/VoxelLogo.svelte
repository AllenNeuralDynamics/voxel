<script lang="ts">
	import { brand } from '$lib/themes';

	export interface CubeScheme {
		light: string;
		mid: string;
		dark: string;
	}

	interface Props {
		topLeft?: CubeScheme;
		topRight?: CubeScheme;
		bottom?: CubeScheme;
		class?: string;
	}

	const { topLeft = brand.green, topRight = brand.red, bottom = brand.yellow, class: className = '' }: Props = $props();
</script>

<svg xmlns="http://www.w3.org/2000/svg" viewBox="-7 -5 360 360" class={className}>
	<!-- Top-Left Cube -->
	<polygon points="86.6,0 173.2,50 86.6,100 0,50" fill={topLeft.light} />
	<polygon points="0,50 86.6,100 86.6,200 0,150" fill={topLeft.mid} />
	<polygon points="86.6,100 173.2,50 173.2,150 86.6,200" fill={topLeft.dark} />
	<!-- Top-Right Cube -->
	<polygon points="259.8,0 346.4,50 259.8,100 173.2,50" fill={topRight.light} />
	<polygon points="173.2,50 259.8,100 259.8,200 173.2,150" fill={topRight.mid} />
	<polygon points="259.8,100 346.4,50 346.4,150 259.8,200" fill={topRight.dark} />
	<!-- Bottom Cube -->
	<polygon points="173.2,150 259.8,200 173.2,250 86.6,200" fill={bottom.light} />
	<polygon points="86.6,200 173.2,250 173.2,350 86.6,300" fill={bottom.mid} />
	<polygon points="173.2,250 259.8,200 259.8,300 173.2,350" fill={bottom.dark} />
</svg>
