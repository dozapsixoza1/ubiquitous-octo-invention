# backup.py
# Запускай перед каждым обновлением: python backup.py

import shutil
from datetime import datetime
from pathlib import Path
from config import Config

def backup():
    db_path = Path(Config.DATABASE_URL.replace('sqlite:///', ''))

    if not db_path.exists():
        print(f"❌ База не найдена: {db_path}")
        return

    backup_dir = Config.BASE_DIR / 'backups'
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_path = backup_dir / f"flybase_backup_{timestamp}.db"

    shutil.copy2(db_path, backup_path)
    print(f"✅ Бэкап создан: {backup_path}")

if __name__ == '__main__':
    backup()
