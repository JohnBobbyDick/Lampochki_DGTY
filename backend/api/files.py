import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from models.schemas import ZipRequest

router = APIRouter()


def _unsafe(path: str) -> bool:
    return (not path.strip() or path.startswith("/") or "\\" in path
            or ".." in path.split("/") or "" in path.split("/"))


@router.post("/files/zip")
def files_zip(req: ZipRequest) -> Response:
    """Pack the given project files (path = ProjectFile.id) into changed.zip."""
    if not req.files:
        raise HTTPException(422, "Нет файлов для архива")
    for f in req.files:
        if _unsafe(f.path):
            raise HTTPException(422, f"Недопустимый путь файла: {f.path!r}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in req.files:
            z.writestr(f.path, f.code)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="changed.zip"'})
