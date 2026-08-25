from pathlib import Path

import numpy as np

# ---------------- CONFIG ----------------
NPY_DIR = Path(r"C:\Users\apolon\Documents\Polonsky\BrukerSandbox")
PATTERN = "eds_profile_map_*_element_*.npy"

SAVE_FIGURE = True
FIGURE_PATH = NPY_DIR / "eds_element_map_comparison.png"
# ----------------------------------------


def load_maps(npy_dir: Path, pattern: str):
    paths = sorted(npy_dir.glob(pattern))
    maps = []

    for path in paths:
        arr = np.load(path)
        maps.append((path, arr))

    return maps


def print_stats(maps):
    print(f"Found {len(maps)} .npy files")

    for path, arr in maps:
        print()
        print(f"File: {path.name}")
        print(f"  shape: {arr.shape}")
        print(f"  dtype: {arr.dtype}")
        print(f"  min: {arr.min()}")
        print(f"  max: {arr.max()}")
        print(f"  sum: {int(arr.sum())}")
        print(f"  nonzero: {int((arr != 0).sum())}")

    if len(maps) >= 2:
        print()
        print("Pairwise comparisons:")

        for i in range(len(maps)):
            for j in range(i + 1, len(maps)):
                p1, a = maps[i]
                p2, b = maps[j]

                if a.shape != b.shape:
                    print(f"  {p1.name} vs {p2.name}: shape mismatch")
                    continue

                diff = a.astype(np.int64) - b.astype(np.int64)
                print(f"  {p1.name} vs {p2.name}:")
                print(f"    abs diff sum: {int(np.abs(diff).sum())}")
                print(f"    max abs diff: {int(np.abs(diff).max())}")

                # correlation can be undefined for all-zero arrays
                if a.std() > 0 and b.std() > 0:
                    corr = np.corrcoef(a.ravel(), b.ravel())[0, 1]
                    print(f"    correlation: {corr:.4f}")
                else:
                    print("    correlation: undefined")


def maybe_save_figure(maps):
    if not SAVE_FIGURE:
        return

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print()
        print("matplotlib not installed; skipping side-by-side figure")
        return

    if not maps:
        return

    n = len(maps)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 4), squeeze=False)

    for ax, (path, arr) in zip(axes[0], maps):
        im = ax.imshow(arr, cmap="gray")
        ax.set_title(path.name, fontsize=8)
        ax.axis("off")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.tight_layout()
    fig.savefig(FIGURE_PATH, dpi=200)
    print()
    print(f"Saved comparison figure: {FIGURE_PATH}")


def main():
    maps = load_maps(NPY_DIR, PATTERN)
    print_stats(maps)
    maybe_save_figure(maps)


if __name__ == "__main__":
    main()
