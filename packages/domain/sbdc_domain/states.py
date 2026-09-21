from enum import StrEnum


class TaskStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    PARSING = "parsing"
    REFERENCES_READY = "references_ready"
    FETCHING_SOURCES = "fetching_sources"
    INDEXING = "indexing"
    CHECKING = "checking"
    CHECKING_FAILED = "checking_failed"
    REVIEW_READY = "review_ready"
    REVIEWED = "reviewed"
    REPORTING = "reporting"
    COMPLETED = "completed"
    RETENTION_PENDING = "retention_pending"
    PURGED = "purged"
    PURGE_FAILED = "purge_failed"
    VALIDATION_FAILED = "validation_failed"
    PARSING_FAILED = "parsing_failed"


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.VALIDATING},
    TaskStatus.VALIDATING: {TaskStatus.PARSING, TaskStatus.VALIDATION_FAILED},
    TaskStatus.VALIDATION_FAILED: {TaskStatus.VALIDATING},
    TaskStatus.PARSING: {TaskStatus.REFERENCES_READY, TaskStatus.PARSING_FAILED},
    TaskStatus.PARSING_FAILED: {TaskStatus.PARSING},
    TaskStatus.REFERENCES_READY: {TaskStatus.FETCHING_SOURCES, TaskStatus.CHECKING},
    TaskStatus.FETCHING_SOURCES: {TaskStatus.INDEXING, TaskStatus.CHECKING_FAILED},
    TaskStatus.INDEXING: {TaskStatus.CHECKING, TaskStatus.CHECKING_FAILED},
    TaskStatus.CHECKING: {TaskStatus.REVIEW_READY, TaskStatus.REVIEWED, TaskStatus.CHECKING_FAILED},
    TaskStatus.CHECKING_FAILED: {TaskStatus.FETCHING_SOURCES, TaskStatus.CHECKING, TaskStatus.RETENTION_PENDING},
    TaskStatus.REVIEW_READY: {TaskStatus.CHECKING, TaskStatus.REVIEWED},
    TaskStatus.REVIEWED: {TaskStatus.REPORTING},
    TaskStatus.REPORTING: {TaskStatus.COMPLETED},
    TaskStatus.COMPLETED: {TaskStatus.RETENTION_PENDING},
    TaskStatus.RETENTION_PENDING: {TaskStatus.PURGED, TaskStatus.PURGE_FAILED},
    TaskStatus.PURGE_FAILED: {TaskStatus.RETENTION_PENDING},
    TaskStatus.PURGED: set(),
}


def transition_task(current: TaskStatus | str, target: TaskStatus) -> TaskStatus:
    source = TaskStatus(current)
    if target not in ALLOWED_TRANSITIONS[source]:
        raise ValueError(f"任务不能从 {source.value} 进入 {target.value}")
    return target
