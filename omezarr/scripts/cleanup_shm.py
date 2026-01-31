"""Clean up stale shared memory segments left by crashed ome-zarr-writer processes.

Usage:
    uv run python omezarr/scripts/cleanup_shm.py
    uv run python omezarr/scripts/cleanup_shm.py --prefix ring  # custom prefix
"""

import argparse
from multiprocessing import shared_memory


def cleanup(prefix: str = "ring", max_slots: int = 10, max_levels: int = 5) -> int:
    """Remove stale shared memory segments matching the naming convention.

    Returns the number of segments cleaned.
    """
    suffixes = ["", "_s0", "_s1", "_s2", "_s3", "_s4"]
    cleaned = 0

    for slot in range(max_slots):
        for level in range(max_levels):
            for suffix in suffixes:
                name = f"{prefix}_{slot}_{level}{suffix}"
                try:
                    shm = shared_memory.SharedMemory(name=name, create=False)
                    shm.close()
                    shm.unlink()
                    print(f"  Cleaned: {name}")
                    cleaned += 1
                except FileNotFoundError:
                    pass

    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up stale shared memory segments")
    parser.add_argument("--prefix", default="ring", help="Shared memory name prefix (default: ring)")
    parser.add_argument("--max-slots", type=int, default=10, help="Max slot indices to check (default: 10)")
    parser.add_argument("--max-levels", type=int, default=5, help="Max level indices to check (default: 5)")
    args = parser.parse_args()

    print(f"Scanning for stale shared memory segments with prefix '{args.prefix}'...")
    cleaned = cleanup(prefix=args.prefix, max_slots=args.max_slots, max_levels=args.max_levels)

    if cleaned:
        print(f"Removed {cleaned} stale segment(s).")
    else:
        print("No stale segments found.")


if __name__ == "__main__":
    main()
