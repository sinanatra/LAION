<script>
  import { onMount } from "svelte";
  import DetailPanel from "./lib/DetailPanel.svelte";
  import MapView from "./lib/MapView.svelte";
  import SearchControls from "./lib/SearchControls.svelte";
  import InfoText from "./lib/InfoText.svelte";
  import {
    filterItems,
    isFlaggedUnsafe,
    sortItems,
  } from "./lib/filterAndSort.js";

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
  let viewMode = $state("map");
  let atlasMeta = $state(null);

  onMount(async () => {
    const base = import.meta.env.BASE_URL;
    try {
      const res = await fetch(`${base}data/metadata.json`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      items = await res.json();
    } catch (err) {
      loadError = err.message;
      return;
    }
    try {
      const res = await fetch(`${base}data/atlas-meta.json`);
      if (res.ok) atlasMeta = await res.json();
    } catch {}
  });

  function tileStyle(item) {
    if (!atlasMeta || item.atlasCell === undefined) {
      return item.color ? `background-color: ${item.color}` : "";
    }
    const { cols, rows } = atlasMeta;
    const col = item.atlasCell % cols;
    const row = Math.floor(item.atlasCell / cols);
    const posX = cols > 1 ? (col / (cols - 1)) * 100 : 0;
    const posY = rows > 1 ? (row / (rows - 1)) * 100 : 0;
    return `background-image: url(${import.meta.env.BASE_URL}data/atlas.jpg); background-size: ${cols * 100}% ${rows * 100}%; background-position: ${posX}% ${posY}%;`;
  }

  let percentOfDataset = $derived.by(() => {
    if (items.length === 0) return "0";
    const value = (items.length / TOTAL_DATASET_SIZE) * 100;
    return new Intl.NumberFormat(undefined, {
      maximumSignificantDigits: 2,
    }).format(value);
  });

  let filtered = $derived(
    sortItems(filterItems(items, { query, scoreMode, minScore, maxScore })),
  );

  function pickRandom() {
    if (filtered.length === 0) return;
    const index = Math.floor(Math.random() * filtered.length);
    const pick = filtered[index];
    highlightedId = pick.id;
    selectedItem = pick;
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
    <div class="flex text-sm normal-case">
      <button
        class="cursor-pointer px-3 {viewMode === 'grid'
          ? 'underline'
          : 'opacity-60'}"
        onclick={() => (viewMode = "grid")}
      >
        grid
      </button>
      <button
        class="cursor-pointer px-3 {viewMode === 'map'
          ? 'underline'
          : 'opacity-60'}"
        onclick={() => (viewMode = "map")}
      >
        map
      </button>
    </div>
  </menu>
</header>

<article
  class="flex w-full flex-col-reverse md:h-[calc(100vh-30px)] md:flex-row"
>
  <div
    class="w-full bg-(--background-color) text-(--text-color) md:h-full md:flex-1 {viewMode ===
    'grid'
      ? 'overflow-y-auto md:block'
      : 'h-[70vh] overflow-hidden md:h-full'}"
  >
    {#if !loadError}
      {#if viewMode === "grid"}
        <div class="grid grid-cols-[repeat(auto-fill,minmax(30px,1fr))]">
          {#each filtered as item (item.id)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div
              id={`item-${item.id}`}
              title={item.caption}
              style={tileStyle(item)}
              onclick={() => (selectedItem = item)}
              class="aspect-square w-full cursor-pointer bg-no-repeat {highlightedId ===
              item.id
                ? 'outline-2 outline-(--text-color)'
                : ''} {blurUnsafe && isFlaggedUnsafe(item)
                ? 'blur-sm hover:blur-none'
                : ''}"
            ></div>
          {/each}
        </div>
        {#if filtered.length === 0}
          <p>no images match your filters.</p>
        {/if}
      {:else}
        <MapView
          items={filtered}
          bind:selectedItem
          {highlightedId}
          {blurUnsafe}
        />
      {/if}
    {/if}
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
