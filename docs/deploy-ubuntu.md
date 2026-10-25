# Запуск на сервере Ubuntu — javablueprints.mooo.com

Инструкция для Ubuntu Server 26.04 LTS. Для 24.04 LTS шаги такие же. Версии «26.06» у Ubuntu нет: релизы выходят
в апреле (.04) и октябре (.10).

Итог: сайт открывается по адресу **https://javablueprints.mooo.com** с бесплатным сертификатом, который
обновляется сам.

```
Интернет ──443/80──► Caddy (на хосте: HTTPS, сертификат)
                        └──► 127.0.0.1:8080 ► frontend (nginx: интерфейс + /api) ► backend (FastAPI + JDK 17)
```
Java и Python ставить на сервер не нужно — они внутри Docker-образа.

## Запуск на уже подготовленном сервере

Этот раздел — для сервера, на котором шаги 1–6 ниже уже выполнены:
- Docker и Caddy установлены;
- репозиторий лежит в `/opt/Lampochki_DGTY`;
- в нём есть `.env` с `JB_HTTP_BIND=127.0.0.1:8080`;
- Caddyfile указывает на `127.0.0.1:8080`.

Запуск или перезапуск после `docker compose down`:

```bash
cd /opt/Lampochki_DGTY
git pull                                   # свежий main
cat .env                                   # JB_HTTP_BIND=127.0.0.1:8080
grep JB_HTTP_BIND docker-compose.yml       # "${JB_HTTP_BIND:-80}:80" — иначе git pull не прошёл
docker compose up -d --build               # сборка и запуск (первый раз 3–10 минут)
docker compose ps                          # backend и frontend — running
curl -sI http://127.0.0.1:8080/ | head -1  # HTTP/1.1 200 OK
sudo systemctl status caddy --no-pager | head -3   # active (running)
```

Откройте **https://javablueprints.mooo.com**. Если вместо интерфейса белая страница, обновите её без кеша:
Ctrl+Shift+R (на Mac — Cmd+Shift+R). Браузер мог запомнить пустой ответ 502, который Caddy отдавал, пока
приложение не работало.

Остановить: `docker compose down`. Перезапустить без пересборки: `docker compose restart`. Обновить версию — шаг 7.

**Ключи ИИ.** Если в `backend/.env` лежат ключи Gemini, закройте сайт паролем (раздел 9) или удалите ключи:
код посетителей может их прочитать.

## 0. Что нужно

| | Минимум | Рекомендуется |
|---|---|---|
| CPU / RAM | 2 vCPU / 2 ГБ | 2–4 vCPU / 4 ГБ (сборка фронтенда и javac требуют памяти) |
| Диск | 10 ГБ | 20 ГБ |
| Порты | 22 (SSH), 80 и 443 | |
| Домен | `javablueprints.mooo.com` → IP сервера | |

## 1. Домен

`mooo.com` — домен сервиса FreeDNS (freedns.afraid.org). В его панели (**Subdomains**) у
`javablueprints.mooo.com` должна быть **A-запись** с публичным IPv4 сервера. Если у сервера есть IPv6, можно
добавить и AAAA-запись. Если AAAA-запись есть, но IPv6 на сервере не настроен, удалите её: иначе сертификат
не выпустится.

Проверка (с любого компьютера):
```bash
dig +short javablueprints.mooo.com      # должен вывести IP сервера
```
DNS обновляется от нескольких минут до часа. Не переходите к шагу 6, пока команда не покажет нужный IP.

## 2. Подготовка сервера

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install ca-certificates curl git ufw
```

Swap — нужен, если RAM 2 ГБ и меньше, иначе сборка фронтенда может упасть:
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Файрвол:
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp       # нужен Caddy для выпуска сертификата и редиректа на https
sudo ufw allow 443/tcp
sudo ufw enable
```

## 3. Docker

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

> Если `apt update` пишет, что для вашего выпуска репозитория ещё нет (так бывает в первые недели после выхода
> Ubuntu), удалите файл `/etc/apt/sources.list.d/docker.list` и поставьте Docker из репозитория Ubuntu:
> `sudo apt -y install docker.io docker-compose-v2 docker-buildx`.

Дальше:

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER && newgrp docker     # docker без sudo
docker compose version                              # должна быть v2.x
```

## 4. Код и настройки

```bash
cd /opt && sudo git clone https://github.com/JohnBobbyDick/Lampochki_DGTY.git
sudo chown -R $USER:$USER /opt/Lampochki_DGTY && cd /opt/Lampochki_DGTY
git checkout main
```
Если репозиторий приватный, клонируйте по SSH-ключу (deploy key) или по персональному токену GitHub.

Приложение должно слушать только локальный порт — наружу его выставит Caddy. Это задаётся в корневом `.env`
(лежит рядом с `docker-compose.yml`, в git не попадает, поэтому `git pull` его не трогает):
```bash
echo 'JB_HTTP_BIND=127.0.0.1:8080' > .env
```
Если порт 8080 на сервере занят, укажите другой, например `127.0.0.1:8081`, и тот же порт в Caddyfile (шаг 6).

ИИ-подсказки необязательны: без настроек вместо ИИ отвечает база статических подсказок. Если всё же нужны —
сначала прочитайте раздел 9 «Безопасность», затем:
```bash
cp backend/.env.example backend/.env && nano backend/.env    # LLM_ENABLED=true, GEMINI_API_KEY=…
chmod 600 backend/.env
```

## 5. Запуск приложения

```bash
docker compose up -d --build       # первая сборка занимает 3–10 минут
docker compose ps                  # backend и frontend — running
curl -s http://127.0.0.1:8080/api/ai/status && echo     # ответ JSON — бэкенд жив
```

## 6. HTTPS через Caddy

Caddy сам получит сертификат Let's Encrypt для домена и будет его продлевать. Порт 80 он перенаправит на https.

```bash
sudo apt -y install caddy
sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
javablueprints.mooo.com {
    encode gzip
    reverse_proxy 127.0.0.1:8080
}
EOF
sudo systemctl reload caddy
sudo journalctl -u caddy -n 30 --no-pager     # ищите "certificate obtained successfully"
```

Откройте **https://javablueprints.mooo.com**, затем пример `Warehouse.java` → «Запустить». В консоли внизу
должен появиться вывод программы.

Что уже настроено в репозитории:
- WebSocket консоли Caddy проксирует сам.
- Проверка Origin проходит: страница и API на одном домене, а Caddy передаёт исходный `Host`.
- nginx берёт настоящий IP посетителя из заголовка, который ставит Caddy. Поэтому лимит новых сессий
  (30 за 10 минут) считается для каждого посетителя отдельно, а не один на всех.

Если сертификат не выпускается:
- `dig +short javablueprints.mooo.com` должен показывать IP этого сервера;
- порты 80 и 443 открыты в ufw и в файрволе хостинга (security group / панель провайдера);
- никакой другой сервис не занимает 80 / 443: `sudo ss -ltnp | grep -E ':80 |:443 '`.

## 7. Обновление

```bash
cd /opt/Lampochki_DGTY
git pull
docker compose up -d --build
docker image prune -f              # удалить старые образы
```
Файлы `.env` и `backend/.env` при обновлении не меняются.

После перезагрузки сервера всё поднимается само: у контейнеров `restart: unless-stopped`, Docker и Caddy в
автозапуске.

## 8. Логи и обслуживание

```bash
docker compose logs -f backend        # логи бэкенда (ключи и пароли прокси маскируются)
docker compose logs -f frontend       # логи nginx (в них уже настоящие IP посетителей)
sudo journalctl -u caddy -f           # логи Caddy и сертификатов
docker compose restart backend
docker compose down                   # остановить приложение
```

Проверка демо-сценария прямо на сервере (необязательно):
```bash
python3 results/demo_scenario.py http://127.0.0.1:8080     # должно быть «9 из 9»
```

## 9. Безопасность — прочитайте перед публикацией

Приложение **выполняет код, который присылают посетители**. По умолчанию (`JAVA_SANDBOX_MODE=subprocess`)
программа запускается внутри контейнера бэкенда. Защита такая:
- не root;
- 10 с процессорного времени на запуск (в консоли сессия с ожиданием ввода — до 60 с);
- лимит Java-кучи и общий лимит контейнера 1 ГБ.

Полной изоляции нет. Мы проверили, что такая программа:
- **видит переменные окружения бэкенда**, в том числе `GEMINI_API_KEY` и пароли прокси из `backend/.env`;
- **имеет доступ в интернет.**

Поэтому:
- **Открытый сайт для всех — без ключей ИИ.** Не создавайте `backend/.env` с ключами: всё, кроме ответов LLM,
  работает на статических подсказках.
- **Нужен ИИ** — закройте сайт паролем. Получите хеш пароля командой `caddy hash-password` (она спросит пароль)
  и замените Caddyfile:
  ```bash
  sudo tee /etc/caddy/Caddyfile > /dev/null <<'EOF'
  javablueprints.mooo.com {
      basicauth {
          jury <хеш из caddy hash-password>
      }
      encode gzip
      reverse_proxy 127.0.0.1:8080
  }
  EOF
  sudo systemctl reload caddy
  ```
  Логин — `jury`, пароль — тот, что вы ввели. В Ubuntu ставится Caddy 2.6, поэтому директива пишется
  `basicauth`; в Caddy 2.8+ она называется `basic_auth`.

  Используйте отдельные ключи с лимитом расходов и после демо удалите их.
- Авторизации в самом приложении нет: у каждой вкладки браузера своя сессия, файлы проекта хранятся в браузере
  посетителя.
- Порт бэкенда (8000) наружу не публикуется, а интерфейс слушает только `127.0.0.1`. Не меняйте это.

## 10. Частые проблемы

| Симптом | Причина и решение |
|---|---|
| `Bind for 127.0.0.1:8080 failed: port is already allocated` | Порт занят другим сервисом. Смените порт в `.env` (`JB_HTTP_BIND=127.0.0.1:8081`) и в Caddyfile, затем `docker compose up -d` и `sudo systemctl reload caddy` |
| `Pool overlaps with other one on this address space` | Подсеть `172.30.57.0/24` уже занята. Добавьте в корневой `.env`: `JB_SUBNET=172.31.99.0/24`, `JB_NGINX_IP=172.31.99.10`, `FORWARDED_ALLOW_IPS=172.31.99.10` |
| Сборка падает на `npm run build` (killed / exit 137) | Не хватает памяти — добавьте swap (шаг 2) |
| Белая страница или `502 Bad Gateway`, в логе Caddy `dial tcp 127.0.0.1:8080: connect: connection refused` | Приложение не запущено или слушает другой порт. Проверьте `docker compose ps` и сравните порт в `.env` и Caddyfile. Затем обновите страницу без кеша (Ctrl+Shift+R) |
| `failed to bind host port 0.0.0.0:80/tcp: address already in use` | Порт 80 занят Caddy, а приложение пытается занять его само: на сервере старая версия `docker-compose.yml` или нет `.env`. Выполните `git pull`, `echo 'JB_HTTP_BIND=127.0.0.1:8080' > .env`, затем `docker compose up -d` |
| Код разбирается, но «Запустить» не подключается к консоли | Проверка Origin не совпала (WebSocket закрывается). Откройте сайт именно по `https://javablueprints.mooo.com` или добавьте адрес в `backend/.env`: `ALLOWED_ORIGINS=https://javablueprints.mooo.com` и перезапустите бэкенд |
| «Слишком много новых сессий» | Больше 30 новых вкладок с одного IP за 10 минут — подождите или закройте лишние вкладки |
| ИИ не отвечает | `docker compose exec backend python check_llm.py` проверяет ключи и прокси (ключи в выводе маскируются) |
