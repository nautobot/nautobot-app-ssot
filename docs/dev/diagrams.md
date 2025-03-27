# Model Diagrams

To aide developers in understanding the various models and how they interoperate for the SSoT project.

```mermaid
erDiagram
DiffSyncModel{
    ClassVar[str] _modelname
    ClassVar[Tuple[str]] _identifiers
    ClassVar[Tuple[str]] _shortname
    ClassVar[Tuple[str]] _attributes
    ClassVar[Dict[str]] _children
    DiffSyncModelFlags model_flags
    Optional[Adapter] adapter
    DiffSyncStatus _status
    string _status_message
    ConfigDict model_config
}
Adapter{
    Optional[str] type
    ClassVar[List[str]] top_level
}
"nautobot_app_ssot.Sync"[Sync]{
    string source
    string target
    datetime start_time
    duration source_load_time
    duration target_load_time
    duration diff_time
    duration sync_time
    PositiveBigIntegerField source_load_memory_final
    PositiveBigIntegerField source_load_memory_peak
    PositiveBigIntegerField target_load_memory_final
    PositiveBigIntegerField target_load_memory_peak
    PositiveBigIntegerField diff_memory_final
    PositiveBigIntegerField diff_memory_peak
    PositiveBigIntegerField sync_memory_final
    PositiveBigIntegerField sync_memory_peak
    boolean dry_run
    json diff
    JobResult job_result FK
}
"nautobot_app_ssot.SyncLogEntry"[SyncLogEntry]{
    Sync sync FK
    datetime timestamp
    string action
    string status
    json diff
    ContentType synced_object_type FK
    uuid synced_object_id
    GenericForeignKey synced_object
    string object_repr
    string message
}
"extras.JobResult"[JobResult]{}
"nautobot_app_ssot.SyncLogEntry" }o--|| "nautobot_app_ssot.Sync" : "must have"
"nautobot_app_ssot.Sync" }o--o| "extras.JobResult" : "may have"
DiffSyncModel||--|{Adapter : adapter
```
