<script lang="ts">
  import { onMount } from 'svelte';

  /**
   * On capture, a thumbnail flies from the preview (`data-fly-origin`) into the snapshots picker
   * (`data-fly-target`) — a "filed away" cue. Fully self-contained: spawns a transient element,
   * animates it, removes it. Driven by the `voxel:snapshot-captured` window event.
   */
  function fly(thumbnail: string): void {
    const origin = document.querySelector('[data-fly-origin]')?.getBoundingClientRect();
    const target = document.querySelector('[data-fly-target]')?.getBoundingClientRect();
    if (!origin || !target) return;

    const img = document.createElement('img');
    img.src = thumbnail;
    img.alt = '';
    img.style.position = 'fixed';
    img.style.zIndex = '100';
    img.style.opacity = '0';
    img.className = 'pointer-events-none rounded-sm border border-border/60 object-cover shadow-xl';

    img.onload = () => {
      const aspect = img.naturalWidth / img.naturalHeight || 1;
      const startW = Math.min(origin.width * 0.45, 220);
      const startH = startW / aspect;
      const startCx = origin.left + origin.width / 2;
      const startCy = origin.top + origin.height / 2;

      img.style.left = `${startCx - startW / 2}px`;
      img.style.top = `${startCy - startH / 2}px`;
      img.style.width = `${startW}px`;
      img.style.height = `${startH}px`;

      const dx = target.left + target.width / 2 - startCx;
      const dy = target.top + target.height / 2 - startCy;
      const scale = Math.max(0.05, target.height / startH);

      const anim = img.animate(
        [
          { transform: 'translate(0, 0) scale(1)', opacity: 1, offset: 0 },
          { opacity: 1, offset: 0.75 },
          { transform: `translate(${dx}px, ${dy}px) scale(${scale})`, opacity: 0, offset: 1 }
        ],
        { duration: 500, easing: 'cubic-bezier(0.4, 0, 0.2, 1)' }
      );
      anim.onfinish = () => img.remove();
      anim.oncancel = () => img.remove();
    };

    document.body.appendChild(img);
  }

  onMount(() => {
    const onCaptured = (e: Event) => fly((e as CustomEvent<{ thumbnail: string }>).detail.thumbnail);
    window.addEventListener('voxel:snapshot-captured', onCaptured);
    return () => window.removeEventListener('voxel:snapshot-captured', onCaptured);
  });
</script>
