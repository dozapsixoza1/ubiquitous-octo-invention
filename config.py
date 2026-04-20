# config.py
import os
from pathlib import Path

class Config:
    # Токен бота
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    
    # ID администраторов (через запятую)
    ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
    
    # База данных
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///antbase.db')
    
    # Настройки бота
    BOT_NAME = "ANT BASE"
    BOT_VERSION = "1.0.0"
    
    # Пути к файлам
    BASE_DIR = Path(__file__).parent
    MEDIA_DIR = BASE_DIR / 'media'
    LOGS_DIR = BASE_DIR / 'logs'

# Создаем необходимые директории
Config.MEDIA_DIR.mkdir(exist_ok=True)
Config.LOGS_DIR.mkdir(exist_ok=True)