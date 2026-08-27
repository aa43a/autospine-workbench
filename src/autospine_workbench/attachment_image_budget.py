"""Reusable incremental resource ceilings for attachment image admission."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AttachmentImageBudget:
    max_images: int
    max_image_bytes: int
    max_total_bytes: int
    max_image_pixels: int
    max_total_pixels: int

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in (
            self.max_images, self.max_image_bytes, self.max_total_bytes,
            self.max_image_pixels, self.max_total_pixels,
        )):
            raise ValueError(
                "Attachment image budget must contain positive integers"
            )


@dataclass(slots=True)
class AttachmentImageBudgetTracker:
    """Track bytes/pixels without retaining or decoding extra images."""

    budget: AttachmentImageBudget | None
    image_count: int = 0
    total_bytes: int = 0
    total_pixels: int = 0

    def allows_inventory(self, count: int) -> bool:
        return self.budget is None or count <= self.budget.max_images

    def add_snapshot(self, byte_count: int) -> bool:
        self.image_count += 1
        self.total_bytes += byte_count
        return self.budget is None or (
            self.image_count <= self.budget.max_images
            and byte_count <= self.budget.max_image_bytes
            and self.total_bytes <= self.budget.max_total_bytes
        )

    def add_decoded(self, width: int, height: int) -> bool:
        pixels = width * height
        self.total_pixels += pixels
        return self.budget is None or (
            pixels <= self.budget.max_image_pixels
            and self.total_pixels <= self.budget.max_total_pixels
        )
