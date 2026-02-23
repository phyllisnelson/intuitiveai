"""Task polling endpoint.

GET /api/v1/tasks/{task_id}  — check the status of an async operation.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ReadAuthDep, TaskStoreDep
from app.schemas.common import APIResponse
from app.schemas.task import TaskResponse

router = APIRouter(tags=["tasks"])


@router.get(
    "/tasks/{task_id}",
    response_model=APIResponse[TaskResponse],
    summary="Poll an async operation",
)
async def get_task(
    task_id: str,
    task_store: TaskStoreDep,
    _auth: ReadAuthDep,
) -> APIResponse[TaskResponse]:
    """Check the status of a long-running operation (create / delete / resize …).

    Poll this endpoint after receiving a 202 Accepted response from any
    mutating VM operation.  Returns the task record including its current
    ``status`` (pending → running → success | failed).
    """
    task = await task_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return APIResponse(data=task)
