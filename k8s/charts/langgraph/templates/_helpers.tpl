{{/*
Expand the name of the chart.
*/}}
{{- define "langgraph.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains the chart name it will be used as a full name.
*/}}
{{- define "langgraph.fullname" -}}
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
Create chart label value.
*/}}
{{- define "langgraph.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "langgraph.labels" -}}
helm.sh/chart: {{ include "langgraph.chart" . }}
{{ include "langgraph.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels — used in matchLabels.
*/}}
{{- define "langgraph.selectorLabels" -}}
app.kubernetes.io/name: {{ include "langgraph.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use.
*/}}
{{- define "langgraph.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "langgraph.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Name of the ConfigMap holding non-secret environment variables.
*/}}
{{- define "langgraph.configmapName" -}}
{{- printf "%s-config" (include "langgraph.fullname" .) }}
{{- end }}

{{/*
Name of the Secret holding sensitive environment variables.
*/}}
{{- define "langgraph.secretName" -}}
{{- printf "%s-secret" (include "langgraph.fullname" .) }}
{{- end }}
