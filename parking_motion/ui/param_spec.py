from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ParamSpec:
    target: Literal["motion", "event", "processing"]
    attr: str
    label: str
    kind: Literal["int", "float", "bool"]
    minimum: float = 0
    maximum: float = 1_000_000
    step: float = 1
    hint: str = ""
    special_value_text: str | None = None


PARAM_SPECS: list[ParamSpec] = [
    ParamSpec(
        target="processing",
        attr="frame_skip",
        label="Прореживание",
        kind="int",
        minimum=1,
        maximum=60,
        step=1,
        hint=(
            "Сколько кадров пропускать между анализируемыми. Чем больше — тем "
            "быстрее анализ, но мелкие/быстрые движения легче пропустить."
        ),
    ),
    ParamSpec(
        target="motion",
        attr="area_threshold",
        label="Площадь, px²",
        kind="int",
        minimum=0,
        maximum=1_000_000,
        step=50,
        hint=(
            "Минимальная суммарная площадь движущихся пикселей в ROI (px²), "
            "чтобы кадр считался «движением». Меньше — чувствительнее."
        ),
    ),
    ParamSpec(
        target="motion",
        attr="min_contour_area",
        label="Мин. площадь блоба, px²",
        kind="int",
        minimum=0,
        maximum=100_000,
        step=50,
        hint=(
            "Минимальная площадь одного движущегося блоба (px²), чтобы он "
            "учитывался. Отбрасывает мелкий шум (листья, дождь, пиксельные "
            "блики) до суммирования общей площади."
        ),
    ),
    ParamSpec(
        target="motion",
        attr="mog_detect_shadows",
        label="Учёт теней",
        kind="bool",
        hint=(
            "Пытаться отличать тень от объекта. Полезно, если ловятся тени; "
            "немного снижает скорость."
        ),
    ),
    ParamSpec(
        target="event",
        attr="merge_gap_s",
        label="Склейка, с",
        kind="float",
        minimum=0.0,
        maximum=60.0,
        step=0.1,
        hint=(
            "Если пропадание движения короче этого времени — событие не "
            "разбивается. Больше → ближние всплески склеиваются в одно событие."
        ),
    ),
    ParamSpec(
        target="event",
        attr="min_duration_s",
        label="Мин. длительность, с",
        kind="float",
        minimum=0.0,
        maximum=60.0,
        step=0.1,
        hint=("Минимальная длительность события. Короткие всплески (шум, бабочка) отбрасываются."),
    ),
    ParamSpec(
        target="event",
        attr="min_motion_frames",
        label="Мин. кадров движения",
        kind="int",
        minimum=1,
        maximum=1000,
        step=1,
        hint=(
            "Минимум сэмплов с движением внутри события. Помогает выкинуть "
            "одиночные блипы (компрессия, мерцание)."
        ),
    ),
    ParamSpec(
        target="event",
        attr="min_peak_area",
        label="Мин. пиковая площадь, px²",
        kind="int",
        minimum=0,
        maximum=1_000_000,
        step=100,
        hint=(
            "Самый «громкий» кадр события должен превышать этот порог. Режет "
            "слабые события, которые еле-еле прошли per-frame порог площади."
        ),
    ),
    ParamSpec(
        target="event",
        attr="max_event_duration_s",
        label="Макс. длительность, с",
        kind="float",
        minimum=0.0,
        maximum=300.0,
        step=0.5,
        hint=(
            "Максимальная длительность одного события (0 — без ограничения). "
            "Если движение длится дольше — событие закрывается принудительно."
        ),
    ),
    ParamSpec(
        target="processing",
        attr="parallel_workers",
        label="Потоков",
        kind="int",
        minimum=1,
        maximum=8,
        step=1,
        hint="Сколько файлов обрабатывать параллельно.",
    ),
]
