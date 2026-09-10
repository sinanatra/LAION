<script>
  let { item, onClose } = $props();

  let formattedExif = $derived.by(() => {
    if (!item.exif) return null;
    try {
      return JSON.stringify(JSON.parse(item.exif), null, 2);
    } catch {
      return item.exif;
    }
  });
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onClose()} />

<aside
  class="w-full border-b bg-(--fade-color) mb-10 p-2 text-base text-(--background-color)"
>
  <button
    class="bg-black text-white px-1 pointer mb-2 block"
    onclick={onClose}
    aria-label="Close">close</button
  >
  <img
    src={`${import.meta.env.BASE_URL}data/images/${item.filename}`}
    alt={item.caption}
    class="mb-2 block h-60 w-full object-contain bg-white"
  />
  <div class="space-y-1">
    <p class="text-base font-semibold leading-tight">
      {item.caption}
    </p>

    <p class="break-all">
      <a
        class="underline text-olive-800 text-xs leading-[1.1em] block"
        href={item.source_url}
        target="_blank"
        rel="noopener noreferrer">{item.source_url}</a
      >
    </p>

    {#if item.punsafe !== undefined}
      <p>unsafe probability: {(item.punsafe * 100).toFixed(2)}%</p>
    {/if}
    {#if item.pwatermark !== undefined}
      <p>watermark probability: {(item.pwatermark * 100).toFixed(2)}%</p>
    {/if}
    {#if formattedExif}
      <p class="text-sm">exif:</p>
      <pre
        class="max-h-40 overflow-auto whitespace-pre-wrap break-all bg-black p-2 text-xs text-white select-all"><code
          >{formattedExif}</code
        ></pre>
    {/if}
  </div>
</aside>
