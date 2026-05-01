import copy
from pathlib import Path

from PySide6.QtCore import QModelIndex, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from parking_motion.config import ProcessingParams, SessionState
from parking_motion.core.events import Event
from parking_motion.ui.events_table import EventsModel
from parking_motion.ui.file_list_panel import FileListPanel
from parking_motion.ui.params_panel import ParamsPanel
from parking_motion.ui.player import EventPlayer
from parking_motion.ui.processing_controller import ProcessingController
from parking_motion.ui.roi_widget import RoiCanvas
from parking_motion.ui.thumbnail_service import ThumbnailService

THUMB_WIDTH = 160
THUMB_HEIGHT = 90


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

        self._events_model = EventsModel()
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._events_model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(1)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Фильтр по имени файла…")
        self._filter_edit.textChanged.connect(self._proxy.setFilterFixedString)

        self._events_view = QTableView()
        self._events_view.setModel(self._proxy)
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
        header.setStretchLastSection(False)
        self._events_view.doubleClicked.connect(self._on_event_double_clicked)

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(self._filter_edit)
        bottom_layout.addWidget(self._events_view)

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

    def _update_run_enabled(self) -> None:
        ok = (
            len(self._session.files) > 0
            and self._session.roi is not None
            and not self._controller.is_running()
        )
        self._run_btn.setEnabled(ok)

    def _on_run_clicked(self) -> None:
        if self._controller.is_running():
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
        self._update_run_enabled()

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
        source_index = self._proxy.mapToSource(index)
        event = self._events_model.event_at(source_index.row())
        if event is None:
            return
        self._top_stack.setCurrentWidget(self._player)
        self._player.play_at(event.source, event.start_s)

    def closeEvent(self, event) -> None:
        self._player.stop()
        self._controller.shutdown(3000)
        self._thumb_service.shutdown()
        super().closeEvent(event)
