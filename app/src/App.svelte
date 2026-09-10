<script>
  import { onMount, untrack } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import DetailPanel from "./lib/DetailPanel.svelte";
  import SearchControls from "./lib/SearchControls.svelte";
  import InfoText from "./lib/InfoText.svelte";
  import {
    filterItems,
    isFlaggedUnsafe,
    sortItems,
  } from "./lib/filterAndSort.js";

  // laion/relaion2B-en-research-safe row count, via the HF datasets-server
  // /size endpoint (checked 2026-09).
  const TOTAL_DATASET_SIZE = 2_097_693_557;

  let items = $state([]);
  let loadError = $state(null);
  let query = $state("");
  let scoreMode = $state("unsafe");
  let minScore = $state(0);
  let maxScore = $state(1);
  let blurUnsafe = $state(true);
  let selectedItem = $state(null);
  let highlightedId = $state(null);

  onMount(async () => {
    try {
      const res = await fetch(`${import.meta.env.BASE_URL}data/metadata.json`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      items = await res.json();
    } catch (err) {
      loadError = err.message;
    }
  });

  // Ticks up live as batches reveal, instead of jumping straight to the
  // final value once metadata.json loads — a small "loading" flourish.
  let percentOfDataset = $derived.by(() => {
    if (visibleCount === 0) return "0";
    const value = (visibleCount / TOTAL_DATASET_SIZE) * 100;
    return new Intl.NumberFormat(undefined, {
      maximumSignificantDigits: 2,
    }).format(value);
  });

  let filtered = $derived(
    sortItems(filterItems(items, { query, scoreMode, minScore, maxScore })),
  );

  const BATCH_SIZE = 50;
  let visibleCount = $state(0);
  let loadedIds = new SvelteSet();

  $effect(() => {
    items.length;
    query;
    scoreMode;
    minScore;
    maxScore;
    visibleCount = Math.min(BATCH_SIZE, untrack(() => filtered.length));
  });

  let visible = $derived(filtered.slice(0, visibleCount));

  $effect(() => {
    const batch = visible;
    if (
      batch.length > 0 &&
      visibleCount < filtered.length &&
      batch.every((item) => loadedIds.has(item.id))
    ) {
      visibleCount = Math.min(visibleCount + BATCH_SIZE, filtered.length);
    }
  });

  function onImageSettled(id) {
    loadedIds.add(id);
  }

  function pickRandom() {
    if (filtered.length === 0) return;
    const index = Math.floor(Math.random() * filtered.length);
    const pick = filtered[index];
    highlightedId = pick.id;
    selectedItem = pick;
    if (visibleCount <= index) {
      visibleCount = index + 1;
    }
    requestAnimationFrame(() => {
      document
        .getElementById(`item-${pick.id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  console.log(
    "%cHi there :) What are you doing here? Peeping around are you? the code is here: https://github.com/sinanatra",
    "color: #ff69b4; font-weight: bold; font-size: 14px;",
  );
</script>

<header class="block h-7.5 w-full">
  <menu
    class="flex items-center text-white justify-between pl-4 uppercase text-xl tracking-wide"
  >
    <p>{percentOfDataset}% of laion-5b</p>
  </menu>
</header>

<article
  class="flex w-full flex-col-reverse md:h-[calc(100vh-30px)] md:flex-row"
>
  <div
    class="w-full overflow-y-auto bg-(--background-color) text-(--text-color) md:block md:h-full md:flex-1"
  >
    <div>
      {#if !loadError}
        <div class="grid grid-cols-[repeat(auto-fill,minmax(30px,1fr))]">
          {#each visible as item (item.id)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <img
              id={`item-${item.id}`}
              src={`${import.meta.env.BASE_URL}data/images/${item.filename}`}
              alt=""
              title={item.caption}
              onclick={() => (selectedItem = item)}
              onload={() => onImageSettled(item.id)}
              onerror={(e) => {
                if (e.currentTarget instanceof HTMLElement)
                  e.currentTarget.style.display = "none";
                onImageSettled(item.id);
              }}
              class="aspect-square w-full cursor-pointer object-cover {highlightedId ===
              item.id
                ? 'outline-2 outline-(--text-color)'
                : ''} {blurUnsafe && isFlaggedUnsafe(item)
                ? 'blur-sm hover:blur-none'
                : ''}"
            />
          {/each}
        </div>
        {#if filtered.length === 0}
          <p>no images match your filters.</p>
        {/if}
      {/if}
    </div>
  </div>

  <div
    class="w-full shrink-0 overflow-y-auto bg-(--fade-color) py-2 text-(--background-color) md:h-full md:w-64"
  >
    {#if selectedItem}
      <DetailPanel item={selectedItem} onClose={() => (selectedItem = null)} />
    {/if}
    <div class="px-2">
      {#if loadError}
        <p>
          Could not load data/metadata.json ({loadError}). Run the notebook
          first.
        </p>
      {:else}
        <SearchControls
          bind:query
          bind:scoreMode
          bind:minScore
          bind:maxScore
          bind:blurUnsafe
          onRandom={pickRandom}
          filteredCount={filtered.length}
          totalCount={items.length}
        />
        <InfoText />
      {/if}
    </div>
  </div>
</article>
