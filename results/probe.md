# Проба параметров — 24.10.2026 03:21

- GPT: `https://aiprimetech.io/v1` — OpenAI Chat Completions (`/chat/completions`, лимит через `max_tokens`)

## Модели, доступные ключам (GET /v1/models)

- `gpt-5.3-codex-spark` (openai)
- `gpt-5.5` (openai)
- `gpt-5.6` (openai)
- `gpt-5.6-luna` (openai)
- `gpt-5.6-sol` (openai)
- `gpt-5.6-terra` (openai)
- `gpt-6` (openai)
- `gpt-6-astra` (openai)
- `gpt-6-luna` (openai)
- `gpt-6-sol` (openai)
- `gpt-6.1-sol` (openai)
- `gpt-image-2` (openai)
- `gpt-image-2.5-flare` (openai)
- `gpt-image-2.5-sunburst` (openai)

## Результаты

| Модель | Проверка | Итог | stop_reason | Токены in/out | Время, с | Ответ API |
|---|---|---|---|---|---|---|
| gpt-6-astra | базовый запрос | ✅ принят | end_turn | 22/9 | 2.35 | Голубое. |
| gpt-6-astra | temperature=0.2 | ✅ принят | end_turn | 22/9 | 2.96 | Голубое. |
| gpt-6-astra | temperature=1.0 | ✅ принят | end_turn | 22/9 | 1.68 | Голубое. |
| gpt-6-astra | effort=low | ✅ принят | end_turn | 22/8 | 2.14 | Голубое |
| gpt-6-astra | effort=high | ✅ принят | end_turn | 22/9 | 1.73 | Голубое. |
| gpt-6-astra | max_tokens=3 | ✅ принят | end_turn | 22/9 | 2.1 | Голубое. |
| gpt-6-luna | базовый запрос | ✅ принят | end_turn | 22/8 | 1.26 | Голубое |
| gpt-6-luna | temperature=0.2 | ✅ принят | end_turn | 22/8 | 1.35 | Голубого |
| gpt-6-luna | temperature=1.0 | ✅ принят | end_turn | 22/8 | 1.37 | Голубое |
| gpt-6-luna | effort=low | ✅ принят | end_turn | 22/8 | 1.59 | Голубого |
| gpt-6-luna | effort=high | ✅ принят | end_turn | 22/8 | 1.28 | Голубого |
| gpt-6-luna | max_tokens=3 | ✅ принят | end_turn | 22/8 | 2.22 | Голубого |
| gpt-6 | базовый запрос | ✅ принят | end_turn | 22/9 | 1.85 | Голубое. |
| gpt-6 | temperature=0.2 | ✅ принят | end_turn | 22/8 | 1.64 | Голубое |
| gpt-6 | temperature=1.0 | ✅ принят | end_turn | 22/9 | 2.01 | Голубое. |
| gpt-6 | effort=low | ✅ принят | end_turn | 22/8 | 3.24 | Голубое |
| gpt-6 | effort=high | ✅ принят | end_turn | 22/9 | 2.11 | Голубое. |
| gpt-6 | max_tokens=3 | ✅ принят | end_turn | 22/9 | 1.81 | Голубое. |

Расшифровка: ✅ — модель приняла параметр; ❌ bad_request 400 — параметр отклонён.
