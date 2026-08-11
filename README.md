# Автоматизация тикетов поддержки

Минимальный AI/ML PoC для 200 тысяч русскоязычных тикетов в день. Он принимает
четыре формата обращений, маскирует PII, классифицирует тему, применяет
детерминированный денежный risk gate, получает контекст hybrid-поиском Qdrant + BGE-M3 и формирует
ответ через FakeLLM или LiteLLM. Повторяющиеся запросы кэшируются в настоящем
Redis; решения пишутся в PostgreSQL и трассируются в Langfuse.

Реализован один happy path — уверенный FAQ может быть закрыт автоматически — и
один risky/fallback path: денежная тема, низкая уверенность, сбой RAG/LLM или
аудита всегда отправляют тикет оператору.

## Быстрый запуск

Требования: Python 3.12+, uv, Docker Desktop, NVIDIA Container Toolkit и GPU.
На этой машине Compose настроен для RTX 5070 Ti.

~~~powershell
Copy-Item .env.example .env
# Замените все CHANGE_ME и нулевой LANGFUSE_ENCRYPTION_KEY.

uv sync --extra dev
uv run python scripts/prepare_dataset.py
uv run python scripts/train_classifier.py

# Укажите LITELLM_* в .env.
docker compose --env-file .env -f docker-compose.bge-m3.yml up -d

docker compose --env-file .env -f docker-compose.langfuse.yml up -d
docker compose --env-file .env -f docker-compose.qdrant.yml up -d
uv run python scripts/index_kb.py

docker compose --env-file .env -f docker-compose.yml up --build -d
~~~

Первый запуск BGE-M3 скачивает веса в Docker volume. После готовности endpoint
можно проверить отдельно от Qdrant:

~~~powershell
$body = @{ model = "BAAI/bge-m3"; input = @("проверка embeddings") } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri http://localhost:8081/v1/embeddings -ContentType application/json -Body $body
$result.data[0].embedding.Count  # ожидается 1024
~~~

Интерфейс: <http://localhost:8501>, Langfuse: <http://localhost:3000>,
Qdrant Dashboard: <http://localhost:6333/dashboard>.

Порядок важен: query_dataset оценивает уже построенную KB, но сам никогда не
загружается в Qdrant. `scripts/index_kb.py` синхронно индексирует 12 документов:
dense-векторы BGE-M3 и sparse lexical-векторы для hybrid RRF.

## Проверка

~~~powershell
uv run pytest -q
uv run ruff check .
uv run python -m benchmark
uv run python -m benchmark --live --provider fake
~~~

Первый benchmark проверяет классификатор, risk gate и задержку без внешних
сервисов. Второй делает 60 запросов к настоящим Qdrant и BGE-M3 и считает Hit@1,
Recall@3, MRR, покрытие обязательных и появление запрещённых фактов. Ни одна
метрика не использует LLM-as-a-judge. Результаты пишутся в
benchmark/results/.

Текущий воспроизводимый classifier-only результат на test: accuracy 0.75,
macro-F1 0.745, Top-3 accuracy 0.933, high-risk recall 1.0, auto-close
precision 1.0, p95 горячего пути около 1.4 мс. Live-RAG метрики требуют
запущенных BGE-M3, Qdrant и выбранного провайдера ответа и поэтому не подменены фиктивными числами.

## Экономика

Базовая стоимость: 200 000 × 150 ₽ = 30 млн ₽/день. Типовые обращения —
40%, то есть потолок автоматизируемого потока равен 80 тысячам тикетов и
12 млн ₽ операторской ёмкости в день.

| Сценарий | Автозакрытие | Избежано ручных тикетов | Валовая ёмкость/день |
|---|---:|---:|---:|
| Теневой запуск | 0% | 0 | 0 ₽ |
| Консервативный пилот | 10% | 20 000 | 3,0 млн ₽ |
| Базовый | 25% | 50 000 | 7,5 млн ₽ |
| Верхняя граница типовых | 40% | 80 000 | 12,0 млн ₽ |

При допущении 0,20 ₽ за LLM-инференс базовый сценарий стоит около 10 тысяч
₽/день. Рост reopen rate на 1 п.п. среди 50 тысяч автозакрытий возвращает 500
тикетов, или 75 тысяч ₽/день. Поэтому North Star — число тикетов, закрытых без
оператора при неизменном CSAT, а не количество вызовов модели. Это оценка
высвобождённой ёмкости; она становится денежной экономией только после изменения
штата, аутсорсингового контракта или обработки роста без найма.

## Что внутри

- data/query_dataset.jsonl — 300 тикетов, 12 тем, ответы и ожидаемые действия;
- kb/*.md — 12 русских документов для hybrid-поиска Qdrant;
- src/support_automation/ — адаптеры, классификатор, policy, интеграции и pipeline;
- streamlit_app.py — выбор канала, устройства, готового примера и провайдера;
- четыре независимых Compose: приложение, BGE-M3, Qdrant и Langfuse.

Архитектура и ограничения описаны в [docs/architecture.md](docs/architecture.md),
ML — в [docs/ml.md](docs/ml.md), эксплуатация — в
[docs/risks-and-ops.md](docs/risks-and-ops.md).
