# Развёртывание

Один сервер, всё в Docker: Caddy (HTTPS) → витрина Nuxt и бэкенд Django, плюс Celery,
PostgreSQL, Redis, Meilisearch и ежедневные бэкапы. Конфигурация — `infra/docker-compose.prod.yml`.

```
Интернет → Caddy :443 ─┬─ /api, /admin, /static → backend (gunicorn) ─┬─ PostgreSQL
                       ├─ /media → файлы на диске                     ├─ Redis ← worker, beat (Celery)
                       └─ всё остальное → frontend (Nuxt SSR)         └─ Meilisearch
```

## Сервер

- VPS: **2 vCPU, 4 ГБ RAM, 40 ГБ SSD** (Hetzner CX22, DigitalOcean, местный хостинг), Ubuntu 24.04.
- Открыты порты 22, 80, 443.
- DNS: A-записи `maison.uz` и `www.maison.uz` → IP сервера (для тестового — `dev.maison.uz`).

## Первый запуск

```bash
# 1. Docker
curl -fsSL https://get.docker.com | sh

# 2. Код
git clone https://github.com/IwantPizza-404/maison.git && cd maison

# 3. Настройки: заполнить секреты (openssl rand -hex 32), DOMAIN, Telegram-бот
cp infra/.env.prod.example infra/.env.prod
nano infra/.env.prod

# 4. Сборка, миграции, запуск
./scripts/deploy.sh

# 5. Администратор и справочники (без демо-товаров)
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec backend python manage.py createsuperuser
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec backend python manage.py seed_catalog
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod exec backend python manage.py update_rates
```

HTTPS-сертификат Caddy получает сам при первом запросе (DNS уже должен указывать на сервер).

### Telegram-бот

Один бот для всего: вход покупателей, уведомления покупателям и менеджеру.

1. @BotFather → `/newbot` → токен и username в `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`.
2. `TELEGRAM_WEBHOOK_SECRET` — `openssl rand -hex 32`.
3. `TELEGRAM_MANAGER_CHAT_ID` — id чата менеджера: написать боту, затем
   `https://api.telegram.org/bot<токен>/getUpdates` → `message.chat.id` (для группы — добавить бота в группу).
4. `deploy.sh` сам регистрирует вебхук (`telegram_set_webhook`).

Локально бот работает без вебхука: `make bot` (long polling).

### Вход через WhatsApp (необязательно)

Код входа отправляется через WhatsApp Cloud API (Meta). Пока ключи не заданы, способ на сайте не показывается.

1. [developers.facebook.com](https://developers.facebook.com) → создать приложение типа Business → добавить продукт WhatsApp.
2. Подключить номер магазина (WhatsApp → API Setup) и пройти верификацию бизнеса в Meta Business Manager —
   без неё сообщения уходят только на тестовые номера.
3. WhatsApp Manager → Message templates → создать шаблон категории **Authentication**
   (с кнопкой «Скопировать код»), имя `login_code`, язык Russian. Дождаться одобрения.
4. Постоянный токен: Business Settings → System users → создать пользователя с правами на WhatsApp →
   Generate token (`whatsapp_business_messaging`).
5. В `infra/.env.prod`: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` (из API Setup), при другом имени или языке
   шаблона — `WHATSAPP_TEMPLATE`, `WHATSAPP_TEMPLATE_LANGUAGE`. Затем `./scripts/deploy.sh`.

Сообщения-авторизации в WhatsApp платные (тариф Meta зависит от страны получателя);
лимит — 3 кода в час на номер.

### Тестовый сервер (staging)

В `infra/.env.prod`: `DOMAIN=dev.maison.uz`, `CADDYFILE=Caddyfile.staging`, `NUXT_INDEXABLE=false`,
`STAGING_USER` и `STAGING_PASSWORD_HASH`:

```bash
docker run --rm caddy:2.10-alpine caddy hash-password --plaintext 'пароль'
```

Весь сайт закрыт паролем, `robots.txt` запрещает индексацию.

### Продакшен

`DOMAIN=maison.uz`, `CADDYFILE=Caddyfile`, **`NUXT_INDEXABLE=true`**.

## Обновление

```bash
./scripts/deploy.sh   # git pull → сборка → миграции → перезапуск → поисковый индекс
```

### Автодеплой (CI/CD)

`.github/workflows/ci.yml`: на каждый push и pull request — линтеры, тесты, сборка фронтенда
и Docker-образов. После зелёного CI в `main` джоба `deploy` заходит на сервер по SSH
и запускает `./scripts/deploy.sh`. Пока секреты не заданы, деплой пропускается.

Ключ GitHub ограничен на сервере одной командой — даже утёкший ключ не даёт доступа к серверу.

1. Отдельный ключ (на своём компьютере, без пароля):
   ```bash
   ssh-keygen -t ed25519 -N "" -C "github-actions-deploy" -f ~/.ssh/maison_deploy
   ```
2. На сервере — публичный ключ в `/root/.ssh/authorized_keys` **одной строкой** с ограничением:
   ```
   command="cd /opt/maison && ./scripts/deploy.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA… github-actions-deploy
   ```
3. Проверка с компьютера: `ssh -i ~/.ssh/maison_deploy root@IP` — должен запуститься деплой.
4. GitHub → репозиторий → Settings → Secrets and variables → Actions → New repository secret:
   - `DEPLOY_HOST` — IP или домен сервера;
   - `DEPLOY_SSH_KEY` — содержимое `~/.ssh/maison_deploy` (приватный ключ целиком);
   - `DEPLOY_KNOWN_HOSTS` — вывод `ssh-keyscan -t ed25519 IP`;
   - `DEPLOY_USER` — если не `root` (необязательно).

Ход деплоя — во вкладке Actions репозитория. Ручной `./scripts/deploy.sh` на сервере работает как раньше.

## Полезные команды

```bash
alias dc='docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod'
dc ps                          # состояние сервисов
dc logs -f backend worker      # логи
dc exec backend python manage.py shell
dc restart frontend
```

## Бэкапы

- Дамп базы — ежедневно в `infra/backups/` (14 дневных, 4 недельных, 6 месячных).
- Ручной бэкап: `dc exec backup /backup.sh`.
- **Рекомендуется копировать `infra/backups/` за пределы сервера** (Cloudflare R2, другой сервер):
  бэкап на том же диске не спасёт при потере сервера.
- Фото (том `media`) в бэкап базы не входят — для продакшена лучше хранить их в Cloudflare R2
  (переменные `S3_*`), тогда они не зависят от сервера.

Восстановление:

```bash
gunzip -c infra/backups/daily/maison-ГГГГММДД.sql.gz | dc exec -T postgres psql -U maison maison
```

## Мониторинг

- `SENTRY_DSN` — ошибки бэкенда приходят в Sentry (sentry.io, бесплатный тариф).
- `GET /api/v1/health` — состояние базы и кэша (для внешнего мониторинга, например UptimeRobot).

## Проверено локально (2026-10-11)

Полный стек поднимался с `DOMAIN=localhost`: страницы через HTTPS, редирект http → https,
HSTS, вход в админку, обработка фото воркером и абсолютные ссылки на них при SSR,
курсы валют, поиск, бэкап.
