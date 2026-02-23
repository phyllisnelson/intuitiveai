from enum import StrEnum


class VMState(StrEnum):
    BUILDING = "BUILDING"
    ACTIVE = "ACTIVE"
    SHUTOFF = "SHUTOFF"
    SUSPENDED = "SUSPENDED"
    REBOOT = "REBOOT"
    ERROR = "ERROR"
    DELETED = "DELETED"
    RESIZE = "RESIZE"
    VERIFY_RESIZE = "VERIFY_RESIZE"
    UNKNOWN = "UNKNOWN"


class VMAction(StrEnum):
    START = "start"
    STOP = "stop"
    REBOOT = "reboot"
    HARD_REBOOT = "hard_reboot"
    SUSPEND = "suspend"
    RESUME = "resume"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
