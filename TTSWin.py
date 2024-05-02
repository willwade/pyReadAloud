import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget, QDialog, QComboBox, QSlider, QLabel, QHBoxLayout, QLineEdit, QColorDialog
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject, QLoggingCategory
from PyQt5.QtGui import QFont
import pyttsx3
from tts_wrapper import PollyClient, PollyTTS, GoogleClient, GoogleTTS, MicrosoftClient, MicrosoftTTS
import wave
import pyaudio
import json



        
class VoiceManager(QObject):
    wordSpoken = pyqtSignal(int, int)  # Emit the start and end indices of the spoken word

    def __init__(self, configManager):
        super(VoiceManager, self).__init__()
        self.configManager = configManager
        self.engine = None
        self.engine_type = 'system'  # Default engine type
        self.ttsx_engine = pyttsx3.init()  # Initialize pyttsx3 engine immediately
        self.setup_callbacks()

    def setup_callbacks(self):
        if self.engine_type == 'system':
            self.ttsx_engine.connect('started-word', self.on_word)
    
    def on_word(self, name, location, length):
        self.wordSpoken.emit(location, location + length)

    def speak(self, text):
        if self.engine_type == 'system':
            self.ttsx_engine.say(text)
            self.ttsx_engine.startLoop(False)  # Start in non-blocking mode
        else:
            self.speak_with_timing(text)

    def speak_with_timing(self, text):
        words = text.split()
        position = 0  # This variable will be modified inside emit_word_timing
        durations = [len(word) / 5.0 for word in words]  # Estimate 0.2 seconds per character
    
        def emit_word_timing():
            nonlocal position  # Correct placement of nonlocal
            if not words:  # Check if there are no more words left to process
                return
            duration = durations.pop(0)
            word = words.pop(0)
            start = position
            end = start + len(word)
            self.wordSpoken.emit(start, end)
            QTimer.singleShot(int(duration * 1000), emit_word_timing)
            position = end + 1  # Update position for the next word
    
        emit_word_timing()

    def stop_speak(self):
        if self.engine_type == 'system':
            self.ttsx_engine.endLoop()     
            
    def init_engine(self, engine_type='system'):
        self.engine_type = engine_type
        if engine_type == 'system' or engine_type == 'System Voice (SAPI)':
            self.engine = self.ttsx_engine
            self.engine.setProperty('voice_id', self.configManager.settings.get('voice_name'))
            self.engine.setProperty('rate', self.configManager.settings.get('speech_rate', 200))            
        elif engine_type == 'Google':
            self.engine = GoogleTTS(client=GoogleClient(credentials=self.configManager.credentials['Google']['creds_path']))
        elif engine_type == 'Polly':
            self.engine = PollyTTS(client=PollyClient(credentials=(self.configManager.credentials['Polly']['region'], self.configManager.credentials['Polly']['aws_key_id'], self.configManager.credentials['Polly']['aws_access_key'])), voice=self.configManager.settings.get('voice_name'))
        elif engine_type == 'Azure':
            self.engine = MicrosoftTTS(client=MicrosoftClient(credentials=self.configManager.credentials['Microsoft']['TOKEN'], region=self.configManager.credentials['Microsoft']['region']), voice=self.configManager.settings.get('voice_name'))
        elif engine_type == 'Watson':
            self.engine = WatsonTTS(client=WatsonClient(credentials=(self.configManager.credentials['Watson']['API_KEY'], self.configManager.credentials['Watson']['API_URL'])), voice=self.configManager.settings.get('voice_name'))
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
                return [{'name': voice['nicename'], 'id': voice['name'], 'details': voice} for voice in voices]
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
        self.voiceManager.speak(self.text)
        self.finished.emit()  # Signal that the speech has finished

class TextToSpeechApp(QMainWindow):
    def __init__(self, configManager=None):
        super().__init__()
        self.configManager = configManager
        self.settings = self.configManager.load_settings_from_file()
        self.highlight_color = QColor(self.settings.get('highlight_color', '#FFFF00'))
        self.voiceManager = VoiceManager(configManager)
        self.voiceManager.init_engine(self.settings.get('tts_engine', 'system'))
        self.voiceManager.wordSpoken.connect(self.highlight_text)
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
        self.highlight_color = QColor(settings.get('highlight_color', '#FFFF00'))

            
    def read_text(self):
        cursor = self.textEdit.textCursor()
        text = self.textEdit.toPlainText()
        
        # Get the current position of the cursor in the text
        cursor_position = cursor.position()
    
        # Determine the text to read based on the selected radio button
        selected_text = ""
        if self.radio_sentence.isChecked():
            selected_text = self.extract_sentence(text, cursor_position)
        elif self.radio_paragraph.isChecked():
            selected_text = self.extract_paragraph(text, cursor_position)
        elif self.radio_word.isChecked():
            selected_text = self.extract_word(text, cursor_position)
        elif self.radio_all.isChecked():
            selected_text = text  # Read all text
    
        self.start_speech(selected_text)
    
    def extract_sentence(self, text, pos):
        # Find the nearest sentence around the cursor position
        start = text.rfind('.', 0, pos) + 1
        if start < 0: start = 0
        end = text.find('.', pos)
        if end < 0: end = len(text)
        return text[start:end].strip()
    
    def extract_paragraph(self, text, pos):
        # Find the nearest paragraph around the cursor position
        start = text.rfind('\n', 0, pos) + 1
        if start < 0: start = 0
        end = text.find('\n', pos)
        if end < 0: end = len(text)
        return text[start:end].strip()
    
    def extract_word(self, text, pos):
        # Find the nearest word around the cursor position
        separators = ' ,.;:\n'
        start = max(text.rfind(s, 0, pos + 1) for s in separators if s in text) + 1
        end = min((text.find(s, pos) for s in separators if s in text), default=len(text))
        return text[start:end].strip()


    def start_speech(self, text):
        self.textEdit.setPlainText(text)
        self.thread = SpeechThread(text, self.voiceManager)
        self.thread.finished.connect(self.reset_highlight)
        self.thread.start()

    def highlight_text(self, start, end, format):
        cursor = self.textEdit.textCursor()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, end - start)
        format = QTextCharFormat()
        format.setBackground(QColor(self.settings.get('highlight_color', '#FFFF00')))
        cursor.setCharFormat(format)
        self.textEdit.setTextCursor(cursor)

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
    QLoggingCategory.setFilterRules('qt.fonts=false')
    configManager = ConfigManager()
    app = QApplication(sys.argv)
    # Set font substitutions
    QFont.insertSubstitution("MS Shell Dlg 2", "Segoe UI")
    QFont.insertSubstitution("MS UI Gothic", "Yu Gothic")
    QFont.insertSubstitution("SimSun", "Microsoft YaHei")
    # Optionally set a default font
    ex = TextToSpeechApp(configManager)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
    