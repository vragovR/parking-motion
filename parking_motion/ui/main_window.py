import copy
from pathlib import Path

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSize, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from parking_motion.config import ProcessingParams, SessionState
from parking_motion.core.events import Event
from parking_motion.core.exporter import dedupe_filename, default_clip_filename
from parking_motion.ui.events_table import COLUMNS as EVENT_COLUMNS
from parking_motion.ui.events_table import EventsModel
from parking_motion.ui.export_controller import ExportController
from parking_motion.ui.file_list_panel import FileListPanel
from parking_motion.ui.params_panel import ParamsPanel
from parking_motion.ui.player import EventPlayer
from parking_motion.ui.processing_controller import ProcessingController
from parking_motion.ui.roi_widget import RoiCanvas
from parking_motion.ui.thumbnail_service import ThumbnailService

THUMB_WIDTH = 160
THUMB_HEIGHT = 90
PLAYBACK_LOOKBACK_S = 1.0


class MainWindow(QMainWindow):
    def __init__(self, params: ProcessingParams) -> None:
        super().__init__()
        self._params = params
        self._session = SessionState()

        self._controller = ProcessingController(self)
        self._controller.runStarted.connect(self._on_run_started)
        self._controller.runFinished.connect(self._on_run_finished)
        self._controller.fileStarted.connect(self._on_controller_file_started)
        self._controller.fileProgress.connect(self._on_controller_file_progress)
        self._controller.fileFinished.connect(self._on_controller_file_finished)
        self._controller.overallProgress.connect(self._on_controller_overall_progress)
        self._controller.eventFound.connect(self._on_event_found)
        self._controller.elapsedTick.connect(self._on_elapsed_tick)

        self._export_controller = ExportController(self)
        self._export_controller.exportStarted.connect(self._on_export_started)
        self._export_controller.exportProgress.connect(self._on_export_progress)
        self._export_controller.clipFailed.connect(self._on_export_clip_failed)
        self._export_controller.exportFinished.connect(self._on_export_finished)
        self._export_failures: list[tuple[Event, str]] = []
        self._last_export_dir: str = ""
        self._analysis_complete: bool = False
        self._cancel_requested: bool = False

        self.setWindowTitle("Parking Motion")
        self.resize(1400, 900)

        self._thumb_service = ThumbnailService(max_workers=2, parent=self)
        self._thumb_service.eventThumbnailReady.connect(self._on_event_thumb_ready)

        self._file_panel = FileListPanel(self._thumb_service)
        self._file_panel.filesSelected.connect(self._on_files_selected)
        self._file_panel.fileClicked.connect(self._on_file_clicked)

        self._params_panel = ParamsPanel(params)
        self._params_panel.paramsChanged.connect(self._on_params_changed)

        self._run_btn = QPushButton("Запустить анализ")
        self._run_btn.clicked.connect(self._on_run_clicked)
        self._run_btn.setEnabled(False)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFormat("%v из %m")
        self._progress.setVisible(False)

        self._elapsed_label = QLabel("")
        self._elapsed_label.setStyleSheet("color:#888;")
        self._elapsed_label.setVisible(False)

        self._params_toggle_btn = QPushButton("⚙ Параметры")
        self._params_toggle_btn.setCheckable(True)
        self._params_toggle_btn.setChecked(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._params_toggle_btn)
        left_layout.addWidget(self._file_panel, stretch=1)
        left_layout.addWidget(self._run_btn)
        left_layout.addWidget(self._progress)
        left_layout.addWidget(self._elapsed_label)

        self._roi_canvas = RoiCanvas()
        self._roi_canvas.roiSelected.connect(self._on_roi_selected)
        self._player = EventPlayer()

        self._top_stack = QStackedWidget()
        self._top_stack.addWidget(self._roi_canvas)
        self._top_stack.addWidget(self._player)

        self._params_panel.auto_tune_btn.clicked.connect(self._on_auto_tune_clicked)

        self._events_model = EventsModel()
        self._events_model.rowsInserted.connect(self._on_rows_inserted)
        self._events_model.modelReset.connect(self._update_export_btn_enabled)

        self._download_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        self._download_col = len(EVENT_COLUMNS) - 1
        self._viewed_col = len(EVENT_COLUMNS) - 2

        self._events_view = QTableView()
        self._events_view.setModel(self._events_model)
        self._events_view.setSortingEnabled(False)
        self._events_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._events_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._events_view.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self._events_view.verticalHeader().setDefaultSectionSize(THUMB_HEIGHT + 6)
        header = self._events_view.horizontalHeader()
        header.setSectionsClickable(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, THUMB_WIDTH + 12)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(self._viewed_col, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self._viewed_col, 36)
        header.setSectionResizeMode(self._download_col, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self._download_col, 44)
        header.setStretchLastSection(False)
        self._events_view.doubleClicked.connect(self._on_event_double_clicked)

        self._export_btn = QPushButton("Экспорт всех…")
        self._export_btn.setToolTip(
            "Сохранить все события из таблицы. Доступно после завершения анализа."
        )
        self._export_btn.clicked.connect(self._on_export_all_clicked)
        self._export_btn.setEnabled(False)
        self._export_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._export_progress = QProgressBar()
        self._export_progress.setRange(0, 1)
        self._export_progress.setValue(0)
        self._export_progress.setFormat("Экспорт %v из %m")
        self._export_progress.setVisible(False)

        self._export_cancel_btn = QPushButton("Отменить")
        self._export_cancel_btn.clicked.connect(self._export_controller.cancel)
        self._export_cancel_btn.setVisible(False)
        self._export_cancel_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._show_viewed_chk = QCheckBox("Показывать просмотренные")
        self._show_viewed_chk.setChecked(False)
        self._show_viewed_chk.toggled.connect(self._on_show_viewed_toggled)

        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 0, 0, 0)
        export_row.addWidget(self._show_viewed_chk)
        export_row.addWidget(self._export_btn)
        export_row.addWidget(self._export_progress, stretch=1)
        export_row.addWidget(self._export_cancel_btn)
        export_row.addStretch(1)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 8)
        bottom_layout.addWidget(self._events_view)
        bottom_layout.addLayout(export_row)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.addWidget(self._top_stack)
        right_split.addWidget(bottom)
        right_split.setStretchFactor(0, 1)
        right_split.setStretchFactor(1, 3)
        right_split.setSizes([260, 640])

        self._params_panel.setVisible(False)
        self._params_toggle_btn.toggled.connect(self._params_panel.setVisible)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.addWidget(left)
        main_split.addWidget(right_split)
        main_split.addWidget(self._params_panel)
        main_split.setStretchFactor(0, 0)
        main_split.setStretchFactor(1, 1)
        main_split.setStretchFactor(2, 0)
        main_split.setSizes([420, 660, 320])

        self.setCentralWidget(main_split)

    def _on_params_changed(self, snapshot: ProcessingParams) -> None:
        self._params = snapshot

    def _on_auto_tune_clicked(self) -> None:
        roi = self._session.roi
        if roi is None or roi[2] <= 0 or roi[3] <= 0:
            return
        self._params_panel.apply_thresholds_for_roi(roi[2] * roi[3])

    def _on_files_selected(self, paths: list[Path]) -> None:
        if self._controller.is_running():
            return
        self._session.files = list(paths)
        self._file_panel.set_files(self._session.files)
        self._update_run_enabled()

    def _on_event_thumb_ready(self, path_str: str, start_s: float, image: QImage) -> None:
        self._events_model.set_thumb_for_event(Path(path_str), start_s, QPixmap.fromImage(image))

    def _on_file_clicked(self, path: Path) -> None:
        self._top_stack.setCurrentWidget(self._roi_canvas)
        self._player.stop()
        self._roi_canvas.set_video(path)
        self._roi_canvas.set_roi_from_frame(self._session.roi)

    def _on_roi_selected(self, roi: tuple) -> None:
        self._session.roi = tuple(int(v) for v in roi)
        self._update_run_enabled()
        self._update_auto_tune_enabled()

    def _update_auto_tune_enabled(self) -> None:
        roi = self._session.roi
        ok = roi is not None and roi[2] > 0 and roi[3] > 0
        self._params_panel.auto_tune_btn.setEnabled(ok)

    def _update_run_enabled(self) -> None:
        ok = (
            len(self._session.files) > 0
            and self._session.roi is not None
            and not self._controller.is_running()
        )
        self._run_btn.setEnabled(ok)

    def _on_run_clicked(self) -> None:
        if self._controller.is_running():
            self._cancel_requested = True
            self._controller.cancel()
            self._run_btn.setEnabled(False)
            self._run_btn.setText("Отмена…")
            return
        if not self._session.files or self._session.roi is None:
            QMessageBox.warning(self, "Не готово", "Выберите файлы и обведите ROI на стоп-кадре.")
            return

        files = list(self._session.files)
        self._events_model.clear()
        self._file_panel.reset_for_new_run()
        self._analysis_complete = False
        self._cancel_requested = False
        self._update_export_btn_enabled()

        self._controller.start(files, self._session.roi, copy.deepcopy(self._params))

    def _on_run_started(self, total: int) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._elapsed_label.setVisible(True)
        self._run_btn.setText("Отменить")
        self._file_panel.set_selection_enabled(False)
        self._run_btn.setEnabled(True)

    def _on_run_finished(self, stranded: list[Path]) -> None:
        for path in stranded:
            self._file_panel.mark_idle(path)
        self._run_btn.setText("Запустить анализ")
        self._file_panel.set_selection_enabled(True)
        self._analysis_complete = not self._cancel_requested
        self._update_run_enabled()
        self._update_export_btn_enabled()

    def _on_event_found(self, event: Event) -> None:
        self._events_model.add_event(event, None)
        self._thumb_service.request_event_thumbnail(
            event.source,
            event.start_s,
            event.start_s + 1.0,
            THUMB_WIDTH,
            THUMB_HEIGHT,
        )

    def _on_controller_file_started(self, path: Path) -> None:
        self._file_panel.mark_progress(path, 0, active=True)

    def _on_controller_file_progress(self, path: Path, percent: int, eta: float) -> None:
        self._file_panel.mark_progress(path, percent, active=True)

    def _on_controller_file_finished(self, path: Path) -> None:
        self._file_panel.mark_progress(path, 100, active=False)

    def _on_controller_overall_progress(self, completed: int, total: int) -> None:
        self._progress.setValue(completed)

    def _on_elapsed_tick(self, text: str) -> None:
        self._elapsed_label.setText(f"Время: {text}")

    def _on_event_double_clicked(self, index: QModelIndex) -> None:
        if index.column() in (self._download_col, self._viewed_col):
            return
        event = self._events_model.event_at(index.row())
        if event is None:
            return
        self._top_stack.setCurrentWidget(self._player)
        self._player.play_at(event.source, max(0.0, event.start_s - PLAYBACK_LOOKBACK_S))

    def _on_rows_inserted(self, _parent: QModelIndex, first: int, last: int) -> None:
        for row in range(first, last + 1):
            self._install_viewed_checkbox(row)
            self._install_download_button(row)
        self._update_export_btn_enabled()

    def _install_download_button(self, row: int) -> None:
        index = self._events_model.index(row, self._download_col)
        persistent = QPersistentModelIndex(index)
        btn = QPushButton()
        btn.setIcon(self._download_icon)
        btn.setToolTip("Сохранить клип как…")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setFixedSize(32, 28)
        btn.clicked.connect(lambda _checked=False, p=persistent: self._on_download_clicked(p))

        wrapper = QWidget(self._events_view)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        self._events_view.setIndexWidget(index, wrapper)

    def _on_download_clicked(self, persistent: QPersistentModelIndex) -> None:
        if not persistent.isValid():
            return
        event = self._events_model.event_at(persistent.row())
        if event is None:
            return
        self._on_export_one(event)

    def _install_viewed_checkbox(self, row: int) -> None:
        index = self._events_model.index(row, self._viewed_col)
        persistent = QPersistentModelIndex(index)
        chk = QCheckBox()
        chk.setToolTip("Отметить как просмотренное")
        chk.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        chk.setChecked(self._events_model.is_viewed(row))
        chk.toggled.connect(lambda checked, p=persistent: self._on_viewed_toggled(p, checked))

        wrapper = QWidget(self._events_view)
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(chk, 0, Qt.AlignmentFlag.AlignCenter)
        self._events_view.setIndexWidget(index, wrapper)

    def _on_viewed_toggled(self, persistent: QPersistentModelIndex, checked: bool) -> None:
        if not persistent.isValid():
            return
        row = persistent.row()
        self._events_model.set_viewed(row, checked)
        self._apply_row_visibility(row)
        self._update_export_btn_enabled()

    def _apply_row_visibility(self, row: int) -> None:
        hide = self._events_model.is_viewed(row) and not self._show_viewed_chk.isChecked()
        self._events_view.setRowHidden(row, hide)

    def _on_show_viewed_toggled(self, _checked: bool) -> None:
        for row in range(self._events_model.rowCount()):
            self._apply_row_visibility(row)
        self._update_export_btn_enabled()

    def _visible_event_count(self) -> int:
        include_viewed = self._show_viewed_chk.isChecked()
        count = 0
        for row in range(self._events_model.rowCount()):
            if include_viewed or not self._events_model.is_viewed(row):
                count += 1
        return count

    def _update_export_btn_enabled(self) -> None:
        enabled = (
            self._analysis_complete
            and self._visible_event_count() > 0
            and not self._export_controller.is_running()
        )
        self._export_btn.setEnabled(enabled)

    def _on_export_one(self, event: Event) -> None:
        if self._export_controller.is_running():
            QMessageBox.information(
                self,
                "Экспорт",
                "Дождитесь завершения текущего экспорта или отмените его.",
            )
            return
        default_name = default_clip_filename(event.source, event.start_s, event.duration_s)
        default_dir = self._last_export_dir or str(event.source.parent)
        default_path = str(Path(default_dir) / default_name)
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить клип",
            default_path,
            "MP4 (*.mp4)",
        )
        if not path_str:
            return
        dst = Path(path_str)
        self._last_export_dir = str(dst.parent)
        self._export_failures = []
        self._export_controller.export_one(event, dst, self._params.export)

    def _on_export_all_clicked(self) -> None:
        if self._export_controller.is_running():
            self._export_controller.cancel()
            return
        if self._events_model.rowCount() == 0:
            QMessageBox.information(self, "Экспорт", "Нет событий для экспорта.")
            return
        include_viewed = self._show_viewed_chk.isChecked()
        events: list[Event] = []
        for row in range(self._events_model.rowCount()):
            if not include_viewed and self._events_model.is_viewed(row):
                continue
            event = self._events_model.event_at(row)
            if event is not None:
                events.append(event)
        if not events:
            QMessageBox.information(self, "Экспорт", "Нет событий для экспорта.")
            return

        box = QMessageBox(self)
        box.setWindowTitle("Экспорт")
        box.setText(f"Сохранить {len(events)} событий:")
        single_btn = box.addButton("В один файл", QMessageBox.ButtonRole.AcceptRole)
        multi_btn = box.addButton("Отдельными файлами", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is single_btn:
            self._start_concat_export(events)
        elif clicked is multi_btn:
            self._start_multi_export(events)

    def _start_multi_export(self, events: list[Event]) -> None:
        default_dir = self._last_export_dir or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, "Выберите папку для клипов", default_dir)
        if not directory:
            return
        dest = Path(directory)
        jobs: list[tuple[Event, Path]] = []
        taken: set[str] = set()
        for event in events:
            base = default_clip_filename(event.source, event.start_s, event.duration_s)
            unique = dedupe_filename(dest, base, taken)
            taken.add(unique)
            jobs.append((event, dest / unique))
        if not jobs:
            return
        self._last_export_dir = str(dest)
        self._export_failures = []
        self._export_controller.export_many(jobs, self._params.export)

    def _start_concat_export(self, events: list[Event]) -> None:
        first = events[0]
        default_name = f"{first.source.stem}_concat_{len(events)}_events.mp4"
        default_dir = self._last_export_dir or str(first.source.parent)
        default_path = str(Path(default_dir) / default_name)
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить объединённый клип",
            default_path,
            "MP4 (*.mp4)",
        )
        if not path_str:
            return
        dst = Path(path_str)
        self._last_export_dir = str(dst.parent)
        self._export_failures = []
        self._export_controller.export_concat(events, dst, self._params.export)

    def _on_export_started(self, total: int) -> None:
        self._export_progress.setRange(0, max(1, total))
        self._export_progress.setValue(0)
        self._export_progress.setVisible(True)
        self._export_cancel_btn.setVisible(True)
        self._update_export_btn_enabled()

    def _on_export_progress(self, done: int, total: int) -> None:
        self._export_progress.setRange(0, max(1, total))
        self._export_progress.setValue(done)

    def _on_export_clip_failed(self, event: Event, error: str) -> None:
        self._export_failures.append((event, error))

    def _on_export_finished(self) -> None:
        self._export_progress.setVisible(False)
        self._export_cancel_btn.setVisible(False)
        self._update_export_btn_enabled()
        if self._export_failures:
            lines = [
                f"{ev.source.name} @ {ev.start_s:.1f}s — {err}" for ev, err in self._export_failures
            ]
            QMessageBox.warning(
                self,
                "Экспорт завершён с ошибками",
                "Не удалось экспортировать клипы:\n\n" + "\n".join(lines),
            )
        self._export_failures = []

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._controller.shutdown(3000)
        self._export_controller.shutdown(3000)
        self._thumb_service.shutdown()
        super().closeEvent(event)
