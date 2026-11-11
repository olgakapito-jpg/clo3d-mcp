"""Measurements for the women's classic trouser prototype (Müller & Sohn core).

Half-circumference convention:
- waist_half / hip_half are half body girths in cm (Ст / Сб);
- knee_half / hem_half are half leg widths in cm (Шк / Шн);
- all lengths are cm.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TrouserMeasurements:
    size: int = 40
    waist_half: float = 38.0
    hip_half: float = 50.0
    side_length: float = 106.0
    seat_height: float = 26.5
    knee_half: float = 24.0
    hem_half: float = 21.0
    waist_ease: float = 1.0
    front_dart: float = 2.0
    back_dart: float = 3.0
    hem_above_floor: float = 1.0
    hip_drop: float = 1.0
    back_side_extra: float = 2.0
    waistband_height: float = 4.0
    waistband_overlap: float = 3.0

    def __post_init__(self):
        values = (
            self.waist_half, self.hip_half, self.side_length, self.seat_height,
            self.knee_half, self.hem_half, self.waist_ease, self.front_dart,
            self.back_dart, self.hem_above_floor, self.hip_drop,
            self.back_side_extra, self.waistband_height, self.waistband_overlap,
        )
        if any(type(v) not in (int, float) or v <= 0 for v in values):
            raise ValueError("all measurements must be positive numbers")
        if not 20 <= self.size <= 70:
            raise ValueError("size must be 20..70")
        if self.waist_half >= self.hip_half:
            raise ValueError("waist_half must be smaller than hip_half")
        if self.seat_height >= self.side_length:
            raise ValueError("seat_height must be smaller than side_length")
        if self.knee_half >= self.hip_half or self.hem_half >= self.knee_half:
            raise ValueError("expected hem_half < knee_half < hip_half")

    @property
    def hip_line_drop(self) -> float:
        """Distance from waist down to the hip line (A3A7 = Сб/10 + 3)."""
        return self.hip_half / 10 + 3

    @property
    def front_hip_width(self) -> float:
        """Front panel width at the hip line (Шпп = Сб/2 - 1)."""
        return self.hip_half / 2 - 1

    @property
    def back_hip_width(self) -> float:
        """Back panel width at the hip line (Шзп = Сб/2 + 1)."""
        return self.hip_half / 2 + 1

    @property
    def step_width(self) -> float:
        """Front crotch extension (Сб/10 + 0..1)."""
        return self.hip_half / 10 + 1

    @property
    def front_waist_width(self) -> float:
        """Front waist edge including its dart (Ст/2 + dart + Пт/2)."""
        return self.waist_half / 2 + self.front_dart + self.waist_ease / 2

    @property
    def back_waist_width(self) -> float:
        """Back waist edge including its dart (Ст/2 + dart + Пт/2)."""
        return self.waist_half / 2 + self.back_dart + self.waist_ease / 2

    @property
    def knee_front_half(self) -> float:
        return self.knee_half / 2 - 1

    @property
    def hem_front_half(self) -> float:
        return self.hem_half / 2 - 1

    @property
    def knee_height(self) -> float:
        """Knee line from the seat line: Дш/2 - Дш/10."""
        step_length = self.side_length - self.seat_height
        return step_length / 2 - step_length / 10

    @property
    def y_hip(self) -> float:
        return self.seat_height - self.hip_line_drop

    @property
    def y_seat(self) -> float:
        return self.seat_height

    @property
    def y_knee(self) -> float:
        return self.seat_height + self.knee_height

    @property
    def y_hem(self) -> float:
        return self.side_length - self.hem_above_floor

    def with_size(self, **changes) -> "TrouserMeasurements":
        return replace(self, **changes)


SIZE_40 = TrouserMeasurements()

# A small deterministic ladder used by tests and the CLI --size presets.
SIZE_PRESETS = {
    36: TrouserMeasurements(size=36, waist_half=34.0, hip_half=46.0, knee_half=22.0,
                            hem_half=19.0, side_length=104.0, seat_height=25.5),
    38: TrouserMeasurements(size=38, waist_half=36.0, hip_half=48.0, knee_half=23.0,
                            hem_half=20.0, side_length=105.0, seat_height=26.0),
    40: SIZE_40,
    42: TrouserMeasurements(size=42, waist_half=40.0, hip_half=52.0, knee_half=25.0,
                            hem_half=22.0, side_length=107.0, seat_height=27.0),
    44: TrouserMeasurements(size=44, waist_half=42.0, hip_half=54.0, knee_half=26.0,
                            hem_half=23.0, side_length=108.0, seat_height=27.5),
}
