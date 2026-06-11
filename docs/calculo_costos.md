# Cálculo de Costos — Autonomous Procurement Intelligence Platform

**Fecha:** Junio 2026 | **Región:** Brazil South (brazilsouth)

---

## 1. Comparativa Dev vs Producción

### Infraestructura base (Terraform)

| Recurso | Dev (actual) | Dev $/mes | Prod | Prod $/mes |
|---------|-------------|-----------|------|-----------|
| ACR | Basic, sin red privada | ~$5 | Premium + geo-replication | ~$500 |
| PostgreSQL | B_Standard_B1ms, 32 GB, sin HA | ~$13 | GP_Standard_D4s_v3, 128 GB, ZoneRedundant HA | ~$800 |
| Key Vault | soft_delete 7d, sin purge_protection | ~$2 | soft_delete 90d, purge_protection on | ~$5 |
| Storage Account | Sin versioning, retención 7d | ~$3 | Versioning + change_feed, retención 30d | ~$10 |
| Log Analytics | 30 días (capa gratuita) | ~$0 | 90 días, 5 GB/día | ~$35 |
| Azure Managed Grafana | Standard | ~$50 | Standard | ~$50 |
| Private Endpoints (4x) | No | $0 | ACR, KV, PSQL, Storage | ~$29 |
| Azure Front Door | No | $0 | Standard | ~$35 |
| **Subtotal Terraform** | | **~$73/mes** | | **~$1,464/mes** |

### Kubernetes (AKS + node pools)

| Recurso | Dev | Dev $/mes | Prod | Prod $/mes |
|---------|-----|-----------|------|-----------|
| AKS Control Plane | Free tier | ~$0 | Standard tier | ~$73 |
| System Pool | 1× DS2_v2 on-demand (min=1) | ~$56 | 3× DS2_v2 reserved 1yr | ~$120 |
| User Pool | 1× D2as_v4 on-demand (min=1) | ~$56 | 3× D4s_v3 reserved 1yr | ~$290 |
| GPU Pool | 1× NC4as_T4_v3 Regular (8h/día, 22 días) | **~$88** | 1× NC4ads_L4_v3 on-demand (24/7) | ~$324 |
| Ancho de banda | ~10 GB egreso | ~$1 | ~100 GB egreso | ~$8 |
| **Subtotal AKS** | | **~$201/mes** | | **~$815/mes** |

### Total

| | Dev | Prod |
|-|-----|------|
| Terraform (infra base) | ~$73/mes | ~$1,464/mes |
| AKS + node pools | ~$201/mes | ~$815/mes |
| **TOTAL** | **~$274/mes** | **~$2,279/mes** |
| Ahorro dev vs prod | | **~$2,005/mes (88%)** |

---

## 2. Desglose mensual desarrollo (ambiente actual)

| Recurso | Configuración | Costo/mes |
|---------|---------------|-----------|
| AKS System Pool | 1× DS2_v2 on-demand, min=1 | ~$56 |
| AKS User Pool | 1× D2as_v4 on-demand, min=1 | ~$56 |
| **AKS GPU Pool** | **1× NC4as_T4_v3 Regular, 8h/día, 22 días hábiles** | **~$88** |
| PostgreSQL | B_Standard_B1ms + 32 GB, sin HA | ~$13 |
| Storage Account | Standard LRS | ~$3 |
| ACR Basic | Sin geo-replication | ~$5 |
| Key Vault Standard | Sin purge_protection | ~$2 |
| Log Analytics | 30 días (dentro de capa gratuita) | ~$0 |
| Azure Managed Grafana | Standard | ~$50 |
| Ancho de banda | 10 GB egreso | ~$1 |
| **TOTAL MENSUAL DEV** | | **~$274/mes** |

> El GPU pool es el mayor costo individual (~32% del total). Con auto-shutdown a las 20:00 UTC y min-count=0, el costo baja de ~$360/mes (24/7) a ~$88/mes.

---

## 3. Comparativa de GPUs

| GPU | SKU Azure | VRAM | TFLOPS FP16 | On-demand/hr | Throughput AWQ |
|-----|-----------|------|-------------|-------------|----------------|
| **NVIDIA T4** (dev actual) | NC4as_T4_v3 | 16 GB | 65 | **~$0.50** | ~600 tok/s |
| NVIDIA L4 (prod) | NC4ads_L4_v3 | 24 GB | 121 | ~$1.50 | ~1,400 tok/s |
| NVIDIA A10 | NC6ads_A10_v4 | 24 GB | 125 | ~$2.20 | ~1,600 tok/s |
| NVIDIA L40S | NC8ads_L40S_v1 | 48 GB | 362 | ~$4.50 | ~3,000 tok/s |

### Justificación de la elección T4 para dev

| Criterio | Evaluación |
|----------|-----------|
| VRAM disponible con AWQ (4.2 GB) | ✅ 11.8 GB libres para KV cache |
| Throughput suficiente para demos | ✅ ~600 tok/s = ~7.9 req/s @ 500 tok/req |
| Costo académico | ✅ $0.50/hr (3x más barato que L4) |
| Cuota disponible en brazilsouth | ✅ NC4as_T4_v3 Regular disponible inmediatamente |
| Soporta modelo FP16 | ❌ T4 solo 16 GB VRAM — FP16 (14.5 GB) no deja espacio para KV cache |
| Spot disponible en brazilsouth | ❌ Sin cuota Spot para NC4as_T4_v3 en brazilsouth |

---

## 4. Costo por request y por licitación

### Cálculo base

```
GPU T4 Regular:
  Throughput:     ~600 tok/s
  Requests/hora:  (600 tok/s × 3,600 s/hr) / 500 tok/req = 4,320 req/hr
  Costo GPU/req:  $0.50/hr ÷ 4,320 req/hr = $0.000116/request

GPU L4 on-demand (producción):
  Throughput:     ~1,400 tok/s
  Requests/hora:  (1,400 × 3,600) / 500 = 10,080 req/hr
  Costo GPU/req:  $1.50/hr ÷ 10,080 = $0.000149/request
```

### Costo por licitación completa (análisis full workflow)

Una licitación compleja requiere:
- 10 llamadas a vLLM (~5,000 tokens total)
- 30 segundos de CPU en API Gateway + LangGraph
- 2 MB de almacenamiento de documentos

```
GPU (T4):    10 × $0.000116 = $0.00116
CPU/infra:   30s × $0.0015/min = $0.00075
Storage:     2 MB × $0.0000192/MB = $0.000038
─────────────────────────────────────────────
Total:       ~$0.002 por licitación (0.2 centavos de dólar)
```

---

## 5. Costo por millón de tokens

```
T4 Regular (dev):
  1,000,000 / 600 tok/s = 1,667 s = 27.8 min
  $0.50/hr × (27.8/60) hr = ~$0.23/millón de tokens

L4 on-demand (prod):
  1,000,000 / 1,400 tok/s = 714 s = 11.9 min
  $1.50/hr × (11.9/60) hr = ~$0.30/millón de tokens
```

Comparativa con OpenAI API (GPT-4o):
- GPT-4o: ~$5/M tokens input + $15/M tokens output
- T4 dev: ~$0.23/M tokens (≈22x más barato)
- L4 prod: ~$0.30/M tokens (≈17x más barato)

---

## 6. ROI y análisis de negocio

### Escenario: equipo de licitaciones con 10 analistas

| Métrica | Situación actual (manual) | Con la plataforma |
|---------|--------------------------|-------------------|
| Tiempo análisis/licitación | 8-16 horas | 5-10 minutos |
| Licitaciones procesadas/mes | 5-10 | 50-200 |
| Costo de tiempo (analista $30/hr) | $240-$480/licitación | $2.50-5 (supervisión) |
| Costo de infraestructura | $0 (manual) | ~$274/mes dev / $2,279/mes prod |
| **Ahorro en horas @ 100 licitaciones/mes** | $24,000-$48,000 | **$274 (dev)** |
| **ROI mensual dev** | | **~$23,700-$47,700** |

---

## 7. Alertas de costo configuradas

```bash
# Presupuesto dev: $500/mes
# Alertas al 60% ($300) y 90% ($450)
az consumption budget create \
  --budget-name "procurement-dev-budget" \
  --amount 500 \
  --time-grain Monthly \
  --notifications '[
    {"enabled": true, "operator": "GreaterThan", "threshold": 60,
     "contactEmails": ["christian.misaico.1992@outlook.com"], "thresholdType": "Actual"},
    {"enabled": true, "operator": "GreaterThan", "threshold": 90,
     "contactEmails": ["christian.misaico.1992@outlook.com"], "thresholdType": "Forecasted"}
  ]'
```

---

## 8. Migración de dev a producción — delta de cambios

| Cambio | Variable Terraform | Delta mensual |
|--------|-------------------|---------------|
| ACR Basic → Premium + geo-replication | `enable_private_endpoints=true` + SKU | +$495 |
| PostgreSQL B1ms → GP_D4s_v3 + HA | SKU change | +$787 |
| Private Endpoints (4×) | `enable_private_endpoints=true` | +$29 |
| Azure Front Door Standard | Nuevo recurso | +$35 |
| Log Analytics 30d → 90d | `log_retention_days=90` | +$35 |
| AKS Free → Standard tier | `--tier Standard` | +$73 |
| GPU Pool T4 → L4 (24/7) | Node SKU + on-demand | +$236 |
| GPU pool 8h → 24/7 | min-count=1, auto-shutdown off | incluido arriba |
| **Total delta dev → prod** | | **~+$2,005/mes** |

El único flag que controla la mayoría de cambios (ACR, PostgreSQL, Key Vault, endpoints privados) es `enable_private_endpoints` en el módulo Terraform.