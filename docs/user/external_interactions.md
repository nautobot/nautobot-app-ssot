# External Interactions

This document describes external dependencies and prerequisites for this App to operate, including system requirements, API endpoints, interconnection or integrations to other applications or services, and similar topics.

## External System Integrations

* When using SSoT to build a custom job, be mindful that, depending on how you are retrieving information from a remote data source, you may need to access over specific ports.

## Prometheus Metrics

Nautobot SSoT will add Prometheus metrics for multiple pieces of data that might be of interest in your environment to the `/api/plugins/capacity-metrics/app-metrics` output if the [Nautobot Capacity Metrics](https://github.com/nautobot/nautobot-plugin-capacity-metrics) app is installed and configured. The following metrics are added:

The Nautobot SSoT app has the Nautobot Capacity Metrics app as a dependency, but it is up to the admin to enable it in the `nautobot_config.py` configuration.

### Registered Metrics

Below are the currently registered metrics for the Nautobot SSoT App:

| Metric Name                                       | Type  | Labels                                       | Description                                     |
| ------------------------------------------------- | ----- | -------------------------------------------- | ----------------------------------------------- |
| nautobot_ssot_duration_seconds                    | Gauge | job, phase                                   | Gives a time duration for each phase of a Job   |
| nautobot_ssot_sync_total                          | Gauge | sync_type                                    | Gives a count of SSoT sync totals based on type |
| nautobot_ssot_operation_total                     | Gauge | job, operation                               | Total number of objects for each operation in Job |
| nautobot_ssot_sync_memory_usage_bytes             | Gauge | job, phase                                   | Memory usage for Job during each phase         |

### Sample Prometheus Metrics

```prometheus
# HELP nautobot_ssot_duration_seconds Nautobot SSoT Job Phase Duration in seconds
# TYPE nautobot_ssot_duration_seconds gauge
nautobot_ssot_duration_seconds{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="source_load_time"} 5314.937
nautobot_ssot_duration_seconds{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="target_load_time"} 28241.297
nautobot_ssot_duration_seconds{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="diff_time"} 1405.652
nautobot_ssot_duration_seconds{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="sync_time"} 21921.814
nautobot_ssot_duration_seconds{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="sync_duration"} 98351.03
# HELP nautobot_ssot_sync_total Nautobot SSoT Sync Totals
# TYPE nautobot_ssot_sync_total gauge
nautobot_ssot_sync_total{sync_type="total_syncs"} 4.0
nautobot_ssot_sync_total{sync_type="pending_syncs"} 0.0
nautobot_ssot_sync_total{sync_type="running_syncs"} 0.0
nautobot_ssot_sync_total{sync_type="completed_syncs"} 3.0
nautobot_ssot_sync_total{sync_type="errored_syncs"} 0.0
nautobot_ssot_sync_total{sync_type="failed_syncs"} 1.0
# HELP nautobot_ssot_operation_total Nautobot SSoT operations by Job
# TYPE nautobot_ssot_operation_total gauge
nautobot_ssot_operation_total{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",operation="skip"} 0.0
nautobot_ssot_operation_total{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",operation="create"} 2.0
nautobot_ssot_operation_total{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",operation="delete"} 0.0
nautobot_ssot_operation_total{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",operation="update"} 0.0
nautobot_ssot_operation_total{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",operation="no-change"} 1731.0
# HELP nautobot_ssot_sync_memory_usage_bytes Nautobot SSoT Sync Memory Usage
# TYPE nautobot_ssot_sync_memory_usage_bytes gauge
nautobot_ssot_sync_memory_usage_bytes{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="skip"} 0.0
nautobot_ssot_sync_memory_usage_bytes{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="create"} 2.0
nautobot_ssot_sync_memory_usage_bytes{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="delete"} 0.0
nautobot_ssot_sync_memory_usage_bytes{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="update"} 0.0
nautobot_ssot_sync_memory_usage_bytes{job="plugins-nautobot_ssot-jobs-examples-exampledatasource",phase="no-change"} 1731.0
nautobot_ssot_sync_memory_usage_bytes{job="",phase=""} 0.0
```
