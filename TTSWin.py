import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget, QDialog, QComboBox, QSlider, QLabel, QHBoxLayout, QLineEdit, QColorDialog
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
import pyttsx3
from tts_wrapper import PollyClient, PollyTTS, GoogleClient, GoogleTTS
import wave
import pyaudio
import json


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.parent = parent
        self.credentials = self.load_credentials()
        self.engine = pyttsx3.init()  # Default to system TTS engine
        self.initUI()
        self.load_and_apply_settings()

    def initUI(self):
        layout = QVBoxLayout()
        self.engineCombo = QComboBox()
        self.engineCombo.addItems(['System Voice (SAPI)', 'Polly', 'Google', 'Azure', 'Watson'])
        self.engineCombo.currentIndexChanged.connect(self.on_engine_change)
        layout.addWidget(QLabel("Select TTS Engine:"))
        layout.addWidget(self.engineCombo)

        # Voice selection combo box
        self.voiceCombo = QComboBox()
        layout.addWidget(QLabel("Select Voice:"))
        layout.addWidget(self.voiceCombo)
    
        self.rateSlider = QSlider(Qt.Horizontal)
        self.rateSlider.setMinimum(50)
        self.rateSlider.setMaximum(400)
        layout.addWidget(QLabel("Set Speech Rate:"))
        layout.addWidget(self.rateSlider)
    
        self.colorButton = QPushButton('Choose Highlight Color')
        self.colorButton.clicked.connect(self.choose_color)
        layout.addWidget(self.colorButton)
    
        self.credentials_label = QLabel()
        self.credentials_label.setOpenExternalLinks(True)
        self.credentials_label.setTextFormat(Qt.RichText)
        self.credentials_label.setText('<a href="file:///{}">Manage credentials in credentials.json</a>'.format(os.path.abspath('credentials.json')))
        layout.addWidget(self.credentials_label)
    
        saveButton = QPushButton('Save Settings')
        saveButton.clicked.connect(self.save_settings)
        layout.addWidget(saveButton)
    
        self.setLayout(layout)

    def load_credentials(self):
        # Load credentials from a JSON file
        try:
            with open("credentials.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}  # Return an empty dict if the file does not exist

    def on_engine_change(self, index):
        engine_choice = self.engineCombo.currentText()
        if engine_choice == "System Voice (SAPI)":
            self.update_voice_list()  # This updates the list for the system voices
            self.credentials_label.setVisible(False)  # Hide credentials info for SAPI
        else:
            self.load_and_display_voices(engine_choice)  # Load voices from JSON for other engines
            self.credentials_label.setVisible(True)  # Show credentials info for cloud-based services
        
    def load_and_display_voices(self, engine_name):
        voices = self.load_voices_from_json(engine_name.lower())  # Make sure JSON files are named accordingly
        self.voiceCombo.clear()
        for voice in voices:
            self.voiceCombo.addItem(voice['name'], voice)  # You may need to adjust what data is stored based on your needs
    

    def choose_color(self):
        color = QColorDialog.getColor(self.parent.highlight_color)
        if color.isValid():
            self.parent.highlight_color = color
            self.colorButton.setText(f'Choose Highlight Color (Current: {color.name()})')

    def load_and_apply_settings(self):
        # Load settings from a file and apply them to the UI
        settings = self.load_settings_from_file()
        self.apply_common_settings(settings)
        self.apply_specific_settings(settings)

    def apply_common_settings(self, settings):
        # Apply common settings like speech rate and highlight color
        self.rateSlider.setValue(settings.get("speech_rate", 200))  # Default to 200 if not set
        color_name = settings.get("highlight_color", "#FFFF00")  # Default color
        self.parent.highlight_color = QColor(color_name)
        self.colorButton.setText(f'Choose Highlight Color (Current: {color_name})')

    def apply_specific_settings(self, settings=None):
        if settings is None:
            settings = self.load_settings_from_file()
        engine_choice = settings.get("tts_engine", "System Voice (SAPI)")
        self.engineCombo.setCurrentIndex(self.engineCombo.findText(engine_choice))
    
        if engine_choice == "System Voice (SAPI)":
            self.update_voice_list()
            self.credentials_label.setVisible(False)
        else:
            # Load and display voices for selected TTS-Wrapper engine
            voices = self.load_voices_from_json(engine_choice.lower())
            self.voiceCombo.clear()
            for voice in voices:
                self.voiceCombo.addItem(voice['name'], voice)
            self.credentials_label.setVisible(True)

    def load_voices_from_json(self, engine_name):
        try:
            with open(f"{engine_name}_voices.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return []

    def save_settings(self):
        # Save settings based on the current state of the UI elements
        settings = {
            "tts_engine": self.engineCombo.currentText(),
            "voice_name": self.voiceCombo.currentData(),
            "speech_rate": self.rateSlider.value(),
            "highlight_color": self.parent.highlight_color.name()
        }
        self.save_settings_to_file(settings)
        self.accept()

    def save_settings_to_file(self, settings):
        with open('settings.json', 'w') as f:
            json.dump(settings, f)

    def load_settings_from_file(self):
        try:
            with open('settings.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}  # Return an empty dict if the file does not exist

    def update_voice_list(self):
        # Assuming voice list update for pyttsx3
        self.voiceCombo.clear()
        voices = self.engine.getProperty('voices')
        for voice in voices:
            self.voiceCombo.addItem(voice.name, voice.id)

class SpeechThread(QThread):
    finished = pyqtSignal()

    def __init__(self, text, engine, tts_type, parent=None):
        super(SpeechThread, self).__init__(parent)
        self.text = text
        self.engine = engine
        self.tts_type = tts_type  # 'system' for pyttsx3, 'wrapper' for TTS-Wrapper engines

    def run(self):
        if self.tts_type == 'system':
            # Using pyttsx3
            self.engine.say(self.text)
            self.engine.runAndWait()
        elif self.tts_type == 'wrapper':
            # Using TTS-Wrapper
            audio_bytes = self.engine.synth_to_bytes(self.text, format='wav')
            self.play_audio(audio_bytes)
        self.finished.emit()

    def play_audio(self, audio_bytes):
        # Play audio from bytes
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,  # Assumes 16-bit audio
                        channels=1,  # Mono
                        rate=22050,  # Sample rate
                        output=True)
        stream.write(audio_bytes)
        stream.stop_stream()
        stream.close()
        p.terminate()

class TextToSpeechApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = pyttsx3.init()
        self.tts_type = 'system'  # Default to system type
        self.highlight_color = QColor('yellow')
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Text-to-Speech App')
        self.setGeometry(100, 100, 480, 320)

        # Main layout and widgets
        mainLayout = QVBoxLayout()
        widget = QWidget(self)
        widget.setLayout(mainLayout)
        self.setCentralWidget(widget)

        # Text edit field
        self.textEdit = QTextEdit()
        mainLayout.addWidget(self.textEdit)

        # Radio buttons for reading modes
        self.radio_sentence = QRadioButton("Read Sentence", self)
        self.radio_paragraph = QRadioButton("Read Paragraph", self)
        self.radio_word = QRadioButton("Read Word", self)
        self.radio_all = QRadioButton("Read All", self)
        self.radio_all.setChecked(True)
        radio_layout = QVBoxLayout()
        radio_layout.addWidget(self.radio_sentence)
        radio_layout.addWidget(self.radio_paragraph)
        radio_layout.addWidget(self.radio_word)
        radio_layout.addWidget(self.radio_all)
        mainLayout.addLayout(radio_layout)

        # Read button
        self.button_read = QPushButton('Read', self)
        self.button_read.clicked.connect(self.read_text)
        mainLayout.addWidget(self.button_read)

        # Settings button
        self.button_settings = QPushButton('Settings', self)
        self.button_settings.clicked.connect(self.open_settings)
        mainLayout.addWidget(self.button_settings)

        self.show()


    def read_text(self):
        text = self.textEdit.toPlainText()
        cursor = self.textEdit.textCursor()
        format = QTextCharFormat()
        format.setBackground(self.highlight_color)

        selected_text = ""
        if self.radio_sentence.isChecked():
            selected_text = text.split('.')[0]
        elif self.radio_paragraph.isChecked():
            selected_text = text.split('\n')[0]
        elif self.radio_word.isChecked():
            selected_text = text.split()[0]
        elif self.radio_all.isChecked():
            selected_text = text

        self.highlight_text(selected_text, cursor, format)
        self.start_speech_thread(selected_text)

    def highlight_text(self, text, cursor, format):
        # Find and highlight text
        cursor.movePosition(QTextCursor.Start)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(text))
        self.textEdit.setTextCursor(cursor)
        cursor.setCharFormat(format)

    def start_speech_thread(self, text):
        self.thread = SpeechThread(text, self.engine, self.tts_type)
        self.thread.finished.connect(self.reset_highlight)
        self.thread.start()

    def reset_highlight(self):
        cursor = self.textEdit.textCursor()
        cursor.setCharFormat(QTextCharFormat())  # Reset format
        cursor.clearSelection()
        self.textEdit.setTextCursor(cursor)

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

def main():
    app = QApplication(sys.argv)
    ex = TextToSpeechApp()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
    