from apps.operations.models import OperationTaskStatus


def task_geometry(task):
    if task.geometry:
        return task.geometry, 'task'
    if task.geo_asset_id and task.geo_asset and task.geo_asset.geometry:
        return task.geo_asset.geometry, 'geo_asset'
    return None, ''


def tasks_to_feature_collection(tasks):
    features = []
    for task in tasks:
        geometry, source = task_geometry(task)
        if not geometry:
            continue
        features.append(
            {
                'type': 'Feature',
                'id': task.id,
                'geometry': geometry,
                'properties': {
                    'id': task.id,
                    'code': task.code,
                    'title': task.title,
                    'status': task.status,
                    'status_label': OperationTaskStatus(task.status).label,
                    'priority': task.priority,
                    'area': task.area.name if task.area_id else '',
                    'area_id': task.area_id,
                    'task_type': task.task_type.name if task.task_type_id else '',
                    'task_type_id': task.task_type_id,
                    'geo_asset_id': task.geo_asset_id,
                    'geo_asset_title': task.geo_asset.title if task.geo_asset_id and task.geo_asset else '',
                    'parcela_id': task.parcela_id,
                    'parcela_code': task.parcela.codigo_parcela if task.parcela_id and task.parcela else '',
                    'due_at': task.due_at.isoformat() if task.due_at else None,
                    'detected_at': task.detected_at.isoformat() if task.detected_at else None,
                    'geometry_source': source,
                    'geometry_type': task.geometry_type,
                    'length_m': task.length_m,
                    'perimeter_m': task.perimeter_m,
                    'area_m2': task.area_m2,
                    'vertex_count': task.vertex_count,
                    'is_overdue': task.is_overdue,
                },
            }
        )
    return {'type': 'FeatureCollection', 'features': features}
