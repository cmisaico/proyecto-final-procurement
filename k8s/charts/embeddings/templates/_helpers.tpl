{{/*
Expand the name of the chart.
*/}}
{{- define "embeddings.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "embeddings.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart label.
*/}}
{{- define "embeddings.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "embeddings.labels" -}}
helm.sh/chart: {{ include "embeddings.chart" . }}
{{ include "embeddings.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "embeddings.selectorLabels" -}}
app.kubernetes.io/name: {{ include "embeddings.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the ConfigMap holding model / service configuration
*/}}
{{- define "embeddings.configMapName" -}}
{{- printf "%s-config" (include "embeddings.fullname" .) }}
{{- end }}

{{/*
Name of the HPA
*/}}
{{- define "embeddings.hpaName" -}}
{{- printf "%s-hpa" (include "embeddings.fullname" .) }}
{{- end }}

{{/*
Name of the model cache PVC (when persistence is enabled)
*/}}
{{- define "embeddings.modelCachePvcName" -}}
{{- printf "%s-model-cache" (include "embeddings.fullname" .) }}
{{- end }}
