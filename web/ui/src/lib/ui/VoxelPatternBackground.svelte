<script lang="ts">
	interface Props {
		opacity?: number;
		size?: number;
		fade?: number;
		class?: string;
	}

	const { opacity = 0.5, size = 48, fade = 60, class: className = '' }: Props = $props();
</script>

<div class="pointer-events-none absolute inset-0 {className}">
	<svg class="absolute inset-0 h-full w-full" aria-hidden="true">
		<defs>
			<pattern id="voxel-bg" width={size} height={size} patternUnits="userSpaceOnUse">
				<svg viewBox="-7 -5 360 360" width={size} height={size}>
					<polygon
						points="86.6,0 173.2,50 86.6,100 0,50"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="0,50 86.6,100 86.6,200 0,150"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="86.6,100 173.2,50 173.2,150 86.6,200"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="259.8,0 346.4,50 259.8,100 173.2,50"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="173.2,50 259.8,100 259.8,200 173.2,150"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="259.8,100 346.4,50 346.4,150 259.8,200"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="173.2,150 259.8,200 173.2,250 86.6,200"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="86.6,200 173.2,250 173.2,350 86.6,300"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
					<polygon
						points="173.2,250 259.8,200 259.8,300 173.2,350"
						fill="none"
						stroke="var(--border)"
						stroke-width="6"
						{opacity}
					/>
				</svg>
			</pattern>
		</defs>
		<rect width="100%" height="100%" fill="url(#voxel-bg)" />
	</svg>
	<div
		class="absolute inset-0"
		style="background: radial-gradient(ellipse at center, transparent 0%, var(--background) {fade}%);"
	></div>
</div>
