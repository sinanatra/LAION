<script>
  let {
    query = $bindable(""),
    scoreMode = $bindable("unsafe"),
    minScore = $bindable(0),
    maxScore = $bindable(1),
    blurUnsafe = $bindable(true),
    onRandom,
    filteredCount,
    totalCount,
  } = $props();

  /** @param {number} value */
  function setMin(value) {
    minScore = Math.min(value, maxScore);
  }

  /** @param {number} value */
  function setMax(value) {
    maxScore = Math.max(value, minScore);
  }
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
  <button
    class="bg-black text-white p-1 pointer my-2 block"
    onclick={onRandom}
    disabled={filteredCount === 0}>random</button
  >

  <div class="mt-4">
    <label>
      <input
        type="radio"
        name="score-mode"
        value="unsafe"
        bind:group={scoreMode}
      />
      unsafe
    </label>
    <label class="ml-2">
      <input
        type="radio"
        name="score-mode"
        value="watermark"
        bind:group={scoreMode}
      />
      watermark
    </label>

    <p class="mt-1">
      {scoreMode}: {(minScore * 100).toFixed(0)}% to {(maxScore * 100).toFixed(
        0,
      )}%
    </p>

    <label for="min-score" class="mt-1 block text-sm">min</label>
    <input
      id="min-score"
      class="block w-full"
      type="range"
      min="0"
      max="1"
      step="0.01"
      value={minScore}
      oninput={(e) => setMin(Number(e.currentTarget.value))}
    />

    <label for="max-score" class="mt-1 block text-sm">max</label>
    <input
      id="max-score"
      class="block w-full"
      type="range"
      min="0"
      max="1"
      step="0.01"
      value={maxScore}
      oninput={(e) => setMax(Number(e.currentTarget.value))}
    />

    <label class="mt-2 block">
      <input type="checkbox" bind:checked={blurUnsafe} />
      blur unsafe images
    </label>
  </div>

