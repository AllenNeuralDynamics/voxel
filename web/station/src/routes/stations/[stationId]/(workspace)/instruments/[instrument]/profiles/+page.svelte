<script lang="ts">
  import ProfileBar from '$lib/features/profiles/ProfileBar.svelte';
</script>

<!-- The Profiles address goes to the active profile, else the first one, once the instrument is known. -->
<ProfileBar place="profiles" label="Profiles" />
