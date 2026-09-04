# Agent Platform — V0

Objetivo: provar a plataforma, não o agente.

A V0 implementa um vertical slice:

`HTTP API -> Agent Platform Core -> Runtime Contract -> Fake Runtime -> Observability`

O DeepSeek Harness (DSH) entra depois como o primeiro `RuntimeAdapter`, sem contaminar o core.

## Requisitos

- Python 3.12+
- `venv`

## Rodar

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn agent_platform.api.main:app --reload
```

Em outro terminal:

```bash
curl -s http://127.0.0.1:8000/health
```

```bash
curl -s   -X POST http://127.0.0.1:8000/runs   -H 'content-type: application/json'   -d '{"agent_id":"demo","input":"hello platform"}'
```

Métricas:

```bash
curl -s http://127.0.0.1:8000/metrics
```

Testes:

```bash
pytest
```

## V0 Definition of Done

- [x] `run_id` único.
- [x] Core depende de `RuntimeContract`, não de um harness concreto.
- [x] Fake Runtime prova o fluxo antes da integração com DSH.
- [x] API HTTP mínima.
- [x] Logs estruturados básicos.
- [x] Métricas Prometheus.
- [x] Smoke test.
- [ ] Model Contract + OpenRouter adapter.
- [ ] DSH Runtime Adapter.
- [ ] Deploy via Compose no homelab.
- [ ] Dashboard Grafana.
