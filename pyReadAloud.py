import os
import logging
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QPushButton, QRadioButton,
    QVBoxLayout, QWidget, QDialog, QComboBox, QSlider, QLabel,
    QHBoxLayout, QLineEdit, QColorDialog
)
from PyQt5.QtGui import QTextCursor, QTextCharFormat, QColor, QPalette, QFont
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject
import pyttsx3
from tts_wrapper import (
    PollyClient, PollyTTS, 
    GoogleClient, GoogleTTS, 
    MicrosoftClient, MicrosoftTTS, 
    ElevenLabsClient, ElevenLabsTTS
)
import json
import wave
import pyaudio
import difflib

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("out.log"),
            logging.StreamHandler()
        ]
    )

class VoiceManager(QObject):
    wordSpoken = pyqtSignal(int, int)  # Emit the start and end indices of the spoken word
    speakCompleted = pyqtSignal(str) 
    speechStarted = pyqtSignal()
    
    def __init__(self, configManager):
        super(VoiceManager, self).__init__()
        self.configManager = configManager
        self.engine_client = self.engine_tts = None
        self.engine_type = 'system'  # Default engine type
        self.ttsx_engine = None
        self.current_text = ""
        self.initialize_system_engine()

    def word_boundary_handler(self, word, start_pos, end_pos):
        """Handle word timing events from TTS engines"""
        logging.debug(f"Word boundary event: word='{word}', start={start_pos}, end={end_pos}")
        try:
            if self.wordSpoken:
                # Convert positions to integers if they're not already
                start = int(float(start_pos) * 1000) if isinstance(start_pos, (str, float)) else start_pos
                end = int(float(end_pos) * 1000) if isinstance(end_pos, (str, float)) else end_pos
                
                # Ensure positions are within text bounds
                text_length = len(self.current_text)
                start = max(0, min(start, text_length))
                end = max(0, min(end, text_length))
                
                logging.info(f"Highlighting text from {start} to {end}")
                self.wordSpoken.emit(start, end)
        except Exception as e:
            logging.error(f"Error in word boundary handler: {e}", exc_info=True)

    def word_callback(self, start_char, end_char, word):
        """Handle word timing events from TTS engines"""
        logging.info(f"Word callback: {word} ({start_char:.3f}s - {end_char:.3f}s)")
        try:
            # Find the word position in the current text
            text = self.current_text.lower()
            word = word.lower().strip('.,!?')
            
            logging.debug(f"Looking for word '{word}' in text: '{text}'")
            pos = text.find(word)
            
            if pos >= 0:
                logging.info(f"Found word '{word}' at position {pos}")
                self.wordSpoken.emit(pos, pos + len(word))
            else:
                logging.error(f"Could not find word '{word}' in text")
                
        except Exception as e:
            logging.error(f"Error in word callback: {e}")

    def on_speech_start(self):
        """Handle speech start event"""
        logging.debug("Speech started")
        self.speechStarted.emit()

    def on_speech_end(self):
        """Handle speech end event"""
        logging.debug("Speech ended")
        self.speakCompleted.emit(self.current_text)

    def connect_events(self):
        """Connect to TTS engine events"""
        if self.engine_tts:
            try:
                # Connect word timing callback
                self.engine_tts.connect('onWord', self.word_callback)
                # Connect start/end events
                self.engine_tts.connect('onStart', self.on_speech_start)
                self.engine_tts.connect('onEnd', self.on_speech_end)
                logging.debug("Connected to TTS engine events")
            except Exception as e:
                logging.error(f"Error connecting to TTS events: {e}")

    def speak_threaded(self, text):
        logging.info("Starting threaded speech")
        try:
            if not self.engine_tts:
                logging.warning("No TTS engine selected, using default system voice")
                self.init_engine('system')

            if not text.strip():
                logging.warning("Empty text provided to speak_threaded")
                return

            logging.debug(f"Speaking with engine: {self.engine_type}")
            
            def word_callback(start_char, end_char, word):
                logging.debug(f"Word callback received: word={word}, start={start_char}, end={end_char}")
                info = {
                    'word': word,
                    'start_pos': start_char,
                    'end_pos': end_char
                }
                if self.wordSpoken:
                    self.wordSpoken.emit(info['start_pos'], info['end_pos'])

            ssml_text = self.engine_tts.ssml.add(text)
            logging.debug(f"Starting playback with SSML: {ssml_text}")
            self.engine_tts.start_playback_with_callbacks(ssml_text, callback=word_callback)
            logging.info("Speech completed successfully")
        except Exception as e:
            logging.error(f"Error in speak_threaded: {e}", exc_info=True)
            raise

    def init_tts_wrapper(self, engine_type):
        """Initialize the selected TTS engine"""
        print(f"{engine_type} being set")
        voice_details = self.configManager.settings.get('voice_details', {})
        voice_name = voice_details.get('id')
        lang = voice_details.get('lang')
        
        try:
            if engine_type == 'Google':
                self.engine_client = GoogleClient(credentials=self.configManager.credentials['Google']['creds_path'])
                self.engine_tts = GoogleTTS(client=self.engine_client)
            elif engine_type == 'Polly':
                self.engine_client = PollyClient(credentials=(
                    self.configManager.credentials['Polly']['region'],
                    self.configManager.credentials['Polly']['aws_key_id'],
                    self.configManager.credentials['Polly']['aws_access_key']
                ))
                self.engine_tts = PollyTTS(client=self.engine_client)
            elif engine_type == 'Azure':
                self.engine_client = MicrosoftClient(credentials=(
                    self.configManager.credentials['Microsoft']['token'],
                    self.configManager.credentials['Microsoft']['region']
                ))
                self.engine_tts = MicrosoftTTS(client=self.engine_client)
            elif engine_type == 'ElevenLabs':
                self.engine_client = ElevenLabsClient(credentials=self.configManager.credentials['ElevenLabs']['api_key'])
                self.engine_tts = ElevenLabsTTS(client=self.engine_client)
            else:
                logging.error(f"Unsupported TTS engine type: {engine_type}")
                return

            # Set voice and language if provided
            if voice_name:
                self.engine_tts.set_voice(voice_name, lang_code=lang)
            
            # Connect word timing events
            self.connect_events()
            
        except Exception as e:
            logging.error(f"Error initializing {engine_type} engine: {e}")

    def initialize_system_engine(self):
        """Initialize the system TTS engine using pyttsx3"""
        try:
            self.ttsx_engine = pyttsx3.init()
            logging.debug("Initialized system TTS engine")
        except Exception as e:
            logging.error(f"Error initializing system TTS engine: {e}")
            self.ttsx_engine = None

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
        else:
            self.init_tts_wrapper(engine_type)

        
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
                ssml_text = self.engine_tts.ssml.add(text)
                self.engine_tts.speak(ssml_text)
            except Exception as e:
                logging.debug(f"Error synthesizing or playing audio: {e}")

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

    def on_word_boundary(self, word_info):
        logging.debug(f"Word boundary event received: {word_info}")
        if not word_info or 'word' not in word_info:
            logging.warning("Invalid word_info received in on_word_boundary")
            return

        try:
            word = word_info['word']
            start_pos = word_info.get('start_pos', -1)
            end_pos = word_info.get('end_pos', -1)
            
            if start_pos >= 0 and end_pos >= 0:
                logging.debug(f"Highlighting word: {word} at positions {start_pos}-{end_pos}")
                self.wordSpoken.emit(start_pos, end_pos)
            else:
                # Try fuzzy search if positions are not provided
                text = self.textEdit.toPlainText()
                matches = find_word_positions(text, word)
                if matches:
                    pos = matches[0]  # Use the first match
                    logging.debug(f"Found word '{word}' using fuzzy search at position {pos}")
                    self.wordSpoken.emit(pos, pos + len(word))
                else:
                    logging.warning(f"Could not find word '{word}' in text")
        except Exception as e:
            logging.error(f"Error processing word boundary: {e}", exc_info=True)


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
        self.engineCombo.addItems(['System Voice (SAPI)', 'Polly', 'Google', 'Azure', 'ElevenLabs'])
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
        try:
            logging.info(f"Speech thread starting with text: {self.text[:100]}...")
            self.voiceManager.speak_threaded(self.text)
            logging.info("Speech thread completed")
        except Exception as e:
            logging.error(f"Error in speech thread: {e}", exc_info=True)
        finally:
            self.finished.emit()  # Signal that the speech has finished


class TextToSpeechApp(QMainWindow):
    def __init__(self, configManager=None):
        super().__init__()
        self.initUI()
        self.voiceManager = VoiceManager()
        self.voiceManager.wordSpoken.connect(self.highlight_text)
        self.configManager = configManager or ConfigManager()
        self.load_config()

    def highlight_text(self, start, end):
        """Highlight the specified text range"""
        try:
            cursor = self.textEdit.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            format = cursor.charFormat()
            format.setBackground(QColor(255, 255, 0))  # Yellow highlight
            cursor.mergeCharFormat(format)
            self.textEdit.setTextCursor(cursor)
            logging.info("Successfully highlighted text")
        except Exception as e:
            logging.error(f"Error highlighting text: {e}", exc_info=True)

    def read_text(self):
        """Read the selected text or all text"""
        cursor = self.textEdit.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
        else:
            text = self.textEdit.toPlainText()
            
        if text.strip():
            logging.info(f"Starting to read text: {text[:100]}...")
            self.start_speech(text)
        else:
            logging.warning("No text to read")

    def start_speech(self, text):
        """Start the speech synthesis"""
        try:
            # Create a new thread for speech
            self.speech_thread = SpeechThread(text, self.voiceManager)
            self.speech_thread.finished.connect(self.speech_thread.deleteLater)
            self.speech_thread.start()
            logging.info("Speech thread started")
        except Exception as e:
            logging.error(f"Error starting speech: {e}", exc_info=True)

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

    def apply_settings(self, settings):
        # Set the engine type
        engine_type = settings.get("tts_engine", "System Voice (SAPI)")
        self.voiceManager.init_engine(engine_type)
        self.highlight_color = QColor(settings.get('highlight_color', '#FFFF00'))

            
    def on_speech_started(self):
        """Handle speech start event"""
        logging.debug("Speech started in UI")
        # Clear any previous highlighting
        cursor = self.textEdit.textCursor()
        cursor.select(QTextCursor.Document)
        format = cursor.charFormat()
        format.setBackground(QColor("transparent"))
        cursor.mergeCharFormat(format)

    def on_speak_completed(self, text):
        """Handle speech completion"""
        logging.debug("Speech completed in UI")
        # Clear highlighting
        cursor = self.textEdit.textCursor()
        cursor.select(QTextCursor.Document)
        format = cursor.charFormat()
        format.setBackground(QColor("transparent"))
        cursor.mergeCharFormat(format)
            
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

def find_word_positions(text, word):
    matches = []
    for i in range(len(text)):
        if text[i:i+len(word)] == word:
            matches.append(i)
    return matches

def main():
    logging.info("Starting the application")
    configManager = ConfigManager()
    logging.info("Loaded config Manager")
    app = QApplication(sys.argv)
    # Set font substitutions
    QFont.insertSubstitution("MS Shell Dlg 2", "Segoe UI")
    QFont.insertSubstitution("MS UI Gothic", "Yu Gothic")
    QFont.insertSubstitution("SimSun", "Microsoft YaHei")
    # Optionally set a default font
    ex = TextToSpeechApp(configManager)
    logging.info("Finishing the application")
    sys.exit(app.exec_())
    
if __name__ == '__main__':
    # Setup logging initially
    setup_logging()
    main()