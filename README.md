# Travel Advisory Bot

Бесплатный Telegram бот, который проверяет статусы стран на travel.state.gov 2 раза в день и отправляет уведомления об изменениях.

## Как работает

- Запускается через **GitHub Actions** (полностью бесплатно)
- Проверяет в 08:00 и 20:00 UTC ежедневно
- Сохраняет состояние в репозитории
- Отправляет уведомление в Telegram при изменении уровня advisory

## Быстрая настройка (5 минут)

### 1. Создай Telegram бота

1. Напиши [@BotFather](https://t.me/BotFather) в Telegram
2. Отправь `/newbot`
3. Придумай имя и username
4. **Сохрани токен** (выглядит как `123456789:ABCdefGHIjklMNO...`)

### 2. Узнай свой Chat ID

1. Напиши [@userinfobot](https://t.me/userinfobot) в Telegram
2. Он вернёт твой ID (число вроде `123456789`)
3. **Напиши своему боту** любое сообщение (чтобы активировать чат)

### 3. Создай GitHub репозиторий

1. [Создай новый репозиторий](https://github.com/new) (можно приватный)
2. Загрузи файлы из этой папки:
   ```bash
   cd travel-advisory-bot
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/travel-advisory-bot.git
   git push -u origin main
   ```

### 4. Добавь секреты в GitHub

1. Иди в репозиторий → **Settings** → **Secrets and variables** → **Actions**
2. Нажми **New repository secret** и добавь:
   - `TELEGRAM_BOT_TOKEN` = токен от BotFather
   - `TELEGRAM_CHAT_ID` = твой chat ID

### 5. (Опционально) Укажи страны для мониторинга

По умолчанию мониторятся ВСЕ страны. Чтобы следить только за определёнными:

1. **Settings** → **Secrets and variables** → **Actions** → **Variables**
2. Создай переменную `MONITORED_COUNTRIES`
3. Значение: `Russia,Ukraine,Belarus,Israel` (через запятую)

### 6. Запусти первую проверку

1. Иди в репозиторий → **Actions**
2. Выбери **Check Travel Advisories**
3. Нажми **Run workflow**
4. Бот отправит первое сообщение со статусом!

## Структура уведомлений

```
🚨 Travel Advisory Changes

⬆️ Country Name
   🟡 Level 2 → 🔴 Level 4

🆕 New Country
   🟠 Level 3
```

Уровни:
- 🟢 Level 1: Exercise Normal Precautions
- 🟡 Level 2: Exercise Increased Caution
- 🟠 Level 3: Reconsider Travel
- 🔴 Level 4: Do Not Travel

## Изменить расписание

Отредактируй `.github/workflows/check.yml`:

```yaml
schedule:
  - cron: '0 8 * * *'   # 08:00 UTC
  - cron: '0 20 * * *'  # 20:00 UTC
```

[Генератор cron](https://crontab.guru/)

## Локальный запуск (для тестов)

```bash
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="your-token"
export TELEGRAM_CHAT_ID="your-chat-id"
export MONITORED_COUNTRIES="Russia,Ukraine"  # опционально

python check_advisories.py
```
