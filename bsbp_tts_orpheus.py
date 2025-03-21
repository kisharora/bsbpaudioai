import os
os.environ["VLLM_CPU_KVCACHE_SPACE"] = "8"

import sys
import vllm
from datetime import datetime
import time
import traceback
from PyQt6.QtWidgets import (QApplication, QMainWindow, QStyle, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QComboBox, QSlider, QPushButton, QLabel, QFileDialog, QStyledItemDelegate, QStyleOptionViewItem)
from PyQt6.QtCore import Qt, QTimer, QUrl, QThread, pyqtSignal, QSize, QRect
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QIcon, QPainter, QBrush, QColor

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from orpheus_tts import OrpheusModel
    import wave
    import torch
except ImportError:
    print("Error: Please install the required dependencies: pip install orpheus-speech vllm torch")
    sys.exit(1)

class AudioGenerationThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model, text, voice, speed):
        super().__init__()
        self.model = model
        self.text = text
        self.voice = voice
        self.speed = speed

    def run(self):
        try:
            self.progress.emit("Starting audio generation...")
            total_start = time.time()

            prompt = f"{self.voice}: {self.text}"
            temperature = 0.7 * self.speed
            repetition_penalty = max(1.1, self.speed)
            generation_start = time.time()
            syn_tokens = self.model.generate_speech(
                prompt=prompt,
                voice=self.voice,
                temperature=temperature,
                repetition_penalty=repetition_penalty
            )
            generation_time = time.time() - generation_start

            combine_start = time.time()
            with wave.open("out.wav", "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)

                total_frames = 0
                for audio_chunk in syn_tokens:
                    frame_count = len(audio_chunk) // (wf.getsampwidth() * wf.getnchannels())
                    total_frames += frame_count
                    wf.writeframes(audio_chunk)
                duration = total_frames / wf.getframerate()

            combine_time = time.time() - combine_start
            total_time = time.time() - total_start
            self.progress.emit("Audio saved to out.wav.")
            self.progress.emit(f"<span style='color:#F97316'>Generation time: {generation_time:.2f} seconds</span>")
            self.progress.emit(f"<span style='color:#F97316'>Combine time: {combine_time:.2f} seconds</span>")
            self.progress.emit(f"<span style='color:#F97316'>Total time: {total_time:.2f} seconds</span>")
            self.finished.emit()
        except Exception as e:
            self.error.emit(f"Error during audio generation: {str(e)}")

class CircularProgressIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.setFixedSize(50, 50)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.start(50)

    def rotate(self):
        self.angle = (self.angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self.angle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#F97316")))
        for i in range(8):
            painter.drawEllipse(QRect(-5, -20, 10, 10))
            painter.rotate(45)

class VoiceDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        try:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            painter.save()
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, QColor("#F97316"))
            elif option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, QColor("#4B5563"))
            text = opt.text
            painter.setPen(QColor("#D1D5DB"))
            painter.drawText(option.rect.adjusted(5, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
            painter.restore()
        except Exception as e:
            print(f"Error in VoiceDelegate.paint: {str(e)}")

    def sizeHint(self, option, index):
        return QSize(200, 30)

class BSBPTTSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BSBP TTS - Orpheus")
        self.setStyleSheet("""
            QMainWindow { background-color: #1C2526; color: #D1D5DB; font-family: 'Roboto', sans-serif; }
            QTextEdit { background-color: #374151; color: #D1D5DB; border: 1px solid #F97316; border-radius: 5px; padding: 5px; }
            QComboBox { background-color: #374151; color: #D1D5DB; border: 1px solid #F97316; border-radius: 5px; padding: 5px; }
            QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border-left: 1px solid #F97316; }
            QComboBox::down-arrow { width: 10px; height: 10px; image: none; }
            QComboBox QAbstractItemView { background-color: #374151; color: #D1D5DB; selection-background-color: #F97316; selection-color: #FFFFFF; border: 1px solid #F97316; }
            QPushButton { background-color: #F97316; color: #FFFFFF; border-radius: 5px; padding: 10px; font-weight: bold; }
            QPushButton:hover { background-color: #EA580C; }
            QPushButton:disabled { background-color: #6B7280; color: #A1A1AA; }
            QSlider::groove:horizontal { background: #F97316; height: 8px; border-radius: 4px; }
            QSlider::handle:horizontal { background: #FFFFFF; width: 16px; height: 16px; border-radius: 8px; margin: -4px 0; }
            QLabel { color: #D1D5DB; }
        """)
        self.setGeometry(100, 100, 800, 600)

        if os.path.exists("logo.png"):
            self.setWindowIcon(QIcon("logo.png"))
        else:
            print("Warning: logo.png not found.")

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(150)
        main_layout.addWidget(QLabel("Status Log"))
        main_layout.addWidget(self.logs)

        self.text_input = QTextEdit()
        self.text_input.setAcceptRichText(False)
        self.text_input.setText("""First up, let’s imagine Keanu Reeves in a futuristic cyberpunk café. Neon lights, a glowing blue drink in his hand. Let’s type that in and see what we get.

And here it is... Whoa! This actually looks straight out of a sci-fi movie. The neon reflections, the atmosphere—it’s like John Wick just stepped into Blade Runner.

Or... well, this is interesting. I mean, Keanu Reeves IS kind of there, but why does he look like he’s part toaster? Maybe AI still has some work to do.""")
        main_layout.addWidget(QLabel("Enter Text to Convert"))
        main_layout.addWidget(self.text_input)

        settings_layout = QHBoxLayout()
        left_settings = QVBoxLayout()
        self.voice_combo = QComboBox()
        self.voice_combo.setItemDelegate(VoiceDelegate())
        self.all_voices = ["tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe"]
        self.voice_combo.addItems(self.all_voices)
        left_settings.addWidget(QLabel("Voice"))
        left_settings.addWidget(self.voice_combo)

        speed_layout = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20)
        self.speed_slider.setValue(10)
        self.speed_label = QLabel("1.0x")
        self.speed_slider.valueChanged.connect(self.update_speed_label)
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        left_settings.addWidget(QLabel("Speed"))
        left_settings.addLayout(speed_layout)

        settings_layout.addLayout(left_settings)

        self.player_widget = QWidget()
        self.player_widget.setVisible(False)
        player_layout = QVBoxLayout(self.player_widget)
        player_controls = QHBoxLayout()
        self.play_button = QPushButton("▶")
        self.play_button.setFixedSize(40, 40)
        self.play_button.setStyleSheet("border-radius: 20px;")
        self.play_button.clicked.connect(self.toggle_play)
        player_controls.addWidget(self.play_button)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        player_controls.addWidget(self.seek_slider)

        self.time_label = QLabel("00:00 / 00:00")
        player_controls.addWidget(self.time_label)
        player_layout.addLayout(player_controls)

        settings_layout.addWidget(self.player_widget)
        main_layout.addLayout(settings_layout)

        buttons_layout = QHBoxLayout()
        self.generate_button = QPushButton("Generate Audio")
        self.generate_button.clicked.connect(self.generate_audio)
        buttons_layout.addWidget(self.generate_button)

        self.save_button = QPushButton("Save Audio")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_audio)
        buttons_layout.addWidget(self.save_button)
        main_layout.addLayout(buttons_layout)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.update_seek_slider)
        self.player.durationChanged.connect(self.update_duration)
        self.seek_slider.sliderMoved.connect(self.seek_audio)
        self.player.mediaStatusChanged.connect(self.handle_media_status)

        self.loading_overlay = QWidget(self)
        self.loading_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.8);")
        self.loading_overlay.setVisible(False)
        loading_layout = QVBoxLayout(self.loading_overlay)
        self.progress_indicator = CircularProgressIndicator()
        loading_layout.addWidget(self.progress_indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        self.timer_label = QLabel("Time Elapsed: 00:00")
        self.timer_label.setStyleSheet("color: #D1D5DB; font-size: 16px;")
        loading_layout.addWidget(self.timer_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_timer_label)
        self.elapsed_time = 0

        self.model = None
        self.initialize_model()

    def resizeEvent(self, event):
        self.loading_overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def update_timer_label(self):
        self.elapsed_time += 1
        minutes = self.elapsed_time // 60
        seconds = self.elapsed_time % 60
        self.timer_label.setText(f"Time Elapsed: {minutes:02d}:{seconds:02d}")

    def initialize_model(self):
        self.show_loading_screen("Initializing Orpheus TTS model...")
        try:
            self.logs.append("Loading Orpheus-3b-0.1-ft from Hugging Face...")
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            self.logs.append(f"Detected device: {device}")
            self.logs.append(f"PyTorch version: {torch.__version__}")
            self.logs.append(f"vLLM version: {vllm.__version__}")
            self.model = OrpheusModel(
                model_name="canopylabs/orpheus-3b-0.1-ft",
                max_model_len=32768,
                dtype=torch.float16,  # Use FP16 for MPS compatibility
                device=device
            )
            self.logs.append(f"Orpheus model initialized successfully on {device}.")
        except Exception as e:
            self.logs.append(f"Error initializing Orpheus model: {str(e)}")
            self.logs.append(f"Traceback: {traceback.format_exc()}")
            self.generate_button.setEnabled(False)
        finally:
            self.hide_loading_screen()

    def update_speed_label(self):
        speed = self.speed_slider.value() / 10.0
        self.speed_label.setText(f"{speed:.1f}x")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setText("▶")
        else:
            self.player.play()
            self.play_button.setText("⏸")

    def handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.play_button.setText("▶")
            self.player.setPosition(0)

    def update_seek_slider(self, position):
        self.seek_slider.setValue(position)
        duration = self.player.duration()
        self.seek_slider.setRange(0, duration)
        pos_minutes = position // 60000
        pos_seconds = (position % 60000) // 1000
        dur_minutes = duration // 60000
        dur_seconds = (duration % 60000) // 1000
        self.time_label.setText(f"{pos_minutes:02d}:{pos_seconds:02d} / {dur_minutes:02d}:{dur_seconds:02d}")

    def update_duration(self):
        duration = self.player.duration()
        self.seek_slider.setRange(0, duration)
        dur_minutes = duration // 60000
        dur_seconds = (duration % 60000) // 1000
        self.time_label.setText(f"00:00 / {dur_minutes:02d}:{dur_seconds:02d}")

    def seek_audio(self):
        self.player.setPosition(self.seek_slider.value())

    def generate_audio(self):
        self.show_loading_screen("Generating audio...")
        self.player.stop()
        self.play_button.setText("▶")
        self.player_widget.setVisible(False)
        self.save_button.setEnabled(False)

        text = self.text_input.toPlainText()
        voice = self.voice_combo.currentText()
        speed = self.speed_slider.value() / 10.0

        self.logs.append(f"Input text length: {len(text)} characters")

        self.audio_thread = AudioGenerationThread(self.model, text, voice, speed)
        self.audio_thread.progress.connect(self.logs.append)
        self.audio_thread.finished.connect(self.on_audio_generation_finished)
        self.audio_thread.error.connect(self.on_audio_generation_error)
        self.audio_thread.start()

    def on_audio_generation_finished(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.update_seek_slider)
        self.player.durationChanged.connect(self.update_duration)
        self.seek_slider.sliderMoved.connect(self.seek_audio)
        self.player.mediaStatusChanged.connect(self.handle_media_status)

        self.player.setSource(QUrl.fromLocalFile("out.wav"))
        start_time = time.time()
        while self.player.duration() == 0 and (time.time() - start_time) < 10:
            QApplication.processEvents()
            time.sleep(0.1)
        self.update_duration()
        self.player_widget.setVisible(True)
        self.save_button.setEnabled(True)
        self.hide_loading_screen()

    def on_audio_generation_error(self, error_message):
        self.logs.append(error_message)
        self.hide_loading_screen()

    def save_audio(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"bsbp_tts_{timestamp}.wav"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Audio File", default_filename, "WAV Files (*.wav);;All Files (*)")
        if file_path:
            try:
                import shutil
                shutil.copy("out.wav", file_path)
                self.logs.append(f"Audio saved to {file_path}")
            except Exception as e:
                self.logs.append(f"Error saving audio: {str(e)}")

    def show_loading_screen(self, message=""):
        self.loading_overlay.setVisible(True)
        self.timer_label.setText(message)
        self.elapsed_time = 0
        self.timer_label.setText(f"{message} Time Elapsed: 00:00")
        self.elapsed_timer.start(1000)
        QApplication.processEvents()

    def hide_loading_screen(self):
        elapsed = self.elapsed_time
        if elapsed < 1:
            time.sleep(1 - elapsed)
        self.loading_overlay.setVisible(False)
        self.elapsed_timer.stop()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BSBPTTSWindow()
    window.show()
    sys.exit(app.exec())