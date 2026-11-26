{{- define "sftpgo.image" -}}
{{- $registry := .root.Values.global.imageRegistry -}}
{{- $image := index .root.Values.images .role -}}
{{- if and (not $registry) .override (ne .override "unset") -}}
{{ .override }}
{{- else -}}
{{- if $registry }}{{ trimSuffix "/" $registry }}/{{ end }}{{ $image.repository }}{{ if $image.digest }}@{{ $image.digest }}{{ else }}:{{ $image.tag }}{{ end }}
{{- end -}}
{{- end -}}
