from app.services.exceptions.base import NotFoundError


class ProjectNotFoundError(NotFoundError):
    """Проект не найден."""

    def __init__(self, project_id: int) -> None:
        super().__init__(entity='Project', obj_id=project_id)
