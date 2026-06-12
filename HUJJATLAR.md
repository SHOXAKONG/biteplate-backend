# BitePlate — Loyiha Hujjatlari

> Aqlli Restoran Boshqaruv Tizimining qisqacha texnik bayoni: nima qildik, qanday pattern'lardan foydalandik, arxitektura va optimizatsiyalar.

---

## 1. Loyiha haqida

**BitePlate** — restoran tarmog'i uchun yozilgan zamonaviy boshqaruv tizimi. Qog'oz va eski jarayonlarni almashtiradi: stol holatini, buyurtmalarni, oshxonani, hisob-kitobni va bron qilishni bitta interfeysda boshqaradi.

### Texnologiyalar

| Qism | Tanlov | Nima uchun |
| --- | --- | --- |
| Backend | **Python 3.12 + FastAPI** | Async qo'llab-quvvatlash, tez, Pydantic validatsiya |
| Frontend | **Vue 3 + Vite + TypeScript** | Kichik bundle, tezkor hot reload |
| Auth | **Keycloak 24 (OIDC)** | Sanoat standartidagi identifikatsiya provayder |
| Ma'lumotlar bazasi | **Postgres 16 + SQLAlchemy 2 async** | ACID, JSONB, asyncpg tezligi |
| Migratsiyalar | **Alembic** | Schema versiyalash |
| Fon vazifalar | **Celery + RabbitMQ + Redis** | SMS eslatmalar, rejalashtirilgan vazifalar |
| Konteynerlar | **Docker + k3s** | Dev va prod bir xil muhit |
| Ingress + TLS | **Traefik + cert-manager + Let's Encrypt** | Avtomatik yangilanadigan sertifikatlar |
| Registry | **GHCR** | GitHub'ga integratsiyalashgan |
| CI/CD | **GitHub Actions** (har repo uchun alohida) | Mustaqil pipelinelar |
| SMS | **Eskiz.uz** | Twilio O'zbekiston raqamlarini qabul qilmadi |

---

## 2. 11 ta Design Pattern

Har bir pattern `backend/app/services/` yoki `backend/app/core/` da yashaydi.

| # | Pattern | Fayl | Nima qiladi |
| --- | --- | --- | --- |
| 1 | **Factory Method** | `services/menu.py` | Menyu turini (Starter, Main, Combo) nomi bo'yicha yaratadi |
| 2 | **Composite** | `services/menu.py` | ComboMeal alohida MenuItem'lar to'plamini yagona narx kabi ko'rsatadi |
| 3 | **Decorator** | `services/menu.py` | Chegirma, soliq, qo'shimcha tovar dinamik qo'shiladi |
| 4 | **State** | `services/tables.py` | Stol holati: Free → Reserved → Occupied → AwaitingBill → Cleared |
| 5 | **Command** | `services/kitchen.py` | Oshxona buyruqlari (Prepare, Cancel) — undo qo'llab-quvvatlanadi |
| 6 | **Strategy** | `services/pricing.py` | 5 ta narx algoritmi (Standart, Happy Hour, Loyal, Korporativ, Festival) |
| 7 | **Facade** | `services/billing.py` | Hisob-kitob (soliq, chayanak, bo'linish) bitta interfeys orqali |
| 8 | **Singleton** | `services/history.py` | OrderHistoryLog — bitta global jurnal |
| 9 | **Iterator** | `services/history.py` | Sana/stol/eng ko'p sotilgan mahsulot bo'yicha iteratorlar |
| 10 | **Observer** | `services/notifications.py` | Buyurtma holati o'zgarganda WaiterNotifier, Kitchen, SMS xabar oladi |
| 11 | **Chain of Responsibility** | `core/middleware.py` | RequestID → Timing → Logging → Errors → RateLimit zanjiri |

### Qisqacha tushuntirish

**Factory + Composite + Decorator** — menyu tizimini moslashuvchan qiladi. Yangi kategoriya qo'shsangiz, eski kodga tegmaysiz.

**State** — stol uchun `if status == "free"` shartlar o'rniga har bir holat o'z obyekti bo'ladi. Kod ancha toza.

**Command + undo** — oshpaz xato qilsa, oxirgi harakatni qaytarib oladi. Har buyruq oldingi holatni o'zida saqlaydi.

**Strategy** — Bill klassi narx algoritmini qaysi ekanini bilmasdan ishlatadi. Yangi chegirma qo'shish bitta sinf qo'shish bilan tugaydi.

**Singleton + Iterator** — barcha buyurtmalar yagona jurnalga yoziladi va keyin filtrlash uchun iteratorlar orqali o'qiladi.

**Observer** — yangi xabardor qo'shish (WhatsApp, Telegram) bitta sinf qo'shish bilan ishlaydi — Order klassiga tegilmaydi.

**Chain of Responsibility** — har HTTP so'rov 5 ta middleware'dan o'tadi. Yangi tekshiruv qo'shish — zanjirga yangi halqa qo'shish.

---

## 3. Arxitektura

### So'rov yo'li (brauzerdan javobgacha)

```
Brauzer
   │ HTTPS
   ▼
Traefik Ingress (TLS, Host: api.62.113.58.138.nip.io)
   │
   ▼
biteplate-api Pod (uvicorn + FastAPI)
   │
   ├─ Middleware zanjiri (RequestID → Timing → Log → Error → RateLimit)
   ├─ JWT tekshiruvi (Keycloak JWKS)
   ├─ Rol tekshiruvi (require_role("waiter"))
   ├─ Pydantic validatsiya
   ├─ Service qatlami
   ├─ Repository qatlami (async SQLAlchemy)
   │
   ▼
Postgres 16 (alohida server)
```

### Login flow

1. Brauzer `POST /api/v1/auth/login` yuboradi
2. Backend Keycloak'ga `grant_type=password` so'rov yuboradi (`biteplate-frontend` klient)
3. Keycloak `{access_token, refresh_token}` qaytaradi
4. Backend JWT'ni qayta tekshiradi (imzo + issuer + audience)
5. Brauzer tokenni Pinia store + localStorage'ga saqlaydi
6. Keyingi so'rovlarda `Authorization: Bearer <token>` header
7. Token muddati tugasa, refresh_token bilan yangi olinadi

### K8s topologiyasi

```
VPS 62.113.58.138 (Ubuntu 24 + k3s)
├─ namespace: biteplate
│   ├─ biteplate-api    (FastAPI, 1 replica)
│   ├─ biteplate-worker (Celery, 1 replica)
│   ├─ biteplate-beat   (Celery scheduler)
│   ├─ rabbitmq         (xabar brokeri)
│   └─ redis            (cache + Celery natijasi)
├─ namespace: biteplate-frontend
│   └─ biteplate-frontend (nginx + SPA, 2 replicas)
├─ namespace: biteplate-auth
│   └─ keycloak         (Keycloak 24)
└─ namespace: cert-manager
    └─ Let's Encrypt avtomatik sertifikatlar

VPS 95.216.199.114 (alohida) — Postgres 16
```

### Uchta domen, bitta IP

`nip.io` — bepul wildcard DNS. `*.62.113.58.138.nip.io` → `62.113.58.138`.

| URL | → Service |
| --- | --- |
| `https://app.62.113.58.138.nip.io` | frontend |
| `https://api.62.113.58.138.nip.io` | backend |
| `https://auth.62.113.58.138.nip.io` | keycloak |

Traefik `Host:` headerini o'qib, to'g'ri Service'ga yo'naltiradi.

### CI/CD (har repo uchun)

```
main'ga push
   ↓
Lint + Test (ruff, pytest, vue-tsc)
   ↓
Build & Push (docker → ghcr.io)
   ↓
Deploy (kubectl apply + set image + rollout)
```

Uchta alohida repo (`biteplate-backend`, `biteplate-frontend`, `biteplate-auth`) — har biri mustaqil deploy bo'ladi.

---

## 4. Optimizatsiyalar

### Backend
- **Async SQLAlchemy + asyncpg** — bir vaqtning o'zida ko'proq so'rovlarni bajaradi
- **Pydantic v2** — Rust'da yozilgan validatsiya, 10-20x tezroq
- **JWT JWKS cache** — Keycloak kalitlari 1 soatga keshlanadi, har so'rovda tarmoqqa bormaymiz
- **Multi-issuer JWT** — ikki turdagi token issuer'ni qabul qiladi
- **Connection pool + pre-ping** — Postgres restart bo'lsa ham so'rovlar tushmaydi
- **Chunked seed** — 10k yozuvni 200tadan partiyalarda kiritadi

### Frontend
- **Vite production build** — main JS ~125 KB gzipped (Nuxt'da ~400 KB edi)
- **Lazy-loaded routes** — har dashboard alohida chunk
- **Tailwind purge** — production CSS ~30 KB
- **Lazy images** — ko'rinmagan rasmlar yuklanmaydi
- **Refresh-retry guard** — cheksiz refresh loop'dan himoyalaydi

### Infrastruktura
- **nginx + static SPA** — frontend image ~30 MB (Node SSR ~250 MB bo'lardi)
- **k3s** — vanilla k8s o'rniga, kichik VPS uchun
- **Tashqi Postgres** — disk ajratish, oson backup
- **`imagePullPolicy: Always` + git-SHA tag** — har deploy yangi image tortadi
- **`startupProbe`** Keycloak uchun — 100s startup'ga bardosh
- **`maxSurge: 1, maxUnavailable: 0`** — zero-downtime rolling update
- **Public GHCR** — pull secret kerak emas
- **cert-manager + HTTP-01** — sertifikatlar avtomatik yangilanadi

### Build
- **Multi-stage Docker** — build artifaktlari prod image'iga tushmaydi
- **uv (pip o'rniga)** — Python dep o'rnatish ~10x tez
- **Layer ordering** (`COPY pyproject.toml` keyin `COPY .`) — dep keshi qayta ishlatiladi
- **Debug-on-failure CI step** — rollout muvaffaqiyatsiz bo'lsa, pod holati va event'lar avtomatik chiqadi

---

## 5. Qo'shimcha qo'shilgan funksiyalar (brifdan tashqari)

| Funksiya | Nima qo'shadi |
| --- | --- |
| To'liq HTTP REST API | CLI demo emas — har operatsiya `/api/v1/...` endpoint |
| 6 ta rol uchun alohida dashboard | Admin, Manager, Waiter, Chef, Cashier, Customer |
| Haqiqiy OIDC auth | Keycloak orqali JWT — hardkodlangan rol enum emas |
| 11-pattern: Chain of Responsibility | Middleware stack — GoF 10-likka kirmaydigan pattern |
| Production deploy | https://app.62.113.58.138.nip.io da haqiqiy TLS bilan |
| Mustaqil CI/CD | Har repo o'z ritmida ishlaydi |
| Fon vazifalar | Celery worker + beat, reservation reminderlar |
| Haqiqiy SMS | Eskiz.uz integratsiyasi |
| 10 000 yozuvlik seed | Faker bilan haqiqatga yaqin demo data |
| 30+ kategoriya uchun food rasmlari | Har kategoriya o'zining Unsplash heroi |
| Per-class UML diagrammalar | Asosiy diagrammani 6 ta alohida diagrammaga bo'ldik |

---

## 6. Xavfsizlik

- Hech qaysi parol/maxfiy ma'lumot kodda yo'q — barchasi k8s `Secret` orqali
- Pydantic input validatsiya har endpoint'da
- JWT imzosi har so'rovda tekshiriladi (JWKS keshlangan)
- Rol asosida ruxsat (`require_role("waiter")`)
- ErrorTranslatingMiddleware — ichki xatolarni xavfsiz JSON'ga aylantiradi (stack trace chiqarmaydi)
- TLS barcha public hostnamelarda (Let's Encrypt)
- CORS aniq belgilangan — `*` emas
- Audit log (OrderHistoryLog) — kim nima qildi yozib boriladi
- Rate limit (Redis token bucket) — login brute-force'dan himoya

---

## 7. Cheklovlar va kelgusi ish

### Atayin soddalashtirilgan

| Qaror | Cheklov | Nima uchun |
| --- | --- | --- |
| Bir nodali k3s | HA yo'q | Loyiha prototip |
| Local Keycloak'da H2 | Restartda ma'lumot yo'qoladi | Realm import qayta yuklaydi |
| In-process Singleton | Har worker o'z nusxasi | Asl log Postgres'da |
| `nip.io` DNS | Haqiqiy domen emas | Demo uchun yetarli |
| Metrics stack yo'q | Live dashboard yo'q | `kubectl logs` + `k9s` yetarli |

### 50 ta restoranga kengaytirsak

1. Singleton o'rniga service container scope
2. Keycloak'ni tashqi Postgres'ga ko'chirish
3. Redis Cluster (bitta Redis bottleneck bo'ladi)
4. Kafka — KitchenQueue uchun persistent navbat
5. Abstract Factory — har filial uchun alohida menyu
6. HPA + multi-node k8s
7. Haqiqiy domen + wildcard TLS
8. Sealed Secrets yoki Vault
9. Prometheus + Grafana + Loki
10. Har filial uchun alohida Keycloak realm

---

## 8. Fayllar xaritasi

```
backend/
├── app/
│   ├── core/middleware.py       ← Chain of Responsibility (11)
│   ├── core/security.py         ← JWT multi-issuer
│   ├── services/menu.py         ← Factory (1), Composite (2), Decorator (3)
│   ├── services/tables.py       ← State (4)
│   ├── services/kitchen.py      ← Command (5)
│   ├── services/pricing.py      ← Strategy (6)
│   ├── services/billing.py      ← Facade (7)
│   ├── services/history.py      ← Singleton (8), Iterator (9)
│   └── services/notifications.py ← Observer (10)
├── alembic/                     ← migratsiyalar
├── scripts/seed.py              ← 10k Faker yozuv
├── k8s/                         ← Kubernetes manifestlar
├── Dockerfile                   ← multi-stage
├── ARCHITECTURE.md              ← qisqa arxitektura
└── HUJJATLAR.md                 ← shu fayl
```

---

*BitePlate — 11 ta design pattern, async Python, container-ga moslashtirilgan deploy. Iyun 2026.*
