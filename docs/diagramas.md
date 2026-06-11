# Diagramas Formales — Autonomous Procurement Intelligence Platform

**Fecha:** Junio 2026

> Para cada diagrama se incluye: (1) descripción del diagrama, (2) código fuente (Mermaid / PlantUML) y (3) **prompt detallado** para generar una versión visual con un modelo de IA (DALL-E 3, Midjourney, o Claude).

---

## D-01: Arquitectura de Alto Nivel (Cloud)

### Descripción
Diagrama de arquitectura mostrando los componentes cloud en AKS, las conexiones entre servicios, y los managed services de Azure.

### Código Mermaid

```mermaid
graph TB
    subgraph Internet
        User["👤 Usuario Final"]
        GHA["⚙️ GitHub Actions\n(CI/CD)"]
    end

    subgraph AzureCloud["☁️ Azure Cloud — brazilsouth"]
        ACR["📦 ACR Basic\nacrprocurementdev"]
        KV["🔑 Key Vault\nkv-procurement-az-dev"]

        subgraph AKS["🚀 AKS Cluster — aks-procurement-dev (Free tier)"]
            subgraph SystemPool["System Pool (DS2_v2 x1-3)"]
                Ingress["🌐 NGINX Ingress\n(Public LB)"]
            end

            subgraph UserPool["User Pool (D4s_v3 x1-4)"]
                API["⚡ API Gateway\n(FastAPI, HPA 2-8)"]
                LG["🤖 LangGraph\n(Agentes)"]
                EMB["🧮 Embeddings\n(sentence-transformers)"]
                Qdrant["🗄️ Qdrant\n(Vector DB)"]
                OTel["📡 OTel Collector"]
            end

            subgraph GPUPool["GPU Pool (NC4as_T4_v3 x0-2 Regular)"]
                vLLM["🧠 vLLM\nQwen2.5-7B-AWQ\nescala manual / Cluster Autoscaler"]
            end

            subgraph Monitoring["Namespace: monitoring"]
                Prom["📊 Prometheus"]
                Grafana["📈 Grafana"]
                Loki["📋 Loki + Promtail"]
            end
        end

        PSQL["🐘 PostgreSQL\nB_Standard_B1ms"]
        Blob["📁 Blob Storage\nStandard LRS"]
        Grafana_M["📊 Managed Grafana\ngraf-procurement-dev"]
    end

    User -->|"HTTPS"| Ingress
    GHA -->|"docker push"| ACR
    GHA -->|"helm upgrade"| AKS
    Ingress --> API
    API --> LG
    API --> EMB
    API --> Qdrant
    LG --> vLLM
    API --> vLLM
    EMB --> Qdrant
    API --> PSQL
    API --> Blob
    KV -.->|"CSI mount"| API
    API --> OTel
    OTel --> Prom
    Prom --> Grafana
    Prom --> Grafana_M
    Loki --> Grafana
```

---

## D-02: Flujo de Datos — Workflow Multi-Agente

### Descripción
Diagrama de secuencia mostrando el flujo completo del análisis de licitación desde la petición del usuario hasta el reporte final.

### Código PlantUML

```plantuml
@startuml MultiAgentWorkflow
!theme plain
skinparam backgroundColor #FAFAFA

actor "Usuario" as U
participant "API Gateway\n(FastAPI)" as API
participant "RunFullAnalysis\nUseCase" as UC
participant "Legal Agent\n(LangGraph)" as LA
participant "Proposal Agent\n(LangGraph)" as PA
participant "Audit Agent\n(LangGraph)" as AA
database "Qdrant\n(Vector DB)" as QD
participant "vLLM\n(Qwen2.5-7B)" as LLM
database "PostgreSQL" as DB

U -> API: POST /workflow/full-analysis\n{tender_id}
API -> UC: execute(tender_id)
UC -> DB: create_workflow_record(RUNNING)

group Legal Analysis
    UC -> LA: run(tender_id)
    LA -> QD: retrieve_top_k(query_embedding, k=10)
    QD --> LA: relevant_chunks
    LA -> LLM: analyze_legal_requirements(chunks)
    LLM --> LA: legal_output {risks, obligations}
    LA --> UC: legal_output
end

group Proposal Generation
    UC -> PA: run(tender_id, legal_output)
    PA -> QD: retrieve_top_k(technical_query, k=10)
    QD --> PA: technical_chunks
    PA -> LLM: generate_proposal(chunks, legal_output)
    LLM --> PA: proposal_output {technical, economic}
    PA --> UC: proposal_output
end

group Compliance Audit
    UC -> AA: run(tender_id, legal_output, proposal_output)
    AA -> LLM: audit_compliance(legal, proposal)
    LLM --> AA: audit_output {score: 0.92, observations}
    AA --> UC: audit_output
end

UC -> DB: save_final_report(legal+proposal+audit)
UC -> DB: update_workflow(COMPLETED)
UC --> API: FullAnalysisResponse
API --> U: {workflow_id, status: "completed",\nfinal_report: {...}}

@enduml
```

---

## D-03: Arquitectura de Observabilidad

### Código Mermaid

```mermaid
flowchart LR
    subgraph Sources["Fuentes de datos"]
        API["API Gateway\n/metrics"]
        vLLM["vLLM\n/metrics"]
        K8S["kube-state-metrics"]
        DCGM["DCGM Exporter\n(GPU metrics)"]
        Pods["Logs de Pods\n(stdout/stderr)"]
    end

    subgraph Collection["Recolección"]
        SM["ServiceMonitor\n(x3)"]
        PT["Promtail\n(DaemonSet)"]
        OTel["OTel Collector\n(traces)"]
    end

    subgraph Storage["Almacenamiento"]
        Prom["Prometheus\n(métricas, 15d)"]
        Loki["Loki\n(logs, 7d)"]
    end

    subgraph Visualization["Visualización"]
        G1["Dashboard:\nLLM & RAG"]
        G2["Dashboard:\nPlatform API"]
        G3["Dashboard:\nGPU & Infra"]
        G4["Dashboard:\nAgents"]
        Grafana["Grafana\n(4 dashboards)"]
    end

    subgraph Alerts["Alertas"]
        PR["PrometheusRule:\nGPUThrottling\nAPIHighLatency\nPodCrashLoop"]
        AM["AlertManager"]
        Email["Email\nchristian.misaico.1992@outlook.com"]
    end

    API & vLLM & K8S & DCGM -->|"scrape 15s"| SM --> Prom
    Pods --> PT --> Loki
    API --> OTel --> Prom
    Prom --> Grafana --> G1 & G2 & G3 & G4
    Loki --> Grafana
    Prom --> PR --> AM --> Email
```

---

## D-04: Estrategia de Autoscaling (3 niveles)

### Código Mermaid

```mermaid
graph TD
    Load["📈 Carga de trabajo"] --> L1 & L2 & L3

    subgraph L1["Nivel 1 — Vertical (VPA)"]
        VPA["VPA ajusta\nCPU/Memory requests\nde pods existentes"]
    end

    subgraph L2["Nivel 2 — Horizontal Pods"]
        HPA["HPA (CPU > 70%)\nAPI Gateway: 2→8 pods\nLangGraph: 1→4 pods (Memory > 80%)"]
        KEDA["KEDA (planificado, no desplegado)\nvLLM: 1→4 pods\ncola > 10 requests"]
    end

    subgraph L3["Nivel 3 — Horizontal Nodes"]
        CA["Cluster Autoscaler\nUser Pool: 1→4 nodos\nGPU Pool: 0→2 nodos T4"]
    end

    HPA -->|"pods Pending"| CA
    KEDA -.->|"planificado"| CA

    subgraph Costs["💰 Impacto en costos"]
        C1["VPA: sin costo adicional\n(optimiza recursos)"]
        C2["HPA: +$56/nodo D4s_v3"]
        C3["KEDA (futuro): +$0.50/hr/nodo T4"]
    end

    L1 -.-> C1
    L2 -.-> C2
    L3 -.-> C3
```

---

## D-05: Patrones LLM — Guardrail + Efficient Context

### Código Mermaid

```mermaid
flowchart TD
    Input["📝 Usuario\n(pregunta)"] --> IG

    subgraph IG["🛡️ Input Guardrail"]
        PI["Prompt Injection\nDetector"]
        JB["Jailbreak\nClassifier"]
        PII_IN["PII Detector"]
        TL["Token Limit\nValidator"]
    end

    IG -->|"✅ PASS"| ECH
    IG -->|"❌ BLOCK"| Reject["400 Bad Request\n+ Log"]

    subgraph ECH["📚 Efficient Context Handler"]
        QE["Query Embedding\n(384-dim)"]
        RET["Retrieval Top-K=10\n(Qdrant HNSW)"]
        COMP["Compressor\n(60% reducción)"]
        RANK["Re-ranker\n(MMR + similarity)"]
    end

    ECH --> LLM

    subgraph LLM["🧠 vLLM — Continuous Batching"]
        BATCH["Batch scheduler\n(16-32 requests)"]
        INFER["Qwen2.5-7B-AWQ\n(T4 GPU, ~600 tok/s)"]
    end

    LLM --> OG

    subgraph OG["🛡️ Output Guardrail"]
        HALL["Hallucination\nDetector"]
        FACT["Factual\nConsistency"]
        PII_OUT["PII Masker"]
    end

    OG -->|"✅ PASS"| Output["✅ Respuesta\nvalidada"]
    OG -->|"❌ FAIL"| Fallback["⚠️ Fallback\nResponse"]

    style IG fill:#fff3cd
    style OG fill:#fff3cd
    style ECH fill:#d1ecf1
    style LLM fill:#d4edda
```

---

## D-06: CI/CD Pipeline — GitHub Actions

### Código Mermaid

```mermaid
flowchart LR
    Push["git push\nmain"] --> J1

    subgraph J1["Job 1: Build & Test\n(ubuntu-latest)"]
        B1["Az Login\n+ ACR Login"]
        B2["Import base images\nto ACR"]
        B3["pytest\n(continue-on-error)"]
        B4["docker build\n(sin push)"]
        B5["Upload artifact\n(image.tar)"]
        B1 --> B2 --> B3 --> B4 --> B5
    end

    subgraph J1B["Job 1b: Build Frontend\n(parallel)"]
        F1["docker build\nfrontend"]
        F2["Push to ACR\n(si main)"]
        F1 --> F2
    end

    J1 --> J2
    J1B --> J4

    subgraph J2["Job 2: Security Scan\n(Trivy)"]
        S1["Download artifact"]
        S2["Trivy scan\nCRITICAL/HIGH\nexit-code: 0"]
        S1 --> S2
    end

    J2 --> J3

    subgraph J3["Job 3: Push to ACR"]
        P1["Load image"]
        P2["Tag + Push\n:sha + :latest"]
        P1 --> P2
    end

    J3 --> J4

    subgraph J4["Job 4: Deploy\n(environment: production)"]
        D1["GPU Operator\n(helm upgrade)"]
        D2["Frontend\n(kubectl apply)"]
        D3["API Gateway\n(helm upgrade)"]
        D4["Canary deploy\n(argo rollouts)"]
        D5["Smoke tests\n(curl /health)"]
        D6["K6 canary\n(error < 5%)"]
        D7["Promote 100%"]
        D1 --> D2 --> D3 --> D4 --> D5 --> D6 --> D7
    end

    J4 -->|"failure"| J5

    subgraph J5["Job 5: Rollback\n(if: failure)"]
        R1["argo rollouts undo\napi-gateway"]
    end

    style J5 fill:#ffcccc
    style J4 fill:#d4edda
```