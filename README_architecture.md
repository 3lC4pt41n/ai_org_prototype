flowchart LR
    subgraph Client
      UI["Frontend (React)"]
    end
    subgraph Server
      API["FastAPI API Server"]
      ORCH["Orchestrator\nScheduler"]
      CELERY["Celery Workers\n(Queues: architect/dev/...)"]
    end
    subgraph Data
      PG[(Postgres DB)]
      Neo4j[(Neo4j Graph DB)]
      Qdrant[(Qdrant Vector DB)]
      Redis[(Redis Broker)]
    end
    subgraph Monitoring
      Prom[[Prometheus]]
      Exporter[[Celery Exporter]]
      Grafana[[Grafana]]
    end

    UI -- HTTP --> API
    API -- reads/writes --> PG
    API -- graph ops --> Neo4j
    API -- vector search --> Qdrant
    API -- enqueues tasks --> Redis
    ORCH -- schedules --> Redis
    CELERY -- pulls jobs --> Redis
    CELERY -- updates --> PG & Neo4j & Qdrant
    Prom -- scrape metrics --> API
    Prom -- scrape metrics --> Exporter
    Grafana -- queries --> Prom
