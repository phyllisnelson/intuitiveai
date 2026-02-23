"""arq task functions — executed inside the arq worker process.

Each function receives a context dict populated by ``startup`` in
``app.workers.main``.  The context holds a fully-initialised
``OpenStackService`` instance under the key ``"svc"``.

Functions are registered in ``WorkerSettings.functions`` so arq routes
enqueued jobs to them by name.
"""

from app.services.openstack_service import POLL_TIMEOUT_SECONDS


async def poll_until_active(
    ctx: dict,
    vm_id: str,
    task_id: str,
    timeout: int = POLL_TIMEOUT_SECONDS,
) -> None:
    await ctx["svc"].poll_until_active(vm_id, task_id, timeout)


async def do_delete(ctx: dict, vm_id: str, task_id: str) -> None:
    await ctx["svc"].do_delete(vm_id, task_id)


async def do_resize(
    ctx: dict,
    vm_id: str,
    task_id: str,
    flavor_id: str,
) -> None:
    await ctx["svc"].do_resize(vm_id, task_id, flavor_id)
