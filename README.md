# Telegram Channel Mirror Bot

A Telegram bot built with aiogram v3 that automatically mirrors (forwards) posts between channels while preserving formatting and supporting link replacement rules.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![aiogram 3.x](https://img.shields.io/badge/aiogram-3.x-blue.svg)](https://docs.aiogram.dev/)

## Features

- 🔄 Mirror posts between multiple source and destination channels
- 📝 Preserve message formatting (HTML)
- 🔗 Replace links using regex patterns
- 📎 Support for all major content types:
  - Text messages
  - Photos and videos
  - Documents and animations
  - Audio and voice messages
  - Video notes
  - Polls (both regular and quiz)
- 💾 SQLite storage for configuration (can be replaced with PostgreSQL)
- 🔐 Admin-only configuration commands

## Requirements

- Python 3.11 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Admin access to source and destination channels

### Telegram API Limitations
- Bot must be an **administrator** in source channels to receive posts
- Bot must be an **administrator** in destination channels to post content
- Media albums are currently sent one by one (will be improved in future versions)

## Швидкий старт
1) Встановіть Python 3.11+
2) Клон/розпакуйте проект, перейдіть у папку
3) Створіть віртуальне оточення та встановіть залежності:
   ```bash
   pip install -r requirements.txt
   ```
4) Скопіюйте `.env.example` у `.env` і заповніть `BOT_TOKEN` та `ADMIN_IDS`
5) Запустіть:
   ```bash
   python bot.py
   ```

## Команди (для адмінів)
- `/add_source` — викликайте в каналі-джерелі, щоб зареєструвати його
- `/add_dest` — викликайте в каналі-призначенні
- `/channels` — список каналів
- `/map <source_tg_id> <dest_tg_id>` — створити зв'язок
- `/unmap <source_tg_id> <dest_tg_id>` — видалити зв'язок
- `/rules` — список правил заміни посилань
- `/addrule <pattern> <replacement>` — додати правило (регулярний вираз)
- `/delrule <id>` — видалити правило за ID

### Приклад правил заміни
- Замінити всі посилання `example.com` на ваш реферальний домен:
  ```
  /addrule https?://(www\.)?example\.com https://mydomain.com
  ```
- Додати UTM-мітки:
  ```
  /addrule (https?://[^\s"<]+) \1?utm_source=mirror
  ```
  (для складних випадків краще писати більш точні патерни)

## Деплой
- Рекомендовано запускати як systemd-сервіс або у Docker.
- Якщо потрібно — додайте вебхук; зараз використовується long-polling для простоти.

## Розширення (TODO)
- Збірка альбомів за `media_group_id` з таймаутом 1–2 с і спільною публікацією
- Відстеження відповідності `source_msg_id ➜ dest_msg_id` для редагувань/видалень
- Панель керування (FastAPI) і PostgreSQL
