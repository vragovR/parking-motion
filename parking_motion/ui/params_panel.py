import copy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from parking_motion.config import ProcessingParams
from parking_motion.ui.param_spec import PARAM_SPECS, ParamSpec


class ParamsPanel(QScrollArea):
    paramsChanged = Signal(object)

    def __init__(
        self,
        params: ProcessingParams,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._params = copy.deepcopy(params)
        self._widgets: dict[tuple[str, str], QWidget] = {}

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        self.auto_tune_btn = QPushButton("Подобрать параметры")
        self.auto_tune_btn.setEnabled(False)
        self.auto_tune_btn.setToolTip(
            "Подбирает «Площадь», «Мин. площадь блоба» и «Мин. пиковую "
            "площадь» по площади выделенного ROI."
        )
        layout.addWidget(self.auto_tune_btn)
        layout.addSpacing(8)

        for spec in PARAM_SPECS:
            self._add_block(layout, spec)

        layout.addStretch(1)

        self.setWidgetResizable(True)
        self.setWidget(container)
        self.setMinimumWidth(280)

    def params(self) -> ProcessingParams:
        return copy.deepcopy(self._params)

    def apply_thresholds_for_roi(self, roi_pixels: int) -> dict[str, int]:
        if roi_pixels <= 0:
            return {}
        proportions = {
            ("motion", "area_threshold"): 0.010,
            ("motion", "min_contour_area"): 0.0015,
            ("event", "min_peak_area"): 0.015,
        }
        applied: dict[str, int] = {}
        for (kind, attr), proportion in proportions.items():
            widget = self._widgets.get((kind, attr))
            if not isinstance(widget, QSpinBox):
                continue
            new_value = max(1, round(roi_pixels * proportion))
            widget.setValue(new_value)
            applied[attr] = new_value
        return applied

    def _add_block(self, layout: QVBoxLayout, spec: ParamSpec) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(spec.label), stretch=1)
        widget = self._make_widget(spec)
        self._widgets[(spec.target, spec.attr)] = widget
        row.addWidget(widget)
        layout.addLayout(row)
        if spec.hint:
            desc = QLabel(spec.hint)
            desc.setWordWrap(True)
            desc.setStyleSheet("color:#888; font-size:11px;")
            layout.addWidget(desc)
        layout.addSpacing(8)

    def _make_widget(self, spec: ParamSpec) -> QWidget:
        target = self._target_for(spec)
        current = getattr(target, spec.attr)
        if spec.kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(current))
            w.toggled.connect(lambda v, s=spec: self._update(s, bool(v)))
            return w
        if spec.kind == "int":
            spin = QSpinBox()
            spin.setRange(int(spec.minimum), int(spec.maximum))
            spin.setSingleStep(int(spec.step))
            if spec.special_value_text is not None:
                spin.setSpecialValueText(spec.special_value_text)
            spin.setValue(int(current))
            spin.valueChanged.connect(lambda v, s=spec: self._update(s, int(v)))
            return spin
        spin = QDoubleSpinBox()
        spin.setRange(float(spec.minimum), float(spec.maximum))
        spin.setSingleStep(float(spec.step))
        if spec.special_value_text is not None:
            spin.setSpecialValueText(spec.special_value_text)
        spin.setValue(float(current))
        spin.valueChanged.connect(lambda v, s=spec: self._update(s, float(v)))
        return spin

    def _target_for(self, spec: ParamSpec) -> object:
        if spec.target == "motion":
            return self._params.motion
        if spec.target == "event":
            return self._params.event
        return self._params

    def _update(self, spec: ParamSpec, value: object) -> None:
        setattr(self._target_for(spec), spec.attr, value)
        self.paramsChanged.emit(copy.deepcopy(self._params))
