import re
from fastapi import APIRouter, HTTPException, params, Request, status
from fastapi.responses import StreamingResponse
from httpx import Response, stream, URL
from handler_function import handle_send_relpy

router = APIRouter(prefix="/dashboard/api", tags=["dashboard"])

@router.post("/v1/api/line/send")
async def send_line(request: Request,patient_id: str, session_id: str):
    res_status = await handle_send_relpy(
        session_id=session_id,
        input_id=patient_id,
        line_bot_api=request.app.state.linebot["line_bot_api"],
        controller=request.app.state.controller,
        auth_controller=request.app.state.auth_controller,
    )
    if res_status == "success":
        return {
            "message": "success"
        }
    else:
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="fail")


@router.post("/v1/line-binding/code")
async def bind_code(request: Request, force_regenerate: bool = False):
    res, status_code = await request.app.state.bind_controller.bind_start(
        request.headers, force_regenerate
    )
    if not res and status_code == 500:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authorized"
        )
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=(res or {}).get("detail"))
    return res


@router.post("/v1/line-binding/access/code")
async def bind_access_code(request: Request, force_regenerate: bool = False):
    res, status_code = await request.app.state.bind_controller.start_access_capture(
        request.headers, force_regenerate
    )
    if not res and status_code == 500:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authorized"
        )
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=(res or {}).get("detail"))
    return res


@router.get("/v1/line-binding/code/{binding_id}")
async def get_bind(request: Request, binding_id: str):
    res, status_code = await request.app.state.bind_controller.get_code(
        binding_id, request.headers
    )
    if status_code == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if status_code == 500:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=(res or {}).get("detail"))
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return res


@router.get("/v1/line-binding/access/code/{binding_id}")
async def get_bind_access(request: Request, binding_id: str):
    res, status_code = await request.app.state.bind_controller.get_access_capture(
        binding_id, request.headers
    )
    if status_code == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if status_code == 500:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=(res or {}).get("detail"))
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return res


@router.post("/v1/line-binding/code/{binding_id}/cancel")
async def cancel_bind(request: Request, binding_id: str):
    res, status_code = await request.app.state.bind_controller.cancel_code(
        binding_id, request.headers
    )
    if status_code == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if status_code == 500:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=(res or {}).get("detail"))
    return res


@router.post("/v1/line-binding/access/code/{binding_id}/cancel")
async def cancel_bind_access(request: Request, binding_id: str):
    res, status_code = await request.app.state.bind_controller.cancel_access_capture(
        binding_id, request.headers
    )
    if status_code == 401:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if status_code == 500:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if status_code != 200:
        raise HTTPException(status_code=status_code, detail=(res or {}).get("detail"))
    return res


@router.delete("/{path:path}")
@router.patch("/{path:path}")
@router.post("/{path:path}")
@router.get("/{path:path}")
async def proxy_get(request: Request, path: str):
    client = request.app.state.client
    print(f"path {path} query {request.url.query}")
    excluded_headers = ["host", "content-length", "connection", "keep-alive"]
    headers = {
        k: v for k, v in request.headers.items() if k.lower() not in excluded_headers
    }
    method = request.method
    body = await request.body()
    req = client.build_request(
        method, path, content=body, params=request.query_params, headers=headers
    )
    res = await client.send(req, stream=True)
    return StreamingResponse(
        res.aiter_raw(), status_code=res.status_code, headers=dict(res.headers)
    )
