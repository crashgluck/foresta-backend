from django.db import transaction
from django.utils import timezone
from rest_framework import exceptions

from apps.operations.models import OperationTaskHistory, OperationTaskStatus
from apps.operations.permissions import can_force_close


ALLOWED_TRANSITIONS = {
    OperationTaskStatus.DETECTED: {
        OperationTaskStatus.EVALUATED,
        OperationTaskStatus.ASSIGNED,
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.EVALUATED: {
        OperationTaskStatus.ASSIGNED,
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.ASSIGNED: {
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.IN_PROGRESS: {
        OperationTaskStatus.EXECUTED,
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.EXECUTED: {
        OperationTaskStatus.VERIFICATION,
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.VERIFICATION: {
        OperationTaskStatus.CLOSED,
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.BLOCKED,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.BLOCKED: {
        OperationTaskStatus.EVALUATED,
        OperationTaskStatus.ASSIGNED,
        OperationTaskStatus.IN_PROGRESS,
        OperationTaskStatus.CANCELLED,
    },
    OperationTaskStatus.CLOSED: set(),
    OperationTaskStatus.CANCELLED: set(),
}


def task_snapshot(task):
    return {
        'code': task.code,
        'title': task.title,
        'status': task.status,
        'priority': task.priority,
        'area_id': task.area_id,
        'task_type_id': task.task_type_id,
        'geo_asset_id': task.geo_asset_id,
        'parcela_id': task.parcela_id,
        'executor_id': task.executor_id,
        'executor_user_id': task.executor_user_id,
        'executor_manual_label': task.executor_manual_label,
        'registered_by_id': task.registered_by_id,
        'verified_by_id': task.verified_by_id,
        'detected_at': task.detected_at.isoformat() if task.detected_at else None,
        'due_at': task.due_at.isoformat() if task.due_at else None,
        'executed_at': task.executed_at.isoformat() if task.executed_at else None,
        'verification_at': task.verification_at.isoformat() if task.verification_at else None,
        'closed_at': task.closed_at.isoformat() if task.closed_at else None,
    }


def create_history(task, *, user, action, previous_status='', new_status='', comment='', reason='', changed_fields=None):
    return OperationTaskHistory.objects.create(
        task=task,
        previous_status=previous_status or '',
        new_status=new_status or '',
        user=user if getattr(user, 'is_authenticated', False) else None,
        action=action,
        comment=comment or '',
        reason=reason or '',
        changed_fields=changed_fields or {},
        snapshot=task_snapshot(task),
    )


def _validate_transition(task, new_status, *, user, force=False):
    current_status = task.status
    if new_status == current_status:
        raise exceptions.ValidationError({'status': 'La tarea ya esta en ese estado.'})
    force_close_allowed = new_status == OperationTaskStatus.CLOSED and force and current_status == OperationTaskStatus.EXECUTED
    if new_status not in ALLOWED_TRANSITIONS.get(current_status, set()) and not force_close_allowed:
        raise exceptions.ValidationError({'status': f'Transicion no permitida desde {current_status} a {new_status}.'})
    if new_status in {OperationTaskStatus.ASSIGNED, OperationTaskStatus.IN_PROGRESS} and not task.has_executor():
        raise exceptions.ValidationError({'executor': 'Debes asignar un ejecutor antes de avanzar.'})
    if new_status == OperationTaskStatus.EXECUTED and not task.obtained_result:
        raise exceptions.ValidationError({'obtained_result': 'Debes registrar el resultado ejecutado antes de marcar Ejecutado.'})
    if new_status == OperationTaskStatus.CLOSED and not task.verification_at:
        if not force:
            raise exceptions.ValidationError({'verification': 'Ejecutado no permite cerrar sin verificacion.'})
        if not can_force_close(user):
            raise exceptions.PermissionDenied('No tienes permiso para cierre forzado.')


@transaction.atomic
def transition_task(task, *, new_status, user, comment='', reason='', force=False, changed_fields=None):
    _validate_transition(task, new_status, user=user, force=force)
    previous_status = task.status
    now = timezone.now()

    if new_status == OperationTaskStatus.EXECUTED and not task.executed_at:
        task.executed_at = now
    if new_status == OperationTaskStatus.CLOSED:
        task.closed_at = now
        if force and not task.verification_at:
            task.verification_at = now
            task.verified_by = user if getattr(user, 'is_authenticated', False) else None

    task.status = new_status
    task.updated_by = user if getattr(user, 'is_authenticated', False) else None
    task.save()
    create_history(
        task,
        user=user,
        action='transition',
        previous_status=previous_status,
        new_status=new_status,
        comment=comment,
        reason=reason,
        changed_fields=changed_fields,
    )
    return task


@transaction.atomic
def assign_task(task, *, user, executor=None, executor_user=None, executor_manual_label='', comment=''):
    previous_status = task.status
    task.executor = executor
    task.executor_user = executor_user
    task.executor_manual_label = executor_manual_label or ''
    if not task.has_executor():
        raise exceptions.ValidationError({'executor': 'Debes informar executor, executor_user o executor_manual_label.'})
    if task.status in {OperationTaskStatus.DETECTED, OperationTaskStatus.EVALUATED}:
        task.status = OperationTaskStatus.ASSIGNED
    task.updated_by = user if getattr(user, 'is_authenticated', False) else None
    task.save()
    create_history(
        task,
        user=user,
        action='assign',
        previous_status=previous_status,
        new_status=task.status,
        comment=comment,
        changed_fields={
            'executor_id': task.executor_id,
            'executor_user_id': task.executor_user_id,
            'executor_manual_label': task.executor_manual_label,
        },
    )
    return task


@transaction.atomic
def verify_task(task, *, user, comment=''):
    if task.status != OperationTaskStatus.EXECUTED:
        raise exceptions.ValidationError({'status': 'Solo una tarea Ejecutada puede pasar a verificacion.'})
    previous_status = task.status
    task.status = OperationTaskStatus.VERIFICATION
    task.verified_by = user if getattr(user, 'is_authenticated', False) else None
    task.verification_at = timezone.now()
    task.updated_by = user if getattr(user, 'is_authenticated', False) else None
    task.save()
    create_history(task, user=user, action='verify', previous_status=previous_status, new_status=task.status, comment=comment)
    return task


@transaction.atomic
def reopen_task(task, *, user, comment='', next_status=OperationTaskStatus.IN_PROGRESS):
    if task.status != OperationTaskStatus.CLOSED:
        raise exceptions.ValidationError({'status': 'Solo una tarea cerrada puede reabrirse.'})
    if next_status not in {OperationTaskStatus.EVALUATED, OperationTaskStatus.ASSIGNED, OperationTaskStatus.IN_PROGRESS}:
        raise exceptions.ValidationError({'status': 'Estado de reapertura no permitido.'})
    previous_status = task.status
    task.status = next_status
    task.closed_at = None
    task.updated_by = user if getattr(user, 'is_authenticated', False) else None
    task.save()
    create_history(task, user=user, action='reopen', previous_status=previous_status, new_status=task.status, comment=comment)
    return task
