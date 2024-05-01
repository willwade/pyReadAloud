import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget, QDialog, QComboBox, QSlider, QLabel, QHBoxLayout, QLineEdit, QColorDialog
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
import pyttsx3
from tts_wrapper import PollyClient, PollyTTS, GoogleClient, GoogleTTS, MicrosoftClient
import wave
import pyaudio
import json



        
class VoiceManager():
    def __init__(self, configManager):
        self.configManager = configManager
        self.engine = None
        self.engine_type = 'system'  # Default engine type
        self.ttsx_engine = pyttsx3.init()  # Initialize pyttsx3 engine immediately
            
    def init_engine(self, engine_type='system'):
        self.engine_type = engine_type
        if engine_type == 'system':
            self.engine = self.ttsx_engine
        elif engine_type == 'Google':
            self.engine = GoogleClient(credentials=self.configManager.credentials['Google']['creds_path'])
        elif engine_type == 'Polly':
            self.engine = PollyClient(credentials=(self.configManager.credentials['Polly']['region'], self.configManager.credentials['Polly']['aws_key_id'], self.configManager.credentials['Polly']['aws_access_key']))
        elif engine_type == 'Azure':
            self.engine = MicrosoftClient(credentials=self.configManager.credentials['Microsoft']['TOKEN'], region=self.configManager.credentials['Microsoft']['region'])
        elif engine_type == 'Watson':
            self.engine = WatsonClient(credentials=(self.configManager.credentials['Watson']['API_KEY'], self.configManager.credentials['Watson']['API_URL']))
        else:
            print(f"Unsupported TTS engine type: {engine_type}")

    def get_voices(self, engine_type):
        if engine_type == 'System Voice (SAPI)':
            voices = self.ttsx_engine.getProperty('voices')
            return [{'name': voice.name, 'id': voice.id} for voice in voices]
        else:
            return self.load_voices_from_service(engine_type)
            
    def speak(self, text):
        if self.engine_type == 'system':
            # Using pyttsx3
            self.engine.say(text)
            self.engine.runAndWait()
        elif self.engine_type == 'wrapper':
            # Using TTS-Wrapper
            audio_bytes = self.engine.synth_to_bytes(self.text, format='wav')
            self.play_audio(audio_bytes)

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


    def shutdown(self):
        if self.engine_type == 'system' and self.ttsx_engine:
            self.ttsx_engine.stop()

    def load_voices_from_service(self, engine_name):
        # Handle voice loading from JSON files for non-system engines
        try:
            with open(f"{engine_name}_voices.json", "r") as file:
                voices = json.load(file)
                return [{'name': voice['name'], 'id': voice['name'], 'details': voice} for voice in voices]
        except FileNotFoundError:
            return []



class ConfigManager():
    def __init__(self):
        self.credentials = self.load_credentials()
        self.settings = self.load_settings_from_file()  # Load settings immediately or load when needed
        
    def load_credentials(self):
        # Load credentials from a JSON file
        try:
            with open("credentials.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}  # Return an empty dict if the file does not exist

    def save_settings_to_file(self, settings):
        with open('settings.json', 'w') as f:
            json.dump(settings, f)
         
    def load_settings_from_file(self):
        try:
            with open('settings.json', 'r') as f:
                settings = json.load(f)
            return settings
        except FileNotFoundError:
            return {}  # Return an empty dict if the file does not exist
        except json.JSONDecodeError:
            return {}


class SettingsDialog(QDialog):
    def __init__(self, parent, voiceManager):
        super(SettingsDialog, self).__init__(parent)
        self.voiceManager = voiceManager
        self.initUI()
        self.load_and_apply_settings() 

    def initUI(self):
        layout = QVBoxLayout()
        self.engineCombo = QComboBox()
        self.engineCombo.addItems(['System Voice (SAPI)', 'Polly', 'Google', 'Azure', 'Watson'])
        self.engineCombo.currentIndexChanged.connect(self.on_engine_change)
        layout.addWidget(QLabel("Select TTS Engine:"))
        layout.addWidget(self.engineCombo)

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
        self.on_engine_change(0)  # Initial call to load voices for the default engine

    def load_and_apply_settings(self):
        settings = self.voiceManager.configManager.load_settings_from_file()
        if settings:
            self.apply_settings(settings)

    def apply_settings(self, settings):
        # Set the engine type
        engine_type = settings.get("tts_engine", "System Voice (SAPI)")
        self.engineCombo.setCurrentText(engine_type)
        self.on_engine_change(None)  # Update the voices based on the selected engine

        # Set the selected voice
        voice_id = settings.get("voice_name")
        index = self.voiceCombo.findData(voice_id)
        if index != -1:
            self.voiceCombo.setCurrentIndex(index)

        # Set the speech rate
        rate = settings.get("speech_rate", 200)
        self.rateSlider.setValue(rate)

        # Set the highlight color
        highlight_color = settings.get("highlight_color", "#FFFFFF")  # Default to white
        self.colorButton.setStyleSheet("background-color: {};".format(highlight_color))
        self.colorButton.setText(highlight_color)

    def on_engine_change(self, index):
        engine_choice = self.engineCombo.currentText()
        voices = self.voiceManager.get_voices(engine_choice)
        self.voiceCombo.clear()
        for voice in voices:
            self.voiceCombo.addItem(voice['name'], voice['id'])
        self.credentials_label.setVisible(engine_choice != "System Voice (SAPI)")
        

    def save_settings(self):
        settings = {
            "tts_engine": self.engineCombo.currentText(),
            "voice_name": self.voiceCombo.currentData(),
            "speech_rate": self.rateSlider.value(),
            "highlight_color": self.colorButton.styleSheet().split("background-color: ")[1].split(";")[0]
        }
        self.voiceManager.configManager.save_settings_to_file(settings)
        self.accept()

    def choose_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.colorButton.setStyleSheet("background-color: %s;" % color.name())
            self.colorButton.setText(color.name())



class SpeechThread(QThread):
    finished = pyqtSignal()

    def __init__(self, text, voiceManager, parent=None):
        super(SpeechThread, self).__init__(parent)
        self.text = text
        self.voiceManager = voiceManager

    def run(self):
        if self.voiceManager:
            self.voiceManager.speak(self.text)
        self.finished.emit()

class TextToSpeechApp(QMainWindow):
    def __init__(self, configManager=None):
        super().__init__()
        self.configManager = configManager
        self.settings = self.configManager.load_settings_from_file()
        self.highlight_color = QColor(self.settings.get('highlight_color', '#FFFF00'))
        self.voiceManager = VoiceManager(configManager)
        self.voiceManager.init_engine(self.settings.get('tts_engine', 'system'))
        self.initUI()
        self.apply_settings(self.settings)

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

    def apply_settings(self, settings):
        self.tts_type = settings.get('tts_engine', 'system')
        self.highlight_color = QColor(settings.get('highlight_color', '#FFFF00'))
    
        if self.tts_type == 'system':
            self.engine = pyttsx3.init()
            voice_id = settings.get('voice_name')
            if voice_id:
                self.engine.setProperty('voice', voice_id)
            rate = settings.get('speech_rate', 200)
            self.engine.setProperty('rate', rate)
        else:
            # Initialize appropriate TTS engine based on type
            self.initialize_tts_engine(settings)


    def initialize_tts_engine(self, settings):
        if self.tts_type == 'Google':
            # Example to initialize Google TTS            
            client = GoogleClient(credentials=self.configManager.credentials['Google']['creds_path'])  # Assuming credentials management is handled
            self.engine = client
        elif self.tts_type == 'Polly':
            # Initialize Polly TTS
            client = PollyClient(credentials=(self.configManager.credentials['Polly']['region'], self.configManager.credentials['Polly']['aws_key_id'], self.configManager.credentials['Polly']['aws_access_key']))
            self.engine = client
        elif self.tts_type == 'Azure':
            # Initialize Azure TTS
            client = MicrosoftClient(credentials=self.configManager.credentials['Microsoft']['TOKEN'], region=self.configManager.credentials['Microsoft']['region'])
            self.engine = client
        elif self.tts_type == 'Watson':
            # Initialize Watson TTS
            client = WatsonClient(credentials=(self.configManager.credentials['Watson']['API_KEY'], self.configManager.credentials['Watson']['API_URL']))
            self.engine = client
        else:
            # Log an error or handle unsupported engine types
            print(f"Unsupported TTS engine type: {self.tts_type}")
            
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
        self.thread = SpeechThread(text, self.voiceManager)
        self.thread.finished.connect(self.reset_highlight)
        self.thread.start()

    def reset_highlight(self):
        cursor = self.textEdit.textCursor()
        cursor.setCharFormat(QTextCharFormat())  # Reset format
        cursor.clearSelection()
        self.textEdit.setTextCursor(cursor)

    def open_settings(self):
        dialog = SettingsDialog(self, self.voiceManager)
        if dialog.exec_():
            # When settings window is shut - reload it and apply settings
            self.settings = self.configManager.load_settings_from_file()
            self.apply_settings(self.settings)

def main():
    configManager = ConfigManager()
    app = QApplication(sys.argv)
    ex = TextToSpeechApp(configManager)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
    