# FactumAudit Telegram Bot 🤖

ИИ-тестировщик сайтов в Telegram. Аудит по URL, анализ HTML, SEO и UX-советы.

## Быстрый старт

### 1. Получи токены

**Telegram Bot Token:**
1. Напиши [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Придумай имя и username для бота
4. Скопируй токен вида `7123456789:AAH...`

**Anthropic API Key:**
1. Зайди на [console.anthropic.com](https://console.anthropic.com)
2. API Keys → Create Key
3. Скопируй ключ вида `sk-ant-api03-...`

### 2. Установи зависимости

```bash
# Клонируй или распакуй проект
cd factumaudit-bot

# Создай виртуальное окружение
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# Установи библиотеки
pip install -r requirements.txt
```

### 3. Настрой переменные окружения

```bash
cp .env.example .env
nano .env  # или открой в любом редакторе
```

Заполни `.env`:
```
TELEGRAM_BOT_TOKEN=7123456789:AAH...
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### 4. Запусти бота

```bash
python bot.py
```

Открой Telegram, найди своего бота и напиши `/start` 🎉

---

## Запуск через Docker

```bash
# Сборка
docker build -t factumaudit-bot .

# Запуск
docker run -d \
  --name factumaudit \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=ваш_токен \
  -e ANTHROPIC_API_KEY=ваш_ключ \
  factumaudit-bot
```

---

## Деплой на сервер (systemd)

### На Ubuntu/Debian:

```bash
# Загрузи файлы на сервер
scp -r factumaudit-bot/ user@server:/opt/factumaudit-bot/

# На сервере
cd /opt/factumaudit-bot
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env  # заполни токены
```

Создай systemd-сервис `/etc/systemd/system/factumaudit.service`:

```ini
[Unit]
Description=FactumAudit Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/factumaudit-bot
EnvironmentFile=/opt/factumaudit-bot/.env
ExecStart=/opt/factumaudit-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable factumaudit
sudo systemctl start factumaudit
sudo systemctl status factumaudit   # проверить статус
sudo journalctl -u factumaudit -f   # смотреть логи
```

---

## Деплой на Railway (бесплатно)

1. Зайди на [railway.app](https://railway.app)
2. New Project → Deploy from GitHub (загрузи репозиторий)
3. В Variables добавь:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
4. Deploy — Railway сам подхватит Dockerfile

---

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | Главное меню с кнопками |
| `/audit` | Полный аудит сайта (выбор категорий) |
| `/html` | Анализ HTML-кода или файла |
| `/seo` | SEO-анализ по URL |
| `/ux` | UX-советы по URL |
| `/help` | Справка |
| `/cancel` | Отменить текущее действие |

Также можно просто написать вопрос — бот ответит как консультант по веб-разработке.

---

## Структура проекта

```
factumaudit-bot/
├── bot.py            ← весь код бота
├── requirements.txt  ← зависимости Python
├── .env.example      ← шаблон переменных окружения
├── .env              ← ваши ключи (не коммитить в git!)
├── Dockerfile        ← для Docker-деплоя
└── README.md
```

## Требования

- Python 3.11+
- ~50 МБ RAM
- Стабильный интернет (polling Telegram API)
