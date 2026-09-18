"""Builds the LAION sample used by the gallery app: streams a systematic
1-in-N sample from `laion/relaion2B-en-research-safe`, downloads and
resizes the images, then computes CLIP embeddings and a UMAP projection
so visually similar images end up near each other in the gallery.

The download step and the embeddings/UMAP step run as two separate OS
processes (this script re-invokes itself for the second one) rather than
sharing one Python process — `datasets` streaming and `torch` don't
reliably coexist in the same long-lived process on every machine, and
this sidesteps that entirely.

Usage:
    python run_pipeline.py                    # download, embed, and project
    python run_pipeline.py --skip-embeddings   # download only
    python run_pipeline.py --umap-only         # retune UMAP without re-encoding
    python run_pipeline.py --backfill-colors   # fill in missing avg-color placeholders
    python run_pipeline.py --build-atlas       # rebuild the map view's sprite atlas

Edit the parameters below to change the sample size, stride, or image
dimensions.
"""
import argparse
import io
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests
from datasets import load_dataset
from dotenv import load_dotenv
from huggingface_hub import login
from PIL import Image, ImageFilter

# === Parameters ===
SAMPLE_EVERY_N = 1000
MAX_TOTAL_IMAGES = 10000
MAX_IMAGE_DIMENSION = 150
MAX_ROWS_TO_SCAN = 15_000_000
SAVE_EVERY = 25
ATLAS_CELL_SIZE = 64  # px per thumbnail in the map view's sprite atlas
ATLAS_BLUR_RADIUS = 6  # px, for the pre-blurred "unsafe" atlas copy

DATASET_NAME = "laion/relaion2B-en-research-safe"

OUTPUT_DIR = Path(__file__).parent / "../app/public/data"
IMAGES_DIR = OUTPUT_DIR / "images"
METADATA_PATH = OUTPUT_DIR / "metadata.json"
PROGRESS_PATH = OUTPUT_DIR / "progress.json"
EMBEDDINGS_PATH = OUTPUT_DIR / "embeddings.npy"
ATLAS_PATH = OUTPUT_DIR / "atlas.jpg"
ATLAS_BLURRED_PATH = OUTPUT_DIR / "atlas-blurred.jpg"
ATLAS_META_PATH = OUTPUT_DIR / "atlas-meta.json"


def resize_to_fit(image, max_dimension):
    width, height = image.size
    scale = max_dimension / max(width, height)
    if scale >= 1:
        return image
    new_size = (round(width * scale), round(height * scale))
    return image.resize(new_size, Image.LANCZOS)


def average_color_hex(image):
    r, g, b = image.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
    return f"#{r:02x}{g:02x}{b:02x}"


VISUAL_GRID = 8  # downsampled to an 8x8 grid of RGB values
VISUAL_WEIGHT = 1.0  # relative influence vs. the (already unit-norm) CLIP embedding


def visual_feature(image):
    # A coarse spatial color grid: captures rough color AND shape/composition
    # (since it's still spatially arranged, not just a global average) at low
    # dimensionality, without needing a separate shape/edge descriptor.
    small = image.resize((VISUAL_GRID, VISUAL_GRID), Image.LANCZOS)
    values = np.asarray(small, dtype=np.float32).flatten() / 255.0
    norm = np.linalg.norm(values)
    return values / norm if norm > 0 else values


def load_metadata():
    return json.loads(METADATA_PATH.read_text()) if METADATA_PATH.exists() else []


def save_metadata(current_metadata):
    with open(METADATA_PATH, "w") as f:
        json.dump(current_metadata, f, indent=2)


def save_progress(rows_scanned):
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"rows_scanned": rows_scanned}, f)


def run_download():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    resume_from = json.loads(PROGRESS_PATH.read_text())["rows_scanned"] if PROGRESS_PATH.exists() else 0
    on_disk_count = len(load_metadata())
    print(f"Resuming with {on_disk_count} images already saved, {resume_from:,} rows already scanned.")

    dataset = load_dataset(DATASET_NAME, split="train", streaming=True)
    if resume_from:
        dataset = dataset.skip(resume_from)

    failed_downloads = 0
    duplicate_skips = 0
    candidates_seen = 0
    batch = []
    i = resume_from - 1

    start = time.time()
    for offset, row in enumerate(dataset):
        i = resume_from + offset
        if i >= MAX_ROWS_TO_SCAN:
            break
        if i % SAMPLE_EVERY_N != 0:
            continue

        if not batch:
            metadata = load_metadata()
            seen_urls = {entry["source_url"] for entry in metadata}
            next_id = max((int(entry["id"]) for entry in metadata), default=-1) + 1

        if len(metadata) + len(batch) >= MAX_TOTAL_IMAGES:
            break

        candidates_seen += 1
        url = row.get("url")
        caption = row.get("caption") or ""

        if url in seen_urls:
            duplicate_skips += 1
            continue

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
        except Exception:
            failed_downloads += 1
            continue

        image = resize_to_fit(image, MAX_IMAGE_DIMENSION)
        image_id = f"{next_id + len(batch):05d}"
        filename = f"{image_id}.jpg"
        image.save(IMAGES_DIR / filename, "JPEG", quality=85)

        entry = {
            "id": image_id,
            "filename": filename,
            "caption": caption,
            "source_url": url,
            "color": average_color_hex(image),
        }
        if row.get("similarity") is not None:
            entry["similarity"] = row["similarity"]
        if row.get("punsafe") is not None:
            entry["punsafe"] = row["punsafe"]
        if row.get("pwatermark") is not None:
            entry["pwatermark"] = row["pwatermark"]
        if row.get("exif") and row["exif"] not in ("{}", "null"):
            entry["exif"] = row["exif"]
        batch.append(entry)
        seen_urls.add(url)

        if len(batch) >= SAVE_EVERY:
            metadata = load_metadata()
            metadata.extend(batch)
            save_metadata(metadata)
            save_progress(i + 1)
            batch = []

        if candidates_seen % 100 == 0:
            elapsed = time.time() - start
            print(f"Scanned {i:,} rows in {elapsed:,.0f}s this run, {len(metadata) + len(batch)} saved total, {failed_downloads} failed, {duplicate_skips} duplicates skipped this run")

    if batch:
        metadata = load_metadata()
        metadata.extend(batch)
        save_metadata(metadata)
        save_progress(i + 1)

    final_count = len(load_metadata())
    print(f"\nDownload done. Scanned up to row {i:,}, sampled {candidates_seen} candidates this run, saved {final_count} images total, {failed_downloads} failed downloads, {duplicate_skips} duplicate URLs skipped this run.")


def run_backfill_colors():
    metadata = load_metadata()
    updated = 0
    for entry in metadata:
        if "color" in entry:
            continue
        path = IMAGES_DIR / entry["filename"]
        if not path.exists():
            continue
        with Image.open(path) as image:
            entry["color"] = average_color_hex(image.convert("RGB"))
        updated += 1
    save_metadata(metadata)
    print(f"Backfilled color for {updated} of {len(metadata)} entries.")


def build_atlas():
    # Precomputes the map view's whole sprite sheet — every thumbnail laid
    # out into one big grid image, plus a second copy with unsafe-flagged
    # ones pre-blurred — so the app fetches two static files total instead
    # of one request per image, and there's no per-tile loading lag at all
    # (everything is already local once those two images have loaded).
    metadata = load_metadata()
    n = len(metadata)
    if n == 0:
        print("No entries in metadata.json — nothing to build an atlas from.")
        return

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    atlas_w = cols * ATLAS_CELL_SIZE
    atlas_h = rows * ATLAS_CELL_SIZE
    print(f"Building {cols}x{rows} atlas ({atlas_w}x{atlas_h}px) for {n} entries...")

    atlas = Image.new("RGB", (atlas_w, atlas_h), (0, 0, 0))
    atlas_blurred = Image.new("RGB", (atlas_w, atlas_h), (0, 0, 0))

    start = time.time()
    missing = 0
    for i, entry in enumerate(metadata):
        col = i % cols
        row = i // cols
        path = IMAGES_DIR / entry["filename"]
        if not path.exists():
            missing += 1
            entry.pop("atlasCell", None)
            continue
        with Image.open(path) as img:
            thumb = img.convert("RGB").resize(
                (ATLAS_CELL_SIZE, ATLAS_CELL_SIZE), Image.LANCZOS
            )
        atlas.paste(thumb, (col * ATLAS_CELL_SIZE, row * ATLAS_CELL_SIZE))
        atlas_blurred.paste(
            thumb.filter(ImageFilter.GaussianBlur(radius=ATLAS_BLUR_RADIUS)),
            (col * ATLAS_CELL_SIZE, row * ATLAS_CELL_SIZE),
        )
        entry["atlasCell"] = i

        if (i + 1) % 500 == 0 or i + 1 == n:
            elapsed = time.time() - start
            print(f"  {i + 1:,}/{n:,} thumbnails placed ({elapsed:,.1f}s elapsed)")

    print("Encoding and saving atlas.jpg + atlas-blurred.jpg (this can take a few seconds for a large atlas)...")
    atlas.save(ATLAS_PATH, "JPEG", quality=85)
    atlas_blurred.save(ATLAS_BLURRED_PATH, "JPEG", quality=85)
    with open(ATLAS_META_PATH, "w") as f:
        json.dump({"cellSize": ATLAS_CELL_SIZE, "cols": cols, "rows": rows}, f)
    save_metadata(metadata)

    total_elapsed = time.time() - start
    print(
        f"Done in {total_elapsed:,.1f}s — {n} entries "
        f"({missing} missing local images skipped) -> {ATLAS_PATH}"
    )


def run_embeddings_and_umap(umap_only=False):
    import umap

    metadata = json.loads(METADATA_PATH.read_text())
    expected_dim = 512 + VISUAL_GRID * VISUAL_GRID * 3

    embeddings = None
    if umap_only and EMBEDDINGS_PATH.exists():
        cached = np.load(EMBEDDINGS_PATH)
        if cached.shape == (len(metadata), expected_dim):
            embeddings = cached
            print(f"Reusing cached embeddings {embeddings.shape} from {EMBEDDINGS_PATH}")
        else:
            print(
                f"Cached embeddings {cached.shape} don't match metadata/features "
                f"({len(metadata)}, {expected_dim}) — re-encoding."
            )

    if embeddings is None:
        # Imported here, in this dedicated subprocess, so torch is never in
        # the same process as the streaming download above.
        import open_clip
        import torch

        torch.multiprocessing.set_sharing_strategy("file_system")

        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        model.eval()

        embeddings = np.zeros((len(metadata), expected_dim), dtype=np.float32)
        batch_size = 32

        with torch.no_grad():
            for batch_start in range(0, len(metadata), batch_size):
                batch = metadata[batch_start : batch_start + batch_size]
                raw_images = [Image.open(IMAGES_DIR / entry["filename"]) for entry in batch]

                clip_input = torch.stack([preprocess(img) for img in raw_images])
                clip_embeddings = model.encode_image(clip_input)
                clip_embeddings = clip_embeddings / clip_embeddings.norm(dim=-1, keepdim=True)

                visual_embeddings = np.stack(
                    [visual_feature(img.convert("RGB")) for img in raw_images]
                )

                embeddings[batch_start : batch_start + len(batch), :512] = clip_embeddings.numpy()
                embeddings[batch_start : batch_start + len(batch), 512:] = (
                    VISUAL_WEIGHT * visual_embeddings
                )

                if batch_start % (batch_size * 10) == 0:
                    print(f"Embedded {batch_start + len(batch)}/{len(metadata)} images...")

        np.save(EMBEDDINGS_PATH, embeddings)
        print(f"Saved {embeddings.shape} embeddings to {EMBEDDINGS_PATH}")

    # n_neighbors=30 (up from 15) favors more global structure over tiny
    # local clusters, which reads better across ~5k points.
    reducer = umap.UMAP(n_neighbors=30, min_dist=0.1, metric="cosine")
    coords_2d = reducer.fit_transform(embeddings)

    # Percentile clipping instead of raw min/max: a handful of outlier points
    # (visually or semantically unlike everything else) otherwise stretch the
    # whole [0,1] normalization, squeezing the actual main cluster into a
    # tiny corner. Outliers still get placed, just clamped to the edge
    # instead of dictating the entire coordinate range.
    mins = np.percentile(coords_2d, 2, axis=0)
    maxs = np.percentile(coords_2d, 98, axis=0)
    normalized = np.clip((coords_2d - mins) / (maxs - mins), 0, 1)

    for entry, (x, y) in zip(metadata, normalized):
        entry["x"] = float(x)
        entry["y"] = float(y)

    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved normalized x/y coordinates for {len(metadata)} entries to {METADATA_PATH}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Only download images; skip the embeddings/UMAP step.",
    )
    parser.add_argument(
        "--umap-only",
        action="store_true",
        help=(
            "Skip download AND re-encoding — reuse embeddings.npy (if it "
            "matches metadata.json) and just rerun UMAP. Fast way to "
            "retune UMAP parameters."
        ),
    )
    parser.add_argument(
        "--backfill-colors",
        action="store_true",
        help=(
            "Compute the average color for any existing entries missing "
            "one, from the already-downloaded local images. No network or "
            "GPU/CPU-heavy work — just local file reads."
        ),
    )
    parser.add_argument(
        "--build-atlas",
        action="store_true",
        help=(
            "Rebuild the map view's sprite atlas (atlas.jpg, "
            "atlas-blurred.jpg, atlas-meta.json) from the already-downloaded "
            "local images. Local-only — no network. Rerun this after adding "
            "images or the map view will fall back to color placeholders "
            "for anything newer than the last atlas build."
        ),
    )
    args = parser.parse_args()

    if args.backfill_colors:
        run_backfill_colors()
        return

    if args.build_atlas:
        build_atlas()
        return

    if args.umap_only:
        run_embeddings_and_umap(umap_only=True)
        return

    load_dotenv()
    login(token=os.environ["HF_TOKEN"])

    run_download()

    if args.skip_embeddings:
        return

    print("\nRunning embeddings + UMAP in a separate process...")
    result = subprocess.run(
        [sys.executable, __file__, "--_embeddings-only"],
        cwd=Path(__file__).parent,
    )
    if result.returncode != 0:
        print("\nEmbeddings/UMAP step failed — your downloaded images and metadata.json are unaffected.")
        sys.exit(result.returncode)

    print("\nPipeline complete — metadata.json now has fresh images and an updated gradient layout.")


if __name__ == "__main__":
    if "--_embeddings-only" in sys.argv:
        run_embeddings_and_umap()
    else:
        main()
