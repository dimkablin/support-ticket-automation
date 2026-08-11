# Автоматизация тикетов поддержки

Минимальный AI/ML PoC для 200 тысяч русскоязычных тикетов в день. Он принимает
четыре формата обращений, маскирует PII, классифицирует тему, применяет
детерминированный денежный risk gate, получает контекст из LightRAG и формирует
ответ через FakeLLM или LiteLLM. Повторяющиеся запросы кэшируются в настоящем
Redis; решения пишутся в PostgreSQL и трассируются в Langfuse.

Реализован один happy path — уверенный FAQ может быть закрыт автоматически — и
один risky/fallback path: денежная тема, низкая уверенность, сбой RAG/LLM или
аудита всегда отправляют тикет оператору.

## Быстрый запуск

Требования: Python 3.12+, uv, Docker Desktop и NVIDIA GPU для существующего
Ollama Compose.

~~~powershell
Copy-Item .env.example .env
# Замените все CHANGE_ME и нулевой LANGFUSE_ENCRYPTION_KEY.

uv sync --extra dev
uv run python scripts/prepare_dataset.py
uv run python scripts/train_classifier.py

docker compose -f ..\..\docker-compose.ollama.yaml up -d
docker exec ollama ollama pull qwen3:8b
docker exec ollama ollama pull bge-m3

docker compose --env-file .env -f docker-compose.langfuse.yml up -d
docker compose --env-file .env -f docker-compose.lightrag.yml up -d
uv run python scripts/index_kb.py

docker compose --env-file .env -f docker-compose.yml up --build -d
~~~

Интерфейс: <http://localhost:8501>, Langfuse: <http://localhost:3000>,
LightRAG: <http://localhost:9621>.

Порядок важен: query_dataset оценивает уже построенную KB, но сам никогда не
загружается в LightRAG. Индексация LightRAG асинхронна — перед live benchmark
дождитесь статуса processed для 12 документов в Web UI.

## Проверка

~~~powershell
uv run pytest -q
uv run ruff check .
uv run python -m benchmark
uv run python -m benchmark --live --provider fake
~~~

Первый benchmark проверяет классификатор, risk gate и задержку без внешних
сервисов. Второй делает 60 запросов к настоящему LightRAG и считает Hit@1,
Recall@3, MRR, покрытие обязательных и появление запрещённых фактов. Ни одна
метрика не использует LLM-as-a-judge. Результаты пишутся в
benchmark/results/.

Текущий воспроизводимый classifier-only результат на test: accuracy 0.75,
macro-F1 0.745, Top-3 accuracy 0.933, high-risk recall 1.0, auto-close
precision 1.0, p95 горячего пути около 1.4 мс. Live-RAG метрики требуют
запущенных Ollama и LightRAG и поэтому не подменены фиктивными числами.

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
- kb/*.md — 12 русских документов для LightRAG;
- src/support_automation/ — адаптеры, классификатор, policy, интеграции и pipeline;
- streamlit_app.py — выбор канала, устройства, готового примера и провайдера;
- три независимых Compose: приложение, LightRAG и Langfuse.

Архитектура и ограничения описаны в [docs/architecture.md](docs/architecture.md),
ML — в [docs/ml.md](docs/ml.md), эксплуатация — в
[docs/risks-and-ops.md](docs/risks-and-ops.md).

