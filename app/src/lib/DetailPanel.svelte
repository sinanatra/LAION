<script>
  let { item, onClose } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onClose()} />

<aside
  class="w-full border-b bg-(--fade-color) mb-10 p-2 text-base text-(--background-color)"
>
  <button class="mb-2 block" onclick={onClose} aria-label="Close">close</button>
  <img
    src={`${import.meta.env.BASE_URL}data/images/${item.filename}`}
    alt={item.caption}
    class="mb-2 block h-60 w-full object-contain bg-white"
  />
  <div class="space-y-1">
    <p class="text-xl">
      {item.caption}
    </p>

    <p class="break-all">
      <a
        class="underline"
        href={item.source_url}
        target="_blank"
        rel="noopener noreferrer">{item.source_url}</a
      >
    </p>
  </div>
</aside>
