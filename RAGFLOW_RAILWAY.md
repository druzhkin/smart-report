# RAGFlow on Railway

Одним Railway service весь RAGFlow не поднимется нормально.

Рабочий вариант, максимально близкий к "запустил один раз и всё само собралось":

1. Создать отдельный Railway project под RAGFlow.
2. Импортировать в него [docker-compose.ragflow.yml](C:\Users\rodina-adm\Documents\dev\smart-report\docker-compose.ragflow.yml).
3. Railway развернёт весь стек как набор сервисов:
   - `ragflow`
   - `ragflow-mysql`
   - `ragflow-minio`
   - `ragflow-redis`
   - `ragflow-es`

## Переменные для проекта RAGFlow

```env
MYSQL_PASSWORD=infini_rag_flow
MINIO_USER=rag_flow
MINIO_PASSWORD=infini_rag_flow
RAGFLOW_REDIS_PASSWORD=infini_rag_flow
ELASTIC_PASSWORD=infini_rag_flow
```

## Что потом вставить в smart-report

После запуска RAGFlow возьми его internal/public URL и пропиши в `smart-report`:

```env
RAGFLOW_API_KEY=...
RAGFLOW_BASE_URL=http://<ragflow-service>.railway.internal:9380
RAGFLOW_REPORTS_DATASET_ID=...
RAGFLOW_FACTS_DATASET_ID=...
```

## Важно

Если Railway не импортирует compose как проект целиком, то это уже ограничение Railway, а не репозитория. В таком случае сервисы придётся создать по одному, но compose-файл выше уже даёт точную схему стека.
