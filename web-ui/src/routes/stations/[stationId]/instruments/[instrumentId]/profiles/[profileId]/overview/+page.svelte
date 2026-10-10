<script lang="ts">
  import { page } from '$app/state';

  import ProfileOverview from '../../ProfileOverview.svelte';
</script>

<ProfileOverview selectedProfileId={page.params.profileId ?? ''} />
