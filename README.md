# users-service

Навчальний проєкт з курсу «Методи та технології забезпечення CI/CD» (лабораторні 1, 2, 4, 5; лаба 3 — у `lab3-etcd/`).
Один сервіс, на якому послідовно будуються всі роботи.

## Що це

REST-сервіс керування користувачами (CRUD) + Angular-клієнт + PostgreSQL + міграції + Helm chart +
власний Kubernetes-контролер резервного копіювання БД.

| Компонент | Технології | Каталог |
|---|---|---|
| Backend API | **Python 3.12, FastAPI**, SQLAlchemy 2 (code-first), шари domain / application / infrastructure / interface | `api/` |
| Міграції (консольний застосунок / K8s Job) | Alembic | `migrations/` |
| Frontend | **Angular 19** + nginx | `web/` |
| Helm chart | Deployment, StatefulSet, StorageClass, PVC, Job, Ingress, Secret, ConfigMap | `k8s/webapp/` |
| Контролер `DatabaseBackup` (лаба 5) | Python, `kubernetes` client | `controller/` |
| Лаба 3 (etcd, кворум) | kind, etcdctl | `lab3-etcd/` |
| CI | GitHub Actions, Azure Pipelines | `.github/workflows/`, `azure-pipelines.yml` |

## API

| Метод | Endpoint | Опис | Коди |
|---|---|---|---|
| GET | `/api/users` | список | 200 |
| GET | `/api/users/{id}` | за id | 200, 404 |
| POST | `/api/users` | створити | 201, 409 (дубль email), 422 |
| PUT | `/api/users/{id}` | оновити | 200, 404, 409, 422 |
| DELETE | `/api/users/{id}` | видалити | 204, 404 |
| GET | `/api/health` | health-check | 200 |

Swagger UI: `/api/docs`, OpenAPI: `/api/openapi.json`.

## Лаба 1 — запуск локально

```bash
# unit-тести (13+4 тести)
cd api && pip install -r requirements-dev.txt && python -m pytest -q

# Docker-образ (тести виконуються під час збірки: образ не збудується, якщо вони падають)
docker build -t users-api:dev api
docker run --rm -p 8080:8080 users-api:dev     # http://localhost:8080/api/docs
```

Без `DATABASE_URL` сервіс використовує SQLite і сам створює таблиці. У Kubernetes схему створює Job з міграціями.

### Налаштування Azure DevOps (Лаба 1, завдання 4) — робиться вручну в UI

1. **Docker Hub:** створіть репозиторії `cicd-users-api`, `cicd-users-web`, `cicd-users-migrations`, `cicd-users-controller` (Docker Hub → Create repository).
   Створіть Access Token (Account settings → Security → New access token, права *Read & Write*).
2. **Azure DevOps:** створіть проєкт (будь-яке ім'я).
3. *Project settings → Service connections → New → Docker Registry → Docker Hub*: вкажіть username і token,
   назва connection — **`dockerhub-connection`** (так її очікує `azure-pipelines.yml`).
4. *Pipelines → New pipeline → GitHub → ваш репозиторій → Existing Azure Pipelines YAML file → `/azure-pipelines.yml`*.
5. У pipeline → *Variables* додайте `DOCKERHUB_REPOSITORY` = `mishablablabla1/cicd-users-api`.
6. Зробіть push у `main` — pipeline запускається автоматично: Build → Test → Docker build → tags (`latest`, `$(Build.BuildId)`) → push.

## Лаба 2 — GitHub Actions

* `.github/workflows/ci.yml` — job `build-n-test` (pytest + збірка Angular) і `docker-pack-n-push`
  (викликає reusable workflow для трьох образів). Тригер: push у `main`, `feature/*`, `bugfix/*`;
  ігноруються зміни в `docs/**` і `README.md`.
* `.github/workflows/docker-pack-n-push.yml` — **reusable workflow** (`workflow_call`) з параметрами
  `repository`, `tag`, `context`, `dockerfile`, `push`. Для `main` образ публікується в Docker Hub,
  для інших гілок — зберігається як artifact workflow.
* Секрети (*Repo → Settings → Secrets and variables → Actions*): **`DOCKERHUB_USERNAME`**, **`DOCKERHUB_TOKEN`**.
  Репозиторії Docker Hub: `cicd-users-api`, `cicd-users-web`, `cicd-users-migrations`, `cicd-users-controller` (останній — для лаби 5).

## Лаба 4 — Kubernetes / Helm

Структура: namespace → `users-db-ss` (StatefulSet) + `users-sc` (StorageClass) + PVC; `users-db-migration-job`
(Helm hook, Alembic); `users-api` (Deployment/Service, Secret + ConfigMap з ConnectionString);
`users-web`; Ingress (`/api` → backend, `/` → frontend). Версії чарту й застосунку — у `Chart.yaml`.

```bash
# локально в kind (образи завантажуються командою kind load)
docker build -t users-api:dev api
docker build -t users-web:dev web
docker build -f migrations/Dockerfile -t users-migrations:dev .
kind load docker-image users-api:dev users-web:dev users-migrations:dev --name <cluster>

helm lint k8s/webapp -f k8s/webapp/values.lab.yaml --strict
helm upgrade --install lab k8s/webapp -n demo --create-namespace \
  -f k8s/webapp/values.lab.yaml --wait --wait-for-jobs --timeout 5m

kubectl -n demo port-forward svc/users-web-svc 8081:80    # http://localhost:8081
```

Для «справжнього» середовища: свій `values.<env>.yaml` (репозиторії образів у Docker Hub, `db.password`,
`ingress.host`) і Ingress-контролер (наприклад ingress-nginx), хост додати в `/etc/hosts`.
Упакувати чарт: `helm package k8s/webapp --destination dist` (CI робить це автоматично, job `helm-package`).

## Лаба 5 — `DatabaseBackup` і контролер

```bash
cd controller/deploy
kubectl apply -f demo-prereqs.yaml                       # namespace demo, Secret, PVC postgres-backups
kubectl apply -f databasebackup-crd.yaml
kubectl wait --for=condition=Established crd/databasebackups.backup.example.com
kubectl apply -f rbac.yaml -f deployment.yaml             # образ users-controller:dev (docker build controller/)
kubectl apply -f databasebackup.yaml
../demo.sh                                                # усі 4 перевірки з методички
```

Хто що створює: `DatabaseBackup` → **наш контролер** створює `CronJob` → **CronJob controller**
(kube-controller-manager) за розкладом створює `Job` → **Job controller** створює `Pod`, у якому `pg_dump -Fc`
пише архів у PVC. Вивід демонстрації: `evidence/lab5-demo-output.txt`.

## Лаба 3

Див. [`lab3-etcd/REPORT.md`](lab3-etcd/REPORT.md) (готовий звіт) і `lab3-etcd/run-lab3.sh` (відтворення експерименту).
