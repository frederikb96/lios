{{/*
Expand the name of the chart.
*/}}
{{- define "lios.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "lios.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "lios.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "lios.labels" -}}
helm.sh/chart: {{ include "lios.chart" . }}
{{ include "lios.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "lios.selectorLabels" -}}
app.kubernetes.io/name: {{ include "lios.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the ServiceAccount to use.
*/}}
{{- define "lios.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "lios.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Name of the Secret to reference for the database URL / APNs credentials.
*/}}
{{- define "lios.secretName" -}}
{{- if .Values.existingSecret }}
{{- .Values.existingSecret }}
{{- else }}
{{- include "lios.fullname" . }}
{{- end }}
{{- end }}

{{/*
Image tag, falling back to the chart's appVersion.
*/}}
{{- define "lios.imageTag" -}}
{{- default .Chart.AppVersion .Values.image.tag }}
{{- end }}

{{/*
Port the application actually listens on.

`config.server.port` is the value the app reads, so it wins when set. The Service port stays
independent: it is what clients connect to, and defaults to the same number only for
convenience.
*/}}
{{- define "lios.appPort" -}}
{{- dig "server" "port" .Values.service.port .Values.config }}
{{- end }}
