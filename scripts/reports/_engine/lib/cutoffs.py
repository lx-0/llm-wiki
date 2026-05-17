"""Config-driven score banding (PHQ-9 → "mild/moderate/severe", etc).

An instrument declares its cutoffs as an ordered list in
`cutoffs.yaml`:

```yaml
- {min: 0,  max: 4,  band: "minimal"}
- {min: 5,  max: 9,  band: "mild"}
- {min: 10, max: 14, band: "moderate"}
- {min: 15, max: 19, band: "moderately-severe"}
- {min: 20, max: 27, band: "severe"}
```

Both bounds are INCLUSIVE. The bands must cover the instrument's valid
score range without gaps or overlaps; `Cutoffs.validate()` enforces
this at load time so a malformed cutoffs.yaml fails fast rather than
silently silently returning the wrong band at a boundary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """One labelled band in a cutoffs ladder. Bounds inclusive."""

    min: int
    max: int
    band: str

    def contains(self, score: int) -> bool:
        return self.min <= score <= self.max


@dataclass(frozen=True)
class Cutoffs:
    """Ordered ladder of bands. Use `band_for(score)` to look up."""

    bands: tuple[Band, ...]

    @classmethod
    def from_list(cls, raw: list[dict]) -> "Cutoffs":
        """Build from the parsed yaml list. Validates contiguity."""
        if not raw:
            raise ValueError("cutoffs.yaml must declare at least one band")
        bands = tuple(
            Band(min=int(entry["min"]), max=int(entry["max"]), band=str(entry["band"]))
            for entry in raw
        )
        cutoffs = cls(bands=bands)
        cutoffs.validate()
        return cutoffs

    def validate(self) -> None:
        """Reject empty / unsorted / overlapping / gapped bands."""
        if not self.bands:
            raise ValueError("Cutoffs must have at least one band")
        for b in self.bands:
            if b.max < b.min:
                raise ValueError(f"Band {b.band!r}: max {b.max} < min {b.min}")
        sorted_bands = sorted(self.bands, key=lambda b: b.min)
        if list(sorted_bands) != list(self.bands):
            raise ValueError(
                "Cutoffs must be declared in ascending order by `min`"
            )
        for prev, nxt in zip(self.bands, self.bands[1:]):
            expected_next_min = prev.max + 1
            if nxt.min != expected_next_min:
                raise ValueError(
                    f"Bands {prev.band!r}..{nxt.band!r} are not contiguous: "
                    f"expected next min={expected_next_min}, got {nxt.min}"
                )

    @property
    def range(self) -> tuple[int, int]:
        return (self.bands[0].min, self.bands[-1].max)

    def band_for(self, score: int) -> str:
        """Look up the band for an integer score. Raises if out-of-range."""
        lo, hi = self.range
        if not (lo <= score <= hi):
            raise ValueError(
                f"Score {score} is outside the declared cutoff range {lo}..{hi}"
            )
        for b in self.bands:
            if b.contains(score):
                return b.band
        # Unreachable if validate() passed: bands cover [lo..hi] contiguously.
        raise AssertionError(
            f"Score {score} fell through cutoffs ladder despite valid range"
        )
