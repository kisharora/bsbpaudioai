import tkinter as tk
from tkinter import messagebox, filedialog
import torch
import os
import soundfile as sf
from kokoro import KPipeline
import time
import platform
from pygame import mixer  # Replaces playsound for cross-platform audio
import logging

class KokoroTTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kokoro TTS")
        self.root.configure(bg="#1A1A2E")
        self.root.geometry("600x700")

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info('Application started')

        # Initialize pygame mixer
        mixer.init()

        self.device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        self.pipeline = None
        self.current_audio = None
        self.voice = "af_heart"
        self.lang_code = "a"

        # Color scheme
        self.bg_color = "#1A1A2E"
        self.fg_color = "#E0E0E0"
        self.accent_color = "#0F3460"
        self.button_color = "#533483"
        self.button_hover = "#E94560"

        # Status Section
        self.status_label = tk.Label(root, text="Status Log", fg=self.fg_color, bg=self.bg_color, font=("Arial", 14, "bold"))
        self.status_label.pack(pady=10)

        self.status_log = tk.Text(root, height=10, width=60, fg=self.fg_color, bg="#2A2A3E", font=("Arial", 10), borderwidth=2, relief="flat")
        self.status_log.pack(pady=5)

        # Loading Indicator
        self.loading_label = tk.Label(root, text="", fg="#FFD700", bg=self.bg_color, font=("Arial", 12, "italic"))
        self.loading_label.pack(pady=5)

        # Pipeline Initialization
        self.init_button = tk.Button(root, text="Initialize Pipeline", fg=self.fg_color, bg=self.button_color,
                                    font=("Arial", 12, "bold"), command=self.initialize_pipeline,
                                    activebackground=self.button_hover, activeforeground=self.fg_color,
                                    highlightthickness=0, highlightbackground=self.button_color, relief="flat", borderwidth=0)
        self.init_button.pack(pady=10)

        # Options Frame
        self.options_frame = tk.Frame(root, bg=self.accent_color, padx=10, pady=10)
        self.options_frame.pack(fill="x", padx=20, pady=5)

        self.lang_label = tk.Label(self.options_frame, text="Language:", fg=self.fg_color, bg=self.accent_color, font=("Arial", 12))
        self.lang_label.grid(row=0, column=0, padx=5, pady=5, sticky="e")

        self.lang_var = tk.StringVar(value=self.lang_code)
        self.lang_options = {
            "a": "American English", "b": "British English", "e": "Spanish",
            "f": "French", "h": "Hindi", "i": "Italian", "j": "Japanese",
            "p": "Brazilian Portuguese", "z": "Mandarin Chinese"
        }
        self.lang_dropdown = tk.OptionMenu(self.options_frame, self.lang_var, *self.lang_options.keys(),
                                          command=lambda _: self.update_voice_options())
        self.lang_dropdown.config(bg=self.button_color, fg=self.fg_color, activebackground=self.button_hover)
        self.lang_dropdown.grid(row=0, column=1, padx=5, pady=5)

        self.voice_label = tk.Label(self.options_frame, text="Voice:", fg=self.fg_color, bg=self.accent_color, font=("Arial", 12))
        self.voice_label.grid(row=1, column=0, padx=5, pady=5, sticky="e")

        self.voice_var = tk.StringVar(value=self.voice)
        self.voice_options = self.get_kokoro_voices()
        self.voice_dropdown = tk.OptionMenu(self.options_frame, self.voice_var, *self.voice_options.keys())
        self.voice_dropdown.config(bg=self.button_color, fg=self.fg_color, activebackground=self.button_hover)
        self.voice_dropdown.grid(row=1, column=1, padx=5, pady=5)

        self.text_label = tk.Label(root, text="Enter Text to Convert", fg=self.fg_color, bg=self.bg_color, font=("Arial", 14, "bold"))
        self.text_label.pack(pady=10)

        self.text_input = tk.Text(root, height=5, width=60, fg=self.fg_color, bg="#2A2A3E", font=("Arial", 10), borderwidth=2, relief="flat")
        self.text_input.pack(pady=5)

        self.speed_frame = tk.Frame(root, bg=self.accent_color, padx=10, pady=10)
        self.speed_frame.pack(fill="x", padx=20, pady=5)

        self.speed_label = tk.Label(self.speed_frame, text="Speed:", fg=self.fg_color, bg=self.accent_color, font=("Arial", 12))
        self.speed_label.pack(side=tk.LEFT, padx=5)

        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_scale = tk.Scale(self.speed_frame, from_=0.5, to=2.0, resolution=0.1, orient=tk.HORIZONTAL,
                                    variable=self.speed_var, bg=self.accent_color, fg=self.fg_color, troughcolor="#2A2A3E",
                                    length=250, highlightthickness=0)
        self.speed_scale.pack(side=tk.LEFT)

        self.generate_button = tk.Button(root, text="Generate Audio", fg=self.fg_color, bg=self.button_color,
                                        font=("Arial", 12, "bold"), command=self.generate_audio,
                                        activebackground=self.button_hover, activeforeground=self.fg_color,
                                        highlightthickness=0, highlightbackground=self.button_color, relief="flat", borderwidth=0)
        self.generate_button.pack(pady=10)

        self.play_button = tk.Button(root, text="Play Audio", fg=self.fg_color, bg=self.button_color,
                                    font=("Arial", 12, "bold"), command=self.play_audio,
                                    activebackground=self.button_hover, activeforeground=self.fg_color,
                                    highlightthickness=0, highlightbackground=self.button_color, relief="flat", borderwidth=0)
        self.play_button.pack(pady=5)

        self.pause_button = tk.Button(root, text="Pause Audio", fg=self.fg_color, bg=self.button_color,
                                     font=("Arial", 12, "bold"), command=self.pause_audio,
                                     activebackground=self.button_hover, activeforeground=self.fg_color,
                                     highlightthickness=0, highlightbackground=self.button_color, relief="flat", borderwidth=0)
        self.pause_button.pack(pady=5)

        self.save_button = tk.Button(root, text="Save Audio", fg=self.fg_color, bg=self.button_color,
                                    font=("Arial", 12, "bold"), command=self.save_audio,
                                    activebackground=self.button_hover, activeforeground=self.fg_color,
                                    highlightthickness=0, highlightbackground=self.button_color, relief="flat", borderwidth=0)
        self.save_button.pack(pady=5)

        self.log_message("Kokoro TTS application started.")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def get_kokoro_voices(self):
        voices = {
            "af": "Default (Bella + Sarah mix)", "af_alloy": "Alloy (Female, American English)",
            "af_aoede": "Aoede (Female, American English)", "af_bella": "Bella (Female, American English)",
            "af_heart": "Heart (Female, American English)", "af_jessica": "Jessica (Female, American English)",
            "af_kore": "Kore (Female, American English)", "af_nicole": "Nicole (Female, American English)",
            "af_nova": "Nova (Female, American English)", "af_river": "River (Female, American English)",
            "af_sarah": "Sarah (Female, American English)", "af_sky": "Sky (Female, American English)",
            "am_adam": "Adam (Male, American English)", "am_michael": "Michael (Male, American English)",
            "bf_emma": "Emma (Female, British English)", "bf_isabella": "Isabella (Female, British English)",
            "bm_george": "George (Male, British English)", "bm_lewis": "Lewis (Male, British English)",
            "hf_default": "Default Hindi (Female, Hindi)"
        }
        return voices

    def update_voice_options(self):
        self.lang_code = self.lang_var.get()
        self.voice_dropdown['menu'].delete(0, 'end')
        filtered_voices = {k: v for k, v in self.get_kokoro_voices().items() if k.startswith(self.lang_code)}
        for voice in filtered_voices.keys():
            self.voice_dropdown['menu'].add_command(
                label=filtered_voices[voice], command=lambda v=voice: self.voice_var.set(v)
            )
        if filtered_voices:
            self.voice_var.set(list(filtered_voices.keys())[0])
        else:
            self.voice_var.set("af_heart")
            self.log_message(f"No voices available for language '{self.lang_code}'. Defaulting to 'af_heart'.")

    def log_message(self, message):
        self.status_log.insert(tk.END, message + "\n")
        self.status_log.see(tk.END)

    def show_loading(self, message):
        self.loading_label.config(text=message)
        self.root.update()

    def hide_loading(self):
        self.loading_label.config(text="")
        self.root.update()

    def initialize_pipeline(self):
        try:
            logging.info('Initializing pipeline...')
            self.show_loading("Initializing pipeline...")
            start_time = time.time()
            self.lang_code = self.lang_var.get()
            self.log_message(f"Initializing pipeline with language: {self.lang_options.get(self.lang_code, self.lang_code)}")
            self.pipeline = KPipeline(lang_code=self.lang_code)
            init_time = time.time() - start_time
            self.log_message(f"Pipeline initialized successfully! Time taken: {init_time:.2f} seconds")
        except Exception as e:
            self.log_message(f"Error initializing pipeline: {str(e)}")
            messagebox.showerror("Error", "Pipeline initialization failed! Check error log.")
        finally:
            self.hide_loading()

    def generate_audio(self):
        if not self.pipeline:
            self.log_message("Pipeline not initialized.")
            messagebox.showerror("Error", "Please initialize the pipeline first!")
            return

        text = self.text_input.get("1.0", tk.END).strip()
        if not text:
            self.log_message("No text entered.")
            messagebox.showwarning("Warning", "Please enter text to convert.")
            return

        try:
            self.show_loading("Generating audio...")
            total_start_time = time.time()

            self.lang_code = self.lang_var.get()
            self.voice = self.voice_var.get()
            speed = self.speed_var.get()
            logging.info(f'Generating audio for text with voice: {self.voice}, speed: {speed}, language: {self.lang_options.get(self.lang_code, self.lang_code)}')
            self.log_message(f"Generating audio for text with voice: {self.voice}, speed: {speed}, language: {self.lang_options.get(self.lang_code, self.lang_code)}")

            # Generation phase
            generation_start = time.time()
            generator = self.pipeline(text, voice=self.voice, speed=speed, split_pattern=r'\n+')
            all_audio = []
            for i, (gs, ps, audio) in enumerate(generator):
                self.log_message(f"Generated segment {i+1}")
                all_audio.append(audio)
            generation_time = time.time() - generation_start

            # Compilation phase
            compilation_start = time.time()
            if all_audio:
                combined_audio = torch.cat(all_audio, dim=0).numpy()
                audio_file = os.path.join(os.getcwd(), "output.wav")  # Cross-platform path
                sf.write(audio_file, combined_audio, 24000)
                self.log_message(f"Audio generated and saved as: {audio_file}")
                self.current_audio = audio_file
            else:
                self.log_message("No audio segments were generated.")
            compilation_time = time.time() - compilation_start

            total_time = time.time() - total_start_time
            self.log_message(f"Generation time: {generation_time:.2f} seconds")
            self.log_message(f"Compilation time: {compilation_time:.2f} seconds")
            self.log_message(f"Total time: {total_time:.2f} seconds")
        except Exception as e:
            self.log_message(f"Error generating audio: {str(e)}. Check if voice '{self.voice}' is supported for language '{self.lang_code}'.")
            messagebox.showerror("Error", "Audio generation failed! Check error log.")
        finally:
            self.hide_loading()

    def play_audio(self):
        if hasattr(self, "current_audio") and self.current_audio and os.path.exists(self.current_audio):
            self.stop_audio()  # Ensure any previous playback is stopped
            logging.info(f'Playing audio: {self.current_audio}')
            self.log_message(f"Playing audio: {self.current_audio}")
            try:
                mixer.music.load(self.current_audio)
                mixer.music.play()
            except Exception as e:
                self.log_message(f"Error playing audio: {str(e)}")
                messagebox.showerror("Error", "Failed to play audio. Check log.")
        else:
            self.log_message("No audio to play or file not found.")
            messagebox.showwarning("Warning", "Generate audio first.")

    def pause_audio(self):
        if mixer.music.get_busy():
            logging.info('Pausing audio playback.')
            self.log_message("Pausing audio playback.")
            mixer.music.pause()
        else:
            self.log_message("No audio is currently playing.")

    def stop_audio(self):
        if mixer.music.get_busy():
            mixer.music.stop()
            logging.info('Audio playback stopped.')
            self.log_message("Audio playback stopped.")

    def save_audio(self):
        if hasattr(self, "current_audio") and self.current_audio and os.path.exists(self.current_audio):
            save_path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV files", "*.wav")], title="Save Audio As")
            if save_path:
                import shutil
                shutil.copy(self.current_audio, save_path)
                logging.info(f'Audio saved to: {save_path}')
                self.log_message(f"Audio saved to: {save_path}")
        else:
            self.log_message("No audio to save or file not found.")
            messagebox.showwarning("Warning", "Generate audio first.")

    def on_closing(self):
        logging.info('Application closed.')
        self.stop_audio()  # Stop any playing audio
        mixer.quit()  # Properly dispose of pygame mixer
        if self.current_audio and os.path.exists(self.current_audio):
            try:
                os.remove(self.current_audio)  # Clean up temporary audio file
                logging.info(f'Temporary audio file {self.current_audio} removed.')
            except Exception as e:
                logging.warning(f'Failed to remove temporary audio file: {str(e)}')
        self.root.destroy()

def main():
    root = tk.Tk()
    app = KokoroTTSApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()