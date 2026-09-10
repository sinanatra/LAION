<script>
  let { item, onClose } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onClose()} />

<aside class="relative h-full w-full text-base">
  <button class="absolute top-1 right-1" onclick={onClose} aria-label="Close"
    >close</button
  >
  <img
    src={`${import.meta.env.BASE_URL}data/images/${item.filename}`}
    alt={item.caption}
    class="block w-full"
  />
  <div class="space-y-1 p-2">
    <p>{item.caption}</p>
    {#if item.keyword}
      <p>keyword: {item.keyword}</p>
    {/if}
  <!-- {#if item.similarity !== undefined && item.similarity !== null}
    <p>similarity: {item.similarity.toFixed(3)}</p>
  {/if} -->
    <p class="break-all">
      source: <a
        class="underline"
        href={item.source_url}
        target="_blank"
        rel="noopener noreferrer">{item.source_url}</a
      >
    </p>
  </div>
</aside>
