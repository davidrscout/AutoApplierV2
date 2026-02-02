from PySide6 import QtCore, QtWidgets


class PersonalQuestionDialog(QtWidgets.QDialog):
    def __init__(self, question: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Personal Question Required")
        self.setModal(True)
        self.answer = ""
        self.remember = False

        layout = QtWidgets.QVBoxLayout(self)

        question_label = QtWidgets.QLabel(question)
        question_label.setWordWrap(True)
        layout.addWidget(question_label)

        self.answer_input = QtWidgets.QLineEdit()
        layout.addWidget(self.answer_input)

        self.remember_checkbox = QtWidgets.QCheckBox("Remember this answer")
        layout.addWidget(self.remember_checkbox)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.answer = self.answer_input.text().strip()
        self.remember = self.remember_checkbox.isChecked()
        if not self.answer:
            QtWidgets.QMessageBox.warning(self, "Required", "Please enter an answer.")
            return
        super().accept()


class CaptchaDialog(QtWidgets.QDialog):
    def __init__(self, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CAPTCHA Required")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
