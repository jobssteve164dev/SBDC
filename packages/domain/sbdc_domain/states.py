from enum import StrEnum


class TaskStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    PARSING = "parsing"
    REFERENCES_READY = "references_ready"
    VALIDATION_FAILED = "validation_failed"
    PARSING_FAILED = "parsing_failed"


ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.VALIDATING},
    TaskStatus.VALIDATING: {TaskStatus.PARSING, TaskStatus.VALIDATION_FAILED},
    TaskStatus.VALIDATION_FAILED: {TaskStatus.VALIDATING},
    TaskStatus.PARSING: {TaskStatus.REFERENCES_READY, TaskStatus.PARSING_FAILED},
    TaskStatus.PARSING_FAILED: {TaskStatus.PARSING},
    TaskStatus.REFERENCES_READY: set(),
}


def transition_task(current: TaskStatus | str, target: TaskStatus) -> TaskStatus:
    source = TaskStatus(current)
    if target not in ALLOWED_TRANSITIONS[source]:
        raise ValueError(f"任务不能从 {source.value} 进入 {target.value}")
    return target
