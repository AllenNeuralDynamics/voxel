<script lang="ts">
	export interface CubeScheme {
		top: string;
		left: string;
		right: string;
	}

	interface Props {
		topLeft?: CubeScheme;
		topRight?: CubeScheme;
		bottom?: CubeScheme;
		class?: string;
	}

	const defaultScheme: CubeScheme = { top: 'currentColor', left: 'currentColor', right: 'currentColor' };

	const { topLeft = defaultScheme, topRight = defaultScheme, bottom = defaultScheme, class: className = '' }: Props =
		$props();
</script>

<svg xmlns="http://www.w3.org/2000/svg" viewBox="-7 -5 360 360" class={className}>
	<!-- Top-Left Cube -->
	<polygon points="86.6,0 173.2,50 86.6,100 0,50" fill={topLeft.top} />
	<polygon points="0,50 86.6,100 86.6,200 0,150" fill={topLeft.left} />
	<polygon points="86.6,100 173.2,50 173.2,150 86.6,200" fill={topLeft.right} />
	<!-- Top-Right Cube -->
	<polygon points="259.8,0 346.4,50 259.8,100 173.2,50" fill={topRight.top} />
	<polygon points="173.2,50 259.8,100 259.8,200 173.2,150" fill={topRight.left} />
	<polygon points="259.8,100 346.4,50 346.4,150 259.8,200" fill={topRight.right} />
	<!-- Bottom Cube -->
	<polygon points="173.2,150 259.8,200 173.2,250 86.6,200" fill={bottom.top} />
	<polygon points="86.6,200 173.2,250 173.2,350 86.6,300" fill={bottom.left} />
	<polygon points="173.2,250 259.8,200 259.8,300 173.2,350" fill={bottom.right} />
</svg>
