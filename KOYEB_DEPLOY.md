# Koyeb'da Deployment: Presenton + Telegram Bot

## Arxitektura

```
[Telegram User]
      │
      ▼
[Bot (Worker) — Koyeb Service 2]
      │  http://presenton.<app>.internal
      ▼
[Presenton (Web) — Koyeb Service 1]
      │  https://api.deepseek.com
      │  https://api.pexels.com
      ▼
[DeepSeek AI + Pexels Images]
```

---

## Qadam 1 — Koyeb'da App yarating

Koyeb dashboard → **Create App** → App nomini bering, masalan: `myapp`

---

## Qadam 2 — Presenton servisini yarating

### 2.1 Service yaratish
**Create Service** → **Docker Image** ni tanlang

**Image:** `ghcr.io/presenton/presenton:latest`

### 2.2 Port
| Port | Protocol | Route  | Public |
|------|----------|--------|--------|
| 80   | HTTP     | /      | ✅ ON  |

> ⚠️ Port 80 ni ochiq qiling — bot internal URL orqali ulanadi

### 2.3 Environment Variables
Koyeb dashboard'da **Environment Variables** bo'limiga quyidagilarni kiriting:

| Variable | Value |
|---|---|
| `LLM` | `openai` |
| `OPENAI_API_KEY` | DeepSeek API kalitingiz (`sk-...`) |
| `OPENAI_BASE_URL` | `https://api.deepseek.com` |
| `OPENAI_MODEL` | `deepseek-chat` |
| `IMAGE_PROVIDER` | `pexels` |
| `PEXELS_API_KEY` | Pexels API kalitingiz |
| `CAN_CHANGE_KEYS` | `false` |

### 2.4 Service nomi
Service nomini **`presenton`** deb belgilang (bu muhim — URL shu nomdan hosil bo'ladi)

### 2.5 Resources
- **Instance:** Standard (kamida 512MB RAM kerak)
- **Region:** Eng yaqin (Frankfurt yoki Singapore)
- **Replicas:** 1

**Deploy** bosing va tayyor bo'lishini kuting (~2-5 daqiqa).

---

## Qadam 3 — Bot servisini yarating

### 3.1 Service yaratish
**Create Service** → **GitHub** yoki **Docker Image** ni tanlang

Agar GitHub: `bot/` papkasini repo'ga yuklang, Dockerfile tanlanadi.

### 3.2 Service turi
Service Type: **Worker** (HTTP emas!)

### 3.3 Environment Variables

| Variable | Value |
|---|---|
| `BOT_TOKEN` | BotFather'dan olgan tokeningiz |
| `PRESENTON_BASE_URL` | `http://presenton.myapp.internal` ⬅️ |
| `PRESENTON_API_KEY` | *(bo'sh qoldiring)* |
| `LOG_LEVEL` | `INFO` |
| `DEFAULT_SLIDES` | `12` |
| `DEFAULT_TONE` | `professional` |
| `DEFAULT_VERBOSITY` | `text-heavy` |
| `DEFAULT_LANGUAGE` | `English` |
| `POLL_INTERVAL_SECONDS` | `10` |
| `MAX_POLL_ATTEMPTS` | `60` |
| `REQUEST_TIMEOUT_SECONDS` | `300` |
| `DROP_PENDING_UPDATES_ON_STARTUP` | `true` |

> ⚠️ **MUHIM:** `PRESENTON_BASE_URL` dagi `myapp` o'rniga o'zingizning **App nomingizni** kiriting!
>
> Format: `http://<service-nomi>.<app-nomi>.internal`
>
> Masalan, App nomi `myapp`, Presenton service nomi `presenton` bo'lsa:
> ```
> http://presenton.myapp.internal
> ```

### 3.4 Service nomi
**`bot`** deb belgilang

### 3.5 Resources
- **Instance:** Nano yoki Micro (bot uchun kam resurs yetadi)
- **Replicas:** `1` ← **Majburiy! 2 bo'lsa 409 Conflict xatosi!**

**Deploy** bosing.

---

## Qadam 4 — Tekshirish

1. Koyeb dashboard'da ikki servis ham **Running** bo'lishi kerak
2. Telegram'da botga `/start` yuboring
3. `/new` → mavzu yuboring

---

## Free Plan Haqida

> ⚠️ Koyeb **free plan**'da internal mesh (`*.internal`) ishlamaydi!

Free plan bo'lsa, bot uchun:
```
PRESENTON_BASE_URL=https://presenton-xxxx.koyeb.app
```
Presenton servisining **public URL**'ini ishlating (Koyeb dashboard'da Settings → Domains da ko'rinadi).

---

## Muammolarni hal qilish

### Bot `ConnectError` bersa
`PRESENTON_BASE_URL` noto'g'ri. Tekshiring:
- App nomi to'g'rimi? (`myapp` o'rnida nima yozdingiz?)
- Service nomi `presenton` mi?
- Free plan bo'lsa public URL ishlating

### Presenton sekin ishga tushadigan bo'lsa
DeepSeek model yuklanmoqda. Birinchi marta 1-2 daqiqa kutish normal.

### `409 Conflict` xatosi
Bot Worker servisining **Replicas = 1** ekanligini tekshiring.

### Deck yaratish uzoq vaqt olsa
`MAX_POLL_ATTEMPTS` va `POLL_INTERVAL_SECONDS` ni oshiring:
```
MAX_POLL_ATTEMPTS=90
POLL_INTERVAL_SECONDS=10
```
(Jami 15 daqiqa)

---

## Lokal sinash (Docker Compose)

```bash
# 1. .env faylini tayyorlang
cp .env.example .env
# .env ni to'ldiring: BOT_TOKEN, DEEPSEEK_API_KEY, PEXELS_API_KEY

# 2. Ishga tushiring
docker compose up --build

# 3. Loglarni kuzating
docker compose logs -f bot
docker compose logs -f presenton
```
