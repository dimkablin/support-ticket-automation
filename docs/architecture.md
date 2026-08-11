# Архитектура

## Поток решения

~~~mermaid
flowchart LR
    C["chat / email / web / mobile"] --> A["Адаптеры и валидация"]
    A --> P["Маскирование PII"]
    P --> M["TF-IDF + Logistic Regression"]
    M --> G{"theme in HIGH_RISK_THEMES?"}
    G -->|да| H["human_need без LLM"]
    G -->|нет| T{"confidence >= 0.22?"}
    T -->|нет| H
    T -->|да| F{"разрешённая FAQ-тема?"}
    F -->|да| K["Qdrant: dense + sparse RRF top-3"]
    F -->|нет| K
    K --> L["FakeLLM или LiteLLM"]
    L --> D{"RAG / LLM / audit доступны?"}
    D -->|да, FAQ| X["auto_reply"]
    D -->|да, нужна проверка| V["approve_require"]
    D -->|нет| H
    X --> PG["PostgreSQL audit"]
    V --> PG
    H --> PG
    P --> R["Redis: точные повторы, TTL 15 минут"]
    A -. обезличенный trace .-> LF["Langfuse"]
~~~

Risk gate находится после классификатора и проверяет именно
`classification.theme in HIGH_RISK_THEMES`; сырой текст не сравнивается со
списком тем. Денежные темы: повторное списание, подозрение на мошенничество,
неполученный возврат и спорная операция. Low-confidence всегда означает
`human_need`. Сбой retrieval, LLM или обязательного audit также запрещает
автоматическую отправку.

Redis-ключ — SHA-256 от обезличенного текста, версии классификатора, KB и
провайдера. Кэш ускоряет точный повтор, но не отменяет новую запись решения в
audit. Langfuse используется для trace этапов, PostgreSQL — для аудируемого
решения; это разные обязанности.

## Синхронный demo path

Streamlit синхронно вызывает pipeline, чтобы один сценарий можно было проверить
в интерфейсе. На горячем пути до 500 мс находятся только адаптация,
PII-маскирование, классификация и policy. Retrieval и генерация допустимо
выполнять дольше; в целевой интеграции клиент сразу получает подтверждение, а
ответ формируется асинхронно.

## Асинхронный burst path

~~~mermaid
flowchart LR
    P["Channel adapter / publisher"] --> I["tickets.incoming"]
    I --> W["Classifier + policy worker"]
    W -->|human_need| H["tickets.human"]
    W -->|auto_reply / approve_require| G["tickets.generate"]
    G --> R["Qdrant + provider + audit"]
    R -->|approve / fallback| H
    I -. retry, delivery limit 3 .-> D["tickets.dlq"]
    G -. retry, delivery limit 3 .-> D
    W -. Prometheus .-> PM["worker /metrics"]
~~~

Отдельный RabbitMQ-контур реально входит в PoC. Quorum queues ограничены 50
тысячами сообщений и используют `reject-publish`, persistent messages,
publisher confirms, prefetch, три попытки доставки и DLQ. Параллелизм LLM
ограничен `LLM_CONCURRENCY`. Это демонстрирует backpressure и безопасный маршрут
при пике, но не является production-кластером: broker и worker локальные, нет
HA, autoscaling и сквозной idempotency store.

## Инцидентные всплески

Пик 20 тысяч тикетов за 10 минут — в среднем около 33 тикетов/с, но сообщения
могут прийти заметно неравномернее. RabbitMQ принимает этот burst и отделяет
приём от генерации, а Redis не повторяет обработку идентичного обезличенного
запроса в течение TTL. Полноценная группировка похожих тикетов в один incident
ID в PoC не реализована.

Локальный burst-тест подтвердил 20 000 из 20 000 публикаций без reject со
скоростью 227 сообщений/с. Это проверяет приём и backpressure, но не доказывает
production HA или способность внешней LLM обработать backlog в пределах SLA.

## Хранилища и интеграции

- Qdrant хранит 12 документов KB с dense RuBERT Tiny 2 и sparse lexical
  векторами; benchmark-тикеты туда не попадают.
- RuBERT Tiny 2 работает локально в Hugging Face TEI на CPU; Qdrant объединяет
  dense и sparse выдачи через RRF.
- PostgreSQL хранит обезличенный audit trail: вход, тему, confidence, действие,
  версии модели/KB и причину fallback.
- Langfuse хранит обезличенный trace этапов и стоимость LLM.
- Redis хранит краткоживущий результат точного повтора.
- RabbitMQ хранит входные, генерационные, операторские и dead-letter сообщения.
- FakeLLM — детерминированный baseline; LiteLLM — единственный путь к реальной
  OpenAI-compatible модели.

Настоящие SDK chat/email/web/mobile и рабочее место оператора заменены локальными
адаптерами, publisher-скриптом и очередью `tickets.human`. Это явная граница PoC.
