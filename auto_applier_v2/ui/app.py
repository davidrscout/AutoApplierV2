import os
import queue
import threading
import webbrowser
from dataclasses import dataclass
from typing import Callable
from tkinter import filedialog

import customtkinter as ctk

from core.cv_context import CVContextManager


@dataclass
class UIState:
    status: str = "Idle"
    running: bool = False


class App(ctk.CTk):
    def __init__(self, on_start: Callable[[dict], None] | None = None, on_pause: Callable[[], None] | None = None) -> None:
        super().__init__()
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("AutoApplier v2")
        self.geometry("1200x720")
        self.minsize(980, 620)

        self.ui_state = UIState()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.on_start = on_start
        self.on_pause = on_pause
        self.cv_context = ""
        self.cv_context_manager = CVContextManager(
            cache_path=os.path.join(os.getcwd(), "config", "cv_context.json")
        )
        self.auth_token_path = os.path.join(os.getcwd(), "config", "auth_token.txt")

        self._build_layout()
        self._bind_events()
        self._poll_logs()
        self._load_auth_token()

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.sidebar = ctk.CTkFrame(self, corner_radius=16)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        self.sidebar.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(self.sidebar, text="Config", font=ctk.CTkFont(size=20, weight="bold"))
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self.cv_label = ctk.CTkLabel(self.sidebar, text="Ruta CVs")
        self.cv_label.grid(row=1, column=0, sticky="w", padx=16, pady=(8, 4))
        self.cv_entry = ctk.CTkEntry(self.sidebar)
        self.cv_entry.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.cv_button = ctk.CTkButton(self.sidebar, text="Cargar CV")
        self.cv_button.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.keywords_label = ctk.CTkLabel(self.sidebar, text="Keywords (Auto)")
        self.keywords_label.grid(row=4, column=0, sticky="w", padx=16, pady=(8, 4))
        self.keywords_entry = ctk.CTkEntry(self.sidebar)
        self.keywords_entry.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.auth_label = ctk.CTkLabel(self.sidebar, text="Auth Token (OAuth)")
        self.auth_label.grid(row=6, column=0, sticky="w", padx=16, pady=(8, 4))
        self.auth_entry = ctk.CTkEntry(self.sidebar)
        self.auth_entry.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.auth_login_button = ctk.CTkButton(self.sidebar, text="Login Google")
        self.auth_login_button.grid(row=8, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.auth_save_button = ctk.CTkButton(self.sidebar, text="Guardar Token")
        self.auth_save_button.grid(row=9, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.location_label = ctk.CTkLabel(self.sidebar, text="Location")
        self.location_label.grid(row=10, column=0, sticky="w", padx=16, pady=(8, 4))
        self.location_entry = ctk.CTkEntry(self.sidebar)
        self.location_entry.grid(row=11, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.controls = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.controls.grid(row=12, column=0, sticky="ew", padx=16, pady=(12, 16))
        self.controls.grid_columnconfigure((0, 1), weight=1)

        self.start_button = ctk.CTkButton(self.controls, text="Iniciar Busqueda", corner_radius=12)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.pause_button = ctk.CTkButton(self.controls, text="Pausar", corner_radius=12, fg_color="#7A1F1F")
        self.pause_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self.pause_button.configure(state="disabled")

        self.main_panel = ctk.CTkFrame(self, corner_radius=16)
        self.main_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        self.main_panel.grid_rowconfigure(1, weight=1)
        self.main_panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(header, text="Status: Idle", font=ctk.CTkFont(size=16, weight="bold"))
        self.status_label.grid(row=0, column=0, sticky="w")

        self.log_box = ctk.CTkTextbox(self.main_panel, corner_radius=12, wrap="word")
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def _bind_events(self) -> None:
        self.start_button.configure(command=self._on_start)
        self.pause_button.configure(command=self._on_pause)
        self.cv_button.configure(command=self._on_load_cv)
        self.auth_login_button.configure(command=self._on_login_google)
        self.auth_save_button.configure(command=self._on_save_auth_token)

    def _on_load_cv(self) -> None:
        path = filedialog.askdirectory(title="Selecciona la carpeta de CVs")
        if path:
            self.cv_entry.delete(0, "end")
            self.cv_entry.insert(0, path)
            self.append_log(f"[UI] CV folder: {path}")
            threading.Thread(target=self._build_cv_context, args=(path,), daemon=True).start()

    def _on_login_google(self) -> None:
        webbrowser.open("http://localhost:8000/auth/login")
        self.append_log("[UI] Abriendo login OAuth en el navegador...")

    def _on_save_auth_token(self) -> None:
        token = self.auth_entry.get().strip()
        if not token:
            self.append_log("[UI] Auth token vacío.")
            return
        os.makedirs(os.path.dirname(self.auth_token_path), exist_ok=True)
        try:
            with open(self.auth_token_path, "w", encoding="utf-8") as f:
                f.write(token)
            self.append_log("[UI] Auth token guardado.")
        except Exception:
            self.append_log("[UI] No se pudo guardar el auth token.")

    def _load_auth_token(self) -> None:
        try:
            with open(self.auth_token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
                if token:
                    self.auth_entry.delete(0, "end")
                    self.auth_entry.insert(0, token)
        except Exception:
            pass

    def _build_cv_context(self, path: str) -> None:
        self.append_log("[UI] Procesando CVs con Ollama...")
        context = self.cv_context_manager.build_context(path, self.append_log)
        if context:
            self.cv_context = context
            self.append_log("[UI] Contexto de CV listo.")
        else:
            self.append_log("[UI] No se pudo generar contexto de CV.")

        keywords_path = os.path.join(os.getcwd(), "config", "keywords.txt")
        self.append_log("[UI] Generando keywords desde CVs...")
        keywords = self.cv_context_manager.build_keywords_file(path, self.append_log, keywords_path)
        if keywords:
            self.keywords_entry.delete(0, "end")
            self.keywords_entry.insert(0, ", ".join(keywords))
            self.append_log(f"[UI] Keywords guardadas: {keywords_path}")
        else:
            self.append_log("[UI] No se pudieron generar keywords.")

    def _on_start(self) -> None:
        if self.ui_state.running:
            return
        if self.auth_entry.get().strip():
            self._on_save_auth_token()
        payload = {
            "cv_root": self.cv_entry.get().strip(),
            "keywords": self.keywords_entry.get().strip(),
            "location": self.location_entry.get().strip(),
            "cv_context": self.cv_context,
        }
        self.ui_state.running = True
        self._set_status("Running")
        self.start_button.configure(state="disabled")
        self.pause_button.configure(state="normal")
        if self.on_start:
            threading.Thread(target=self.on_start, args=(payload,), daemon=True).start()
        else:
            self.append_log("[UI] Iniciar Busqueda: engine no conectado.")

    def _on_pause(self) -> None:
        if not self.ui_state.running:
            return
        self.ui_state.running = False
        self._set_status("Paused")
        self.pause_button.configure(state="disabled")
        self.start_button.configure(state="normal")
        if self.on_pause:
            threading.Thread(target=self.on_pause, daemon=True).start()
        else:
            self.append_log("[UI] Pausar: engine no conectado.")

    def _set_status(self, status: str) -> None:
        self.ui_state.status = status
        self.status_label.configure(text=f"Status: {status}")

    def append_log(self, message: str) -> None:
        self.log_queue.put(message)

    def _poll_logs(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", message + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_logs)


if __name__ == "__main__":
    app = App()
    app.mainloop()
