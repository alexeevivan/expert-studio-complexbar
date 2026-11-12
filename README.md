# ComplexBar Telegram Bot

Telegram-бот для приватной супергруппы ComplexBar с форумными топиками.

Возможности:

- подготовка HTML-постов в личном чате с ботом;
- выбор топика перед публикацией и предпросмотр поста;
- публикация текста и фотографий;
- приватные обращения пользователей в поддержку;
- отдельный топик поддержки для каждого пользователя;
- сохранение истории обращений в SQLite.

## Локальный запуск

Требуется Python 3.10 или новее. На сервере проект проверен с Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python bot.py
```

Заполните `.env` реальными значениями перед запуском. Файл `.env` содержит секреты и не добавляется в Git.

## Переменные окружения

- `BOT_TOKEN` — токен бота от BotFather.
- `ADMIN_CHAT_ID` — ID основной приватной супергруппы.
- `ADMIN_IDS` — Telegram ID администраторов через запятую.
- `SUPPORT_CHAT_ID` — ID отдельной супергруппы поддержки с включёнными топиками.
- `TOPIC_JOURNAL`, `TOPIC_LIBRARY`, `TOPIC_JOBOFFERS`, `TOPIC_CONTACT`, `TOPIC_MANIFESTO` — ID топиков основной группы.
- `DATABASE_PATH` — путь к SQLite-базе, по умолчанию `complexbar.db`.

Топик Events является переименованным General, поэтому для него отдельный `message_thread_id` не требуется.

## Команды

- `/post` — в личном чате выбрать топик, подготовить пост и подтвердить публикацию.
- `/cancel` — отменить подготовку поста.
- `/setupcontact` — разместить и закрепить кнопку обращения в поддержку в топике Contact us.
- `/topicid` — показать ID текущего топика администратору.
- `/chatid` — показать ID текущего чата.

## Тесты

```bash
python -m unittest -v
```

## Развёртывание на сервере

Бот развёртывается вне публичного каталога сайта. Это защищает `.env` и SQLite-базу от доступа через веб-сервер.

Требования к серверу:

- Python 3.10 или новее;
- Git и доступ к `api.telegram.org`;
- разрешённые постоянные фоновые процессы;
- GNU Screen или другой менеджер процессов.

Пример установки на хостинге с Python 3.13 от ISPmanager:

```bash
cd "$HOME"
git clone https://github.com/alexeevivan/expert-studio-complexbar.git complexbar-bot
cd complexbar-bot

/opt/ispmanager/python3.13/bin/python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v
```

Создайте серверный `.env` из шаблона и ограничьте доступ к нему:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Для хранения базы вне исходного кода можно указать абсолютный путь:

```dotenv
DATABASE_PATH=/var/www/<hosting-user>/data/complexbar-bot/data/complexbar.db
```

Не добавляйте `.env` и SQLite-базу в Git. Не передавайте токен бота, пароль хостинга и приватные SSH-ключи через сообщения или файлы репозитория.

### Постоянный запуск через Screen

Перед серверным запуском остановите локальную копию бота. Telegram не допускает одновременную работу двух polling-процессов с одним токеном.

```bash
cd "$HOME/complexbar-bot"
mkdir -p logs

screen -dmS complexbar-bot bash -lc \
  'cd "$HOME/complexbar-bot" && exec .venv/bin/python -u bot.py >> logs/bot.log 2>&1'
```

Проверка процесса и журнала:

```bash
screen -ls
tail -n 30 "$HOME/complexbar-bot/logs/bot.log"
```

Управление процессом:

```bash
# Подключиться к работающей сессии
screen -r complexbar-bot

# Остановить бота
screen -S complexbar-bot -X quit

# Смотреть журнал в реальном времени
tail -f "$HOME/complexbar-bot/logs/bot.log"
```

Чтобы выйти из подключённой сессии без остановки бота, нажмите `Ctrl+A`, затем `D`.

Screen сохраняет процесс после выхода из SSH, но не запускает его после перезагрузки сервера. Для автоматического восстановления потребуется отдельная задача Cron или менеджер процессов.

### Обновление бота на сервере

```bash
cd "$HOME/complexbar-bot"
screen -S complexbar-bot -X quit

git pull --ff-only
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v

mkdir -p logs
screen -dmS complexbar-bot bash -lc \
  'cd "$HOME/complexbar-bot" && exec .venv/bin/python -u bot.py >> logs/bot.log 2>&1'
```

## Приватный GitHub-репозиторий

Репозиторий можно сделать приватным. Уже запущенный бот продолжит работать, потому что файлы находятся на сервере.

После смены видимости анонимные `git clone` и `git pull` перестанут работать. Для последующих обновлений настройте на сервере отдельный SSH deploy key с доступом только на чтение и замените адрес `origin`:

```bash
git remote set-url origin git@github.com:alexeevivan/expert-studio-complexbar.git
```

Не сохраняйте GitHub-токены или приватную часть deploy key в репозитории.
