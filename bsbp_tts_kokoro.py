import sys
import os
import numpy as np
from datetime import datetime
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow,QStyle, QWidget, QVBoxLayout, QHBoxLayout,
                             QTextEdit, QComboBox, QSlider, QPushButton, QLabel, QFileDialog, QStyledItemDelegate, QStyleOptionViewItem)
from PyQt6.QtCore import Qt, QTimer, QUrl, QThread, pyqtSignal, QSize, QRect
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QIcon, QPainter, QBrush, QColor

# Suppress PyTorch deprecation warning
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

# Import Kokoro TTS
try:
    from kokoro import KPipeline
    import soundfile as sf
    import torch
except ImportError:
    print("Error: Please install the required dependencies: pip install kokoro>=0.9.2 soundfile torch")
    sys.exit(1)

# Audio Generation Thread
class AudioGenerationThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, pipeline, text, voice, speed):
        super().__init__()
        self.pipeline = pipeline
        self.text = text
        self.voice = voice
        self.speed = speed

    def run(self):
        try:
            self.progress.emit(f"<span style='color:#F97316'>Starting audio generation...</span>")
            total_start = time.time()
            generator = self.pipeline(self.text, voice=self.voice, speed=self.speed)
            audio_segments = []
            generation_start = time.time()
            for i, (gs, ps, audio) in enumerate(generator):
                self.progress.emit(f"Generated segment {i}: {gs}")
                audio_segments.append(audio)
            generation_time = time.time() - generation_start

            combine_start = time.time()
            if audio_segments:
                combined_audio = np.concatenate(audio_segments)
                sf.write("out.wav", combined_audio, 22050)  # Use 22.05 kHz for better compatibility
                self.progress.emit("Combined all segments into out.wav.")
            else:
                self.progress.emit("No audio segments generated.")
            combine_time = time.time() - combine_start

            total_time = time.time() - total_start
            self.progress.emit(f" Generation time: {generation_time:.2f} seconds")
            self.progress.emit(f"Combine time: {combine_time:.2f} seconds")
            self.progress.emit(f"<span style='color:#F97316'>Total time: {total_time:.2f} seconds</span>")
            self.finished.emit()
        except Exception as e:
            self.error.emit(f"Error during audio generation: {str(e)}")

# Circular Progress Indicator for Loading Screen
class CircularProgressIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0
        self.setFixedSize(50, 50)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self.timer.start(50)  # Update every 50ms

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

# Custom Delegate for Voice Dropdown
class VoiceDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        try:
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            painter.save()

            # Highlight background on hover/selection
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, QColor("#F97316"))
            elif option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, QColor("#4B5563"))

            # Draw the text (icon + name)
            text = opt.text
            painter.setPen(QColor("#D1D5DB"))
            painter.drawText(option.rect.adjusted(5, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, text)
            painter.restore()
        except Exception as e:
            print(f"Error in VoiceDelegate.paint: {str(e)}")

    def sizeHint(self, option, index):
        return QSize(200, 30)

# Main Application Window
class BSBPTTSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BSBP TTS")
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1C2526;
                color: #D1D5DB;
                font-family: 'Roboto', sans-serif;
            }
            QTextEdit {
                background-color: #374151;
                color: #D1D5DB;
                border: 1px solid #F97316;
                border-radius: 5px;
                padding: 5px;
                font-family: 'Arial', sans-serif;
            }
            QComboBox {
                background-color: #374151;
                color: #D1D5DB;
                border: 1px solid #F97316;
                border-radius: 5px;
                padding: 5px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: #F97316;
                border-left-style: solid;
            }
            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
                image: none;
            }
            QComboBox::down-arrow:on, QComboBox::down-arrow:off {
                image: none;
            }
            QComboBox QAbstractItemView {
                background-color: #374151;
                color: #D1D5DB;
                selection-background-color: #F97316;
                selection-color: #FFFFFF;
                border: 1px solid #F97316;
            }
            QPushButton {
                background-color: #F97316;
                color: #FFFFFF;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #EA580C;
            }
            QPushButton:disabled {
                background-color: #6B7280;
                color: #A1A1AA;
            }
            QSlider::groove:horizontal {
                background: #F97316;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 16px;
                height: 16px;
                border-radius: 8px;
                margin: -4px 0;
            }
            QLabel {
                color: #D1D5DB;
            }
        """)
        self.setGeometry(100, 100, 800, 600)

        # Set App Icon
        if os.path.exists("logo.png"):
            self.setWindowIcon(QIcon("logo.png"))
        else:
            print("Warning: logo.png not found in the root folder.")

        # Main layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        # Status Log
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setFixedHeight(150)
        self.logs.setStyleSheet("font-family: 'Arial', monospace;")
        main_layout.addWidget(QLabel("Status Log"))
        main_layout.addWidget(self.logs)

        # Text Input
        self.text_input = QTextEdit()
        self.text_input.setAcceptRichText(False)
        self.text_input.setText("""First up, let’s imagine Keanu Reeves in a futuristic cyberpunk café. Neon lights, a glowing blue drink in his hand. Let’s type that in and see what we get.

And here it is... Whoa! This actually looks straight out of a sci-fi movie. The neon reflections, the atmosphere—it’s like John Wick just stepped into Blade Runner.

Or... well, this is interesting. I mean, Keanu Reeves IS kind of there, but why does he look like he’s part toaster? Maybe AI still has some work to do.""")
        main_layout.addWidget(QLabel("Enter Text to Convert"))
        main_layout.addWidget(self.text_input)

        # Settings and Audio Player
        settings_layout = QHBoxLayout()

        # Left: Settings
        left_settings = QVBoxLayout()
        self.language_combo = QComboBox()
        self.language_combo.addItems([
            "American English (a)", "British English (b)", "Spanish (e)", "French (f)",
            "Hindi (h)", "Italian (i)", "Japanese (j)", "Brazilian Portuguese (p)", "Mandarin Chinese (z)"
        ])
        self.language_combo.currentIndexChanged.connect(self.update_language_and_voices)
        left_settings.addWidget(QLabel("Language"))
        left_settings.addWidget(self.language_combo)

        self.voice_combo = QComboBox()
        self.voice_combo.setItemDelegate(VoiceDelegate())
        self.all_voices = [
            "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica", "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa",
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
            "ef_dora", "em_alex", "em_santa", "ff_siwis", "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
            "if_sara", "im_nicola", "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
            "pf_dora", "pm_alex", "pm_santa", "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
            "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"
        ]
        self.update_voice_combo()  # Populate voices based on initial language
        self.voice_combo.currentIndexChanged.connect(self.check_voice_availability)
        left_settings.addWidget(QLabel("Voice"))
        left_settings.addWidget(self.voice_combo)

        speed_layout = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(5, 20)  # 0.5x to 2.0x
        self.speed_slider.setValue(10)  # Default 1.0x
        self.speed_label = QLabel("1.0x")
        self.speed_slider.valueChanged.connect(self.update_speed_label)
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        left_settings.addWidget(QLabel("Speed"))
        left_settings.addLayout(speed_layout)

        settings_layout.addLayout(left_settings)

        # Right: Audio Player (hidden initially)
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

        # Buttons
        buttons_layout = QHBoxLayout()
        self.generate_button = QPushButton("Generate Audio")
        self.generate_button.clicked.connect(self.generate_audio)
        buttons_layout.addWidget(self.generate_button)

        self.save_button = QPushButton("Save Audio")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_audio)
        buttons_layout.addWidget(self.save_button)
        main_layout.addLayout(buttons_layout)

        # Media Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.update_seek_slider)
        self.player.durationChanged.connect(self.update_duration)
        self.seek_slider.sliderMoved.connect(self.seek_audio)
        self.player.mediaStatusChanged.connect(self.handle_media_status)

        # Loading Screen with Circular Progress Indicator and Timer
        self.loading_overlay = QWidget(self)
        self.loading_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.8);")
        self.loading_overlay.setVisible(False)
        loading_layout = QVBoxLayout(self.loading_overlay)
        self.progress_indicator = CircularProgressIndicator()
        loading_layout.addWidget(self.progress_indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        self.timer_label = QLabel("Time Elapsed: 00:00")
        self.timer_label.setStyleSheet("color: #D1D5DB; font-size: 16px;")
        loading_layout.addWidget(self.timer_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Timer for elapsed time
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.timeout.connect(self.update_timer_label)
        self.elapsed_time = 0

        # Initialize Pipeline
        self.pipeline = None
        self.initialize_pipeline()

    def resizeEvent(self, event):
        self.loading_overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def update_timer_label(self):
        self.elapsed_time += 1
        minutes = self.elapsed_time // 60
        seconds = self.elapsed_time % 60
        self.timer_label.setText(f"Time Elapsed: {minutes:02d}:{seconds:02d}")

    def initialize_pipeline(self):
        self.show_loading_screen("Initializing pipeline...")
        try:
            lang_code = self.language_combo.currentText().split('(')[-1].strip(')')
            self.logs.append(f"Initializing pipeline with lang_code: {lang_code}")
            self.pipeline = KPipeline(lang_code=lang_code, repo_id='hexgrad/Kokoro-82M')
            self.logs.append("Pipeline initialized successfully.")
        except Exception as e:
            self.logs.append(f"Error initializing pipeline: {str(e)}")
            self.generate_button.setEnabled(False)
        finally:
            self.hide_loading_screen()

    def update_language_and_voices(self):
        self.show_loading_screen("Updating language and voices...")
        try:
            lang_code = self.language_combo.currentText().split('(')[-1].strip(')')
            self.logs.append(f"Reinitializing pipeline with lang_code: {lang_code}")
            self.pipeline = KPipeline(lang_code=lang_code, repo_id='hexgrad/Kokoro-82M')
            self.logs.append("Pipeline reinitialized successfully.")
            self.update_voice_combo()
        except Exception as e:
            self.logs.append(f"Error reinitializing pipeline: {str(e)}")
            self.generate_button.setEnabled(False)
        finally:
            self.hide_loading_screen()

    def update_voice_combo(self):
        self.voice_combo.clear()
        lang_code = self.language_combo.currentText().split('(')[-1].strip(')')
        prefix = lang_code[0]
        filtered_voices = [voice for voice in self.all_voices if voice.startswith(f"{prefix}f_") or voice.startswith(f"{prefix}m_")]
        for voice in filtered_voices:
            icon = "♀" if voice.startswith(f"{prefix}f_") else "♂"
            name = voice[3:]
            display_text = f"{icon} {name}"
            self.voice_combo.addItem(display_text, voice)

    def update_speed_label(self):
        speed = self.speed_slider.value() / 10.0
        self.speed_label.setText(f"{speed:.1f}x")

    def check_voice_availability(self):
        selected_index = self.voice_combo.currentIndex()
        if selected_index == -1:
            return
        voice = self.voice_combo.itemData(selected_index)
        lang_code = self.language_combo.currentText().split('(')[-1].strip(')')
        if not (voice.startswith(f"{lang_code[0]}f_") or voice.startswith(f"{lang_code[0]}m_")):
            self.logs.append(f"Voice '{voice}' is not available for the selected language. Coming Soon!")
            self.update_voice_combo()

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
            self.player.setPosition(0)  # Optional: rewind to start

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
        self.player.stop()  # Stop current playback
        self.play_button.setText("▶")  # Reset button
        self.player_widget.setVisible(False)
        self.save_button.setEnabled(False)

        text = self.text_input.toPlainText()
        voice = self.voice_combo.itemData(self.voice_combo.currentIndex())
        speed = self.speed_slider.value() / 10.0

        self.logs.append(f"Input text length: {len(text)} characters")

        # Start audio generation in a separate thread
        self.audio_thread = AudioGenerationThread(self.pipeline, text, voice, speed)
        self.audio_thread.progress.connect(self.logs.append)
        self.audio_thread.finished.connect(self.on_audio_generation_finished)
        self.audio_thread.error.connect(self.on_audio_generation_error)
        self.audio_thread.start()

    def on_audio_generation_finished(self):
        # Reset QMediaPlayer to ensure a clean state
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.update_seek_slider)
        self.player.durationChanged.connect(self.update_duration)
        self.seek_slider.sliderMoved.connect(self.seek_audio)
        self.player.mediaStatusChanged.connect(self.handle_media_status)

        self.player.setSource(QUrl.fromLocalFile("out.wav"))
        # Wait for duration with a longer timeout
        start_time = time.time()
        while self.player.duration() == 0 and (time.time() - start_time) < 10:  # 10-second timeout
            QApplication.processEvents()
            time.sleep(0.1)
        duration_ms = self.player.duration()
        duration_sec = duration_ms / 1000
        # Verify file duration
        audio_data, sr = sf.read("out.wav")
        file_duration_sec = len(audio_data) / sr
        self.logs.append(f"File duration: {file_duration_sec:.2f} seconds")
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
        # Ensure the loading screen is visible for at least 1 second
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