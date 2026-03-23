# Drift Plugins

AI Drift Monitoring Framework의 플러그인 저장소.

## 등록된 플러그인

| Key | Name | Version | Category |
|---|---|---|---|
| cusum | CUSUM | v1.0.0 | statistical |
| ks_test | KS Test | v1.0.0 | statistical |

## 설치

```yaml
# drift_config.yaml
plugins:
  - cusum
  - ks_test
```

```bash
drift-framework install
```
