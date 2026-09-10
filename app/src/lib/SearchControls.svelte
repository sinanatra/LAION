<script>
  let {
    query = $bindable(""),
    onRandom,
    filteredCount,
    totalCount,
  } = $props();
</script>

<div class="mb-2 text-black">
  <p class="mt-1">{filteredCount} of {totalCount}</p>
  <input
    class="my-2 mb-8 block bg-gray-300"
    type="text"
    placeholder="search..."
    bind:value={query}
  />
</div>
<button class="my-2 block" onclick={onRandom} disabled={filteredCount === 0}
  >random</button
>
