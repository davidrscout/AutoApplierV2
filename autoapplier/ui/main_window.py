from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ..core.automation import AutomationRunner
from ..core.storage import load_settings, save_settings


class AutomationThread(QtCore.QThread):
    log_signal = QtCore.Signal(str)
    status_signal = QtCore.Signal(str)
    popup_signal = QtCore.Signal(object)

    def __init__(self, settings: dict, scan_only: bool = False) -> None:
        super().__init__()
        self.settings = settings
        self.scan_only = scan_only
        self.runner: AutomationRunner | None = None

    def run(self) -> None:
        self.runner = AutomationRunner(
            settings=self.settings,
            log_cb=self.log_signal.emit,
            status_cb=self.status_signal.emit,
            popup_cb=self.popup_signal.emit,
        )
        if self.scan_only:
            self.runner.scan_only()
        else:
            self.runner.run()

    def stop(self) -> None:
        if self.runner:
            self.runner.request_stop()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AutoApplier")
        self.resize(900, 600)
        self.settings = load_settings()
        self.worker: AutomationThread | None = None
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(root)

        job_group = QtWidgets.QGroupBox("Job Selection")
        job_layout = QtWidgets.QFormLayout(job_group)
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItem("Loading roles...")
        self.role_combo.setEnabled(False)
        self.role_custom_input = QtWidgets.QLineEdit()
        self.role_custom_input.setPlaceholderText("Custom job type (if Other)")
        self.role_custom_input.setEnabled(False)
        job_layout.addRow("Job type", self.role_combo)
        job_layout.addRow("Custom", self.role_custom_input)
        layout.addWidget(job_group)

        cv_row = QtWidgets.QHBoxLayout()
        self.cv_path_label = QtWidgets.QLabel("No CV folder selected")
        self.cv_select_button = QtWidgets.QPushButton("Select CV Folder")
        self.cv_select_button.clicked.connect(self._select_cv_folder)
        cv_row.addWidget(self.cv_path_label, 1)
        cv_row.addWidget(self.cv_select_button)
        layout.addLayout(cv_row)

        self.scan_button = QtWidgets.QPushButton("Scan CVs")
        self.scan_button.clicked.connect(self._scan_cvs)
        layout.addWidget(self.scan_button)

        buttons_row = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self._start)
        self.stop_button.clicked.connect(self._stop)
        buttons_row.addWidget(self.start_button)
        buttons_row.addWidget(self.stop_button)
        layout.addLayout(buttons_row)

        self.status_label = QtWidgets.QLabel("Idle")
        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.status_label)
        layout.addWidget(self.log_output, 1)

        self.setCentralWidget(root)

    def _load_values(self) -> None:
        self.cv_path_label.setText(self.settings.get("cv_root", "") or "No CV folder selected")
        self._load_roles_from_autoprofile()

    def _select_cv_folder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select CV Folder")
        if folder:
            self.settings["cv_root"] = folder
            save_settings(self.settings)
            self.cv_path_label.setText(folder)
            self._append_log("CV folder selected.")

    def _scan_cvs(self) -> None:
        if not self.settings.get("cv_root"):
            QtWidgets.QMessageBox.warning(self, "Missing CV folder", "Please select a CV folder.")
            return
        self._append_log("Scanning CVs and building AutoProfile...")
        self.start_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.worker = AutomationThread(self.settings, scan_only=True)
        self.worker.log_signal.connect(self._append_log)
        self.worker.status_signal.connect(self._set_status)
        self.worker.popup_signal.connect(self._handle_popup_request)
        self.worker.finished.connect(self._on_scan_finished)
        self.worker.start()

    def _on_scan_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self._set_status("Idle")
        self.worker = None
        self._load_roles_from_autoprofile()

    def _load_roles_from_autoprofile(self) -> None:
        try:
            from ..core.storage import load_autoprofile

            auto = load_autoprofile()
            roles = auto.get("roles", []) if isinstance(auto.get("roles", []), list) else []
        except Exception:
            roles = []
        self.role_combo.clear()
        if roles:
            self.role_combo.addItems(roles + ["Other (custom)"])
            self.role_combo.setEnabled(True)
            self.role_custom_input.setEnabled(True)
        else:
            self.role_combo.addItem("Scan CVs to load roles")
            self.role_combo.setEnabled(False)
            self.role_custom_input.setEnabled(False)
    def _start(self) -> None:
        if not self.settings.get("cv_root"):
            QtWidgets.QMessageBox.warning(self, "Missing CV folder", "Please select a CV folder.")
            return
        if not self.role_combo.isEnabled():
            QtWidgets.QMessageBox.warning(self, "Missing roles", "Please scan CVs to load job roles first.")
            return
        selected_role = self.role_combo.currentText()
        if selected_role == "Other (custom)":
            selected_role = self.role_custom_input.text().strip()
        self.settings["selected_role"] = selected_role
        save_settings(self.settings)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Starting...")
        self.worker = AutomationThread(self.settings)
        self.worker.log_signal.connect(self._append_log)
        self.worker.status_signal.connect(self._set_status)
        self.worker.popup_signal.connect(self._handle_popup_request)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _stop(self) -> None:
        if self.worker:
            self.worker.stop()
            self._append_log("Stop requested.")
        self.stop_button.setEnabled(False)

    def _on_worker_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._set_status("Idle")
        self.worker = None

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _append_log(self, text: str) -> None:
        self.log_output.appendPlainText(text)

    def _handle_popup_request(self, request) -> None:
        from .personal_dialog import PersonalQuestionDialog, CaptchaDialog

        if getattr(request, "kind", "") == "captcha":
            dialog = CaptchaDialog(request.question, self)
            if dialog.exec():
                request.answer = "ok"
                request.remember = False
            else:
                request.answer = None
                request.remember = False
        else:
            dialog = PersonalQuestionDialog(request.question, self)
            if dialog.exec():
                request.answer = dialog.answer
                request.remember = dialog.remember
            else:
                request.answer = None
                request.remember = False
        if request.event:
            request.event.set()
