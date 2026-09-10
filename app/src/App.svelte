<script>
  import { onMount } from "svelte";
  import DetailPanel from "./lib/DetailPanel.svelte";

  // laion/relaion2B-en-research-safe row count, via the HF datasets-server
  // /size endpoint (checked 2026-09).
  const TOTAL_DATASET_SIZE = 2_097_693_557;

  let items = $state([]);
  let loadError = $state(null);
  let query = $state("");
  let activeKeywords = $state(new Set());
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

  let keywords = $derived(
    [...new Set(items.map((item) => item.keyword).filter(Boolean))].sort(),
  );

  let percentOfDataset = $derived.by(() => {
    if (items.length === 0) return "0";
    const value = (items.length / TOTAL_DATASET_SIZE) * 100;
    return new Intl.NumberFormat(undefined, {
      maximumSignificantDigits: 2,
    }).format(value);
  });

  let filtered = $derived.by(() => {
    const matches = items.filter((item) => {
      const matchesKeyword =
        activeKeywords.size === 0 || activeKeywords.has(item.keyword);
      const q = query.trim().toLowerCase();
      const matchesQuery =
        !q ||
        item.caption.toLowerCase().includes(q) ||
        (item.keyword ?? "").toLowerCase().includes(q) ||
        item.source_url.toLowerCase().includes(q);
      return matchesKeyword && matchesQuery;
    });

    const withCoords = matches.filter(
      (item) => item.x !== undefined && item.y !== undefined,
    );
    const withoutCoords = matches.filter(
      (item) => item.x === undefined || item.y === undefined,
    );

    if (withCoords.length > 0) {
      const numBands = Math.max(1, Math.round(Math.sqrt(withCoords.length)));
      const banded = withCoords.map((item) => ({
        item,
        band: Math.min(numBands - 1, Math.floor(item.y * numBands)),
      }));
      banded.sort((a, b) => {
        if (a.band !== b.band) return a.band - b.band;
        const direction = a.band % 2 === 0 ? 1 : -1;
        return direction * (a.item.x - b.item.x);
      });
      return [...banded.map((entry) => entry.item), ...withoutCoords];
    }

    const withSimilarity = matches.filter(
      (item) => item.similarity !== undefined && item.similarity !== null,
    );
    const withoutSimilarity = matches.filter(
      (item) => item.similarity === undefined || item.similarity === null,
    );
    withSimilarity.sort((a, b) => b.similarity - a.similarity);
    return [...withSimilarity, ...withoutSimilarity];
  });

  function toggleKeyword(keyword) {
    const next = new Set(activeKeywords);
    if (next.has(keyword)) next.delete(keyword);
    else next.add(keyword);
    activeKeywords = next;
  }

  function pickRandom() {
    if (filtered.length === 0) return;
    const pick = filtered[Math.floor(Math.random() * filtered.length)];
    highlightedId = pick.id;
    selectedItem = pick;
    requestAnimationFrame(() => {
      document
        .getElementById(`item-${pick.id}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }
</script>

<header class="block h-7.5 w-full">
  <menu
    class="flex items-center text-white justify-between pl-4 uppercase text-xl tracking-wide"
  >
    <p>{percentOfDataset}% of laion-5b</p>
  </menu>
</header>

<article class="flex w-full flex-col md:h-[calc(100vh-30px)] md:flex-row">
  <div
    class="w-full overflow-y-auto bg-(--background-color) text-(--text-color) md:block md:h-full md:flex-1 {selectedItem
      ? 'hidden'
      : ''}"
  >
    <div>
      {#if !loadError}
        <div class="grid grid-cols-[repeat(auto-fill,minmax(30px,1fr))]">
          {#each filtered as item (item.id)}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <img
              id={`item-${item.id}`}
              src={`${import.meta.env.BASE_URL}data/images/${item.filename}`}
              alt={item.caption}
              title={item.caption}
              loading="lazy"
              onclick={() => (selectedItem = item)}
              class="aspect-square w-full cursor-pointer object-cover {highlightedId ===
              item.id
                ? 'outline-2 outline-(--text-color)'
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
    class="w-full shrink-0 overflow-y-auto bg-(--fade-color) text-(--background-color) md:h-full md:w-64"
  >
    {#if selectedItem}
      <DetailPanel item={selectedItem} onClose={() => (selectedItem = null)} />
    {:else}
      <div class="px-2 py-1">
        {#if loadError}
          <p>
            Could not load data/metadata.json ({loadError}). Run the notebook
            first.
          </p>
        {:else}
          <div class="mb-2 text-black">
            <input
              class="my-2 block"
              type="text"
              placeholder="search..."
              bind:value={query}
            />
          </div>
          <p class="mb-4">{filtered.length} of {items.length}</p>
          <button
            class="my-2 block"
            onclick={pickRandom}
            disabled={filtered.length === 0}>random</button
          >

          <p class="mb-3 block leading-[1.4em]">
            This is a teaching tool built for the <a
              class="underline"
              href="https://maind.supsi.ch/master-interaction-design/"
              target="_blank"
              rel="noopener noreferrer">Data Driven Design course</a
            > at SUPSI's Master of Arts in Interaction Design, part of 2026's focus
            on the materialities of AI. It uses a safety-filtered sample of LAION-5B,
            one of the datasets used to train large text-to-image models.
          </p>
          <p class="mb-4 block leading-[1.4em]">
            Click on any image to see its caption and a link back to that
            original source.
          </p>

          {#if keywords.length > 0}
            <div class="columns-2 text-base">
              {#each keywords as keyword}
                <input
                  type="checkbox"
                  id={`kw-${keyword}`}
                  checked={activeKeywords.has(keyword)}
                  onchange={() => toggleKeyword(keyword)}
                /><label for={`kw-${keyword}`}>{keyword}</label><br />
              {/each}
            </div>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
</article>
