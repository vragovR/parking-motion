from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QVBoxLayout,
    QWidget,
)

SEEK_STEP_MS = 5_000


def format_ms(ms: int) -> str:
    ms = max(0, ms)
    seconds = ms // 1000
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class EventPlayer(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._video = QVideoWidget()
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setVideoOutput(self._video)
        self._player.setAudioOutput(self._audio)
        self._pending_position_ms: int | None = None
        self._user_scrubbing = False

        style = self.style()
        self._play_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self._pause_icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)

        self._play_btn = QPushButton()
        self._play_btn.setIcon(self._play_icon)
        self._play_btn.setToolTip("Воспроизвести / Пауза (Space)")
        self._play_btn.clicked.connect(self._toggle_play)

        self._stop_btn = QPushButton()
        self._stop_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self._stop_btn.setToolTip("Стоп")
        self._stop_btn.clicked.connect(self._on_stop_clicked)

        self._back_btn = QPushButton()
        self._back_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self._back_btn.setToolTip("Назад 5 секунд (←)")
        self._back_btn.clicked.connect(lambda: self._seek_relative(-SEEK_STEP_MS))

        self._fwd_btn = QPushButton()
        self._fwd_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self._fwd_btn.setToolTip("Вперёд 5 секунд (→)")
        self._fwd_btn.clicked.connect(lambda: self._seek_relative(SEEK_STEP_MS))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._slider.sliderMoved.connect(self._on_slider_moved)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setMinimumWidth(120)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        controls = QHBoxLayout()
        controls.setContentsMargins(4, 4, 4, 4)
        controls.addWidget(self._play_btn)
        controls.addWidget(self._stop_btn)
        controls.addWidget(self._back_btn)
        controls.addWidget(self._fwd_btn)
        controls.addWidget(self._slider, stretch=1)
        controls.addWidget(self._time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._video, stretch=1)
        layout.addLayout(controls)

        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def play_at(self, path: Path, t_seconds: float) -> None:
        target_ms = max(0, int(t_seconds * 1000))
        new_url = QUrl.fromLocalFile(str(path))
        self.setFocus()

        if self._player.source() == new_url and self._player.duration() > 0:
            self._pending_position_ms = None
            self._player.setPosition(target_ms)
            if self._player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self._player.play()
            return

        self._pending_position_ms = target_ms
        self._player.stop()
        self._player.setSource(new_url)

    def stop(self) -> None:
        self._player.stop()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Space:
            self._toggle_play()
        elif key == Qt.Key.Key_Left:
            self._seek_relative(-SEEK_STEP_MS)
        elif key == Qt.Key.Key_Right:
            self._seek_relative(SEEK_STEP_MS)
        else:
            super().keyPressEvent(event)

    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_stop_clicked(self) -> None:
        self._player.stop()

    def _seek_relative(self, delta_ms: int) -> None:
        duration = self._player.duration()
        if duration <= 0:
            return
        new_pos = max(0, min(duration, self._player.position() + delta_ms))
        self._player.setPosition(new_pos)

    def _on_slider_pressed(self) -> None:
        self._user_scrubbing = True

    def _on_slider_released(self) -> None:
        self._player.setPosition(self._slider.value())
        self._user_scrubbing = False

    def _on_slider_moved(self, value: int) -> None:
        self._update_time_label(value, self._player.duration())

    def _on_position_changed(self, position_ms: int) -> None:
        if not self._user_scrubbing:
            self._slider.setValue(position_ms)
        self._update_time_label(position_ms, self._player.duration())

    def _on_duration_changed(self, duration_ms: int) -> None:
        self._slider.setRange(0, max(0, duration_ms))
        self._update_time_label(self._player.position(), duration_ms)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._play_btn.setIcon(self._pause_icon)
        else:
            self._play_btn.setIcon(self._play_icon)

    def _update_time_label(self, position_ms: int, duration_ms: int) -> None:
        self._time_label.setText(f"{format_ms(position_ms)} / {format_ms(duration_ms)}")

    @Slot(QMediaPlayer.MediaStatus)
    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if (
            status
            in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
            )
            and self._pending_position_ms is not None
        ):
            target = self._pending_position_ms
            self._pending_position_ms = None
            self._player.play()
            self._player.setPosition(target)
