import os
import sys
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QTextEdit, QPushButton, QRadioButton, QVBoxLayout, QWidget, QDialog, QComboBox, QSlider, QLabel, QHBoxLayout, QLineEdit, QColorDialog
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject, QLoggingCategory
from PyQt5.QtGui import QFont
import pyttsx3
from tts_wrapper import PollyClient, PollyTTS, GoogleClient, GoogleTTS, MicrosoftClient, MicrosoftTTS
import wave
import pyaudio
import json

logging.basicConfig(level=logging.DEBUG,format='%(name)s - %(levelname)s - %(message)s')

        
class VoiceManager(QObject):
    wordSpoken = pyqtSignal(int, int)  # Emit the start and end indices of the spoken word
    speakCompleted = pyqtSignal(str) 
    
    def __init__(self, configManager):
        super(VoiceManager, self).__init__()
        self.configManager = configManager
        self.engine = None
        self.engine_type = 'system'  # Default engine type
        self.initialize_ttsx_engine()

    def initialize_ttsx_engine(self):
        self.ttsx_engine = pyttsx3.init()
        self.connect_events()

    def connect_events(self):
        # Connecting to the started-word event
        self.ttsx_engine.connect('started-word', self.on_word)
        logging.debug("Connected to pyttsx3 started-word event.")
        
    def on_word(self, name, location, length):
        logging.debug(f"[on_word] Word started: {name} at {location} with length {length}")
        if location >= 0 and length > 0:
            self.wordSpoken.emit(location, location + length)
        else:
            logging.error(f"[on_word] Invalid word parameters: location={location}, length={length}")

    def speak_threaded(self, word):
        logging.debug(f"[speak_threaded] speak called  {word} with {self.engine_type}")
        if self.engine_type == 'system' or self.engine_type == 'System Voice (SAPI)':
            logging.debug(f"[speak_threaded with system] speaking {word}")
            self.ttsx_engine.say(word)
            self.ttsx_engine.runAndWait()
            self.speakCompleted.emit(word)  # Emit after speaking
        else:
            try:
                logging.debug(f"[speak with wrapper] speaking with timing {word}")
                audio_bytes = self.engine.synth_to_bytes(self.engine.ssml.add(word), format='wav')
                self.play_audio(audio_bytes)
                self.speakCompleted.emit(word)  # Emit after audio played
            except Exception as e:
                logging.error(f"Error in synthesizing or playing audio: {e}")
                self.speakCompleted.emit(word)  # Still emit to continue the process

    def speak_with_timing(self, text):
        words = text.split()
        durations = [len(word) / 5.0 for word in words]  # Adjust time per character if necessary
    
        def speak_next_word(index=0):
            if index < len(words):
                word = words[index]
                duration = durations[index]
                start = sum(len(w) + 1 for w in words[:index])  # calculate start index
                end = start + len(word)
                logging.debug(f"Emitting word: {word}, Start: {start}, End: {end}, Duration: {duration}")
                self.wordSpoken.emit(start, end)
                self.speak_threaded(word)
                QTimer.singleShot(int(duration * 1000), lambda: speak_next_word(index + 1))
    
        speak_next_word()  # Start the recursive timing
    
            
    def init_engine(self, engine_type='system'):
        self.engine_type = engine_type
        voice_details = self.configManager.settings.get('voice_details', {})
        voice_name = voice_details.get('id')
        lang = voice_details.get('lang')
        logging.debug(f"Voice details retrieved: {voice_details}")
        logging.debug(f"Voice name: {voice_name}, Language: {lang}")
        if engine_type == 'system' or engine_type == 'System Voice (SAPI)':
            self.engine = self.ttsx_engine
            self.engine.setProperty('voice', voice_name)
            self.engine.setProperty('rate', self.configManager.settings.get('speech_rate', 200))            
        elif engine_type == 'Google':
            self.engine = GoogleTTS(client=GoogleClient(credentials=self.configManager.credentials['Google']['creds_path']), lang=lang, voice=voice_name)
        elif engine_type == 'Polly':
            self.engine = PollyTTS(client=PollyClient(credentials=(self.configManager.credentials['Polly']['region'], self.configManager.credentials['Polly']['aws_key_id'], self.configManager.credentials['Polly']['aws_access_key'])), voice=voice_name, lang=lang)
        elif engine_type == 'Azure':
            self.engine = MicrosoftTTS(client=MicrosoftClient(credentials=self.configManager.credentials['Microsoft']['TOKEN'], region=self.configManager.credentials['Microsoft']['region']), voice=voice_name, lang=lang)
        elif engine_type == 'Watson':
            self.engine = WatsonTTS(client=WatsonClient(credentials=(self.configManager.credentials['Watson']['API_KEY'], self.configManager.credentials['Watson']['API_URL'])), voice=voice_name, lang=lang)
        else:
            logging.debug(f"Unsupported TTS engine type: {engine_type}")

        
    def get_voices(self, engine_type):
        if engine_type == 'system' or engine_type == 'System Voice (SAPI)':
            voices = self.ttsx_engine.getProperty('voices')
            enhanced_voices = []
            for voice in voices:
                # Extracting the gender and assigning default if None
                if voice.gender is None:
                    gender = 'M'
                else:
                    gender = 'F' if 'female' in voice.gender.lower() else 'N' if 'neuter' in voice.gender.lower() else 'M'
                
               # Extracting the first language or a default if the list is empty
                language = voice.languages[0] if voice.languages else voice.id.split('.')[-1].split('-')[0]
        
                # Adding voice information to the list
                enhanced_voices.append({
                    'name': voice.name,
                    'nicename': voice.name,
                    'id': voice.id,
                    'lang': language,
                    'gender': gender
                })
            return enhanced_voices
        else:
            return self.load_voices_from_service(engine_type)

    def get_lang_for_voice_id(self, engine_type, voice_id):
        if self.engine_type == 'system' or self.engine_type == 'System Voice (SAPI)':
            # For SAPI, language code is not directly available; you might infer or return a default
            voices = self.ttsx_engine.getProperty('voices')
            for voice in voices:
                if voice.id == voice_id:
                    # Example to infer language from voice name, if it includes language information
                    lang = voice.name.split('-')[-1] if '-' in voice.name else 'en-US'  # Example inference
                    return lang
            return 'en-US'  # Return a default if no match or inference is possible
        else:
            voices = self.load_voices_from_service(engine_type)
            for voice in voices:
                if voice['id'] == voice_id:
                    # Assume that the language code is stored in 'country'
                    return voice['country']
            return None  # Return None or a default if no match is found
            
    def speak(self, text):
        logging.debug(f"[speak] calling speak speak - the final one.. {text} with {self.engine_type}")
        if self.engine_type == 'system' or self.engine_type == 'System Voice (SAPI)':
            # Using pyttsx3
            self.engine.say(text)
            self.engine.runAndWait()
        elif self.engine_type != 'system':
            # Using TTS-Wrapper
            try:    
                logging.debug(f"speaking now.. {text}")
                audio_bytes = self.engine.synth_to_bytes(self.engine.ssml.add(text), format='wav')
                self.play_audio(audio_bytes)
            except Exception as e:
                logging.debug(f"Error synthesizing or playing audio: {e}")


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
        if self.engine_type == 'system' or self.engine_type == 'System Voice (SAPI)' and self.ttsx_engine:
            self.ttsx_engine.stop()

    def load_voices_from_service(self, engine_name):
        # Handle voice loading from JSON files for non-system engines
        engine_name = engine_name.lower()
        try:
            with open(f"{engine_name}_voices.json", "r") as file:
                voices = json.load(file)
                return [{'name': voice['nicename'], 'id': voice['name'], 'lang': voice['country'], 'details': voice} for voice in voices]
        except FileNotFoundError:
            logging.debug(f"{engine_name}_voices.json couldnt be found")
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
 
    def load_settings_from_file(self):
        try:
            with open('settings.json', 'r') as f:
                settings = json.load(f)
            logging.debug(f"Settings loaded from file: {settings}")
            return settings
        except FileNotFoundError:
            logging.debug("Settings file not found, returning default settings.")
            return {}  # Return default settings if file is missing

    def save_settings_to_file(self, settings):
        logging.debug(f"Saving settings to file: {settings}")
        with open('settings.json', 'w') as f:
            json.dump(settings, f, ensure_ascii=True, indent=4)
        self.settings = settings  # Update the internal state to the new settings


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


    def find_voice_index_by_id(self, voice_id):
        for index in range(self.voiceCombo.count()):
            if self.voiceCombo.itemData(index).get('id') == voice_id:
                return index
        return -1
    

    def apply_settings(self, settings):
        # Set the engine type
        engine_type = settings.get("tts_engine", "System Voice (SAPI)")
        self.engineCombo.setCurrentText(engine_type)
        self.on_engine_change(None)  # Update the voices based on the selected engine

        # Set the selected voice
        voice_details = settings.get("voice_details", {})
        voice_id = voice_details.get('id')
        index = self.find_voice_index_by_id(voice_id)
        if index != -1:
            self.voiceCombo.setCurrentIndex(index)
        else:
            logging.debug(f"Voice ID {voice_id} not found in the voice list.")


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
        if voices:  # Check if voices is not None and not empty
            for voice in voices:
                display_name = voice.get('nicename', voice.get('name', 'Unknown Voice'))
                self.voiceCombo.addItem(display_name, voice)
        else:
            logging.debug(f"Warning: No voices found for engine {engine_choice}")
        self.credentials_label.setVisible(engine_choice != "System Voice (SAPI)")


    def save_settings(self):
        settings = {
            "tts_engine": self.engineCombo.currentText(),
            "voice_details": self.voiceCombo.currentData(),
            "speech_rate": self.rateSlider.value(),
            "highlight_color": self.colorButton.styleSheet().split("background-color: ")[1].split(";")[0]
        }
        logging.debug(f"Settings before saving: {settings}")
        self.voiceManager.configManager.save_settings_to_file(settings)
        test_settings = self.voiceManager.configManager.load_settings_from_file()
        logging.debug(f"Settings immediately after saving: {test_settings}")
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
        logging.debug(f"[speachthread run] called {self.text}")
        self.voiceManager.speak_threaded(self.text)
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
        self.voiceManager.speakCompleted.connect(self.on_speak_completed)
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
        logging.debug(f"[start_speech] called.. here we go..")
        self.textEdit.setPlainText(text)
        self.thread = SpeechThread(text, self.voiceManager)
        self.thread.finished.connect(self.reset_highlight)
        self.thread.start()

        
    def highlight_text(self, start, end):
        logging.debug(f"[highlight_text] Highlighting text from {start} to {end}")
        try:
            if end > start and start >= 0:
                cursor = self.textEdit.textCursor()
                cursor.setPosition(start)
                cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, end - start)
                format = QTextCharFormat()
                format.setBackground(QColor(self.settings.get('highlight_color', '#FFFF00')))
                cursor.setCharFormat(format)
                self.textEdit.setTextCursor(cursor)
            else:
                logging.error(f"Invalid indices for highlighting: start={start}, end={end}")
        except Exception as e:
            logging.debug(f"Error highlighting text: {e}")

    def on_speak_completed(self, word):
        logging.debug(f"[on speak completed] Finished speaking: {word}")
        # Logic to decide the next word to speak
        # next_word = self.get_next_word()
#         if next_word:
#             self.voiceManager.speak(next_word)
            
    def closeEvent(self, event):
        self.voiceManager.shutdown()
        event.accept()

    def reset_highlight(self):
        cursor = self.textEdit.textCursor()
        cursor.setCharFormat(QTextCharFormat())  # Reset format
        cursor.clearSelection()
        self.textEdit.setTextCursor(cursor)

    def open_settings(self):
        dialog = SettingsDialog(self, self.voiceManager)
        if dialog.exec_():
            self.settings = self.voiceManager.configManager.load_settings_from_file()
            logging.debug(f"Settings after reopening settings dialog: {self.settings}")
            self.apply_settings(self.settings)
            self.voiceManager.init_engine(self.settings.get('tts_engine', 'System Voice (SAPI)'))
            #self.voiceManager.init_engine(self.settings.get('tts_engine', 'System Voice (SAPI)'), self.settings)


def main():

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
    