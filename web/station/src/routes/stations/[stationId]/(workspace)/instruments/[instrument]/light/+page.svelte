<script lang="ts">
  import ProfileBar from '$lib/features/profiles/ProfileBar.svelte';
</script>

<!-- The Light address goes to the active profile, else the first one, once the instrument is known. -->
<ProfileBar place="light" label="Light" />
