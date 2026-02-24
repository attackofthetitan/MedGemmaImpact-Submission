import os
import sys
import json
import httpx
from contextlib import asynccontextmanager
from fastapi import Request, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from linebot.v3.webhook import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    FollowEvent,
    JoinEvent,
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    FollowEvent,
    LeaveEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
)
from handler_function import handle_message, handle_image, handle_follow, handle_send_relpy, handle_send, handle_review
from linebot.v3 import WebhookHandler
from starlette.responses import FileResponse

import bind_controller
from config import config
from bot_controller import Bot_Controller
from auth_controller import Auth_Controller
from bind_controller import Bind_Controller

# class Controller:
#     def __init__(self):


@asynccontextmanager
async def lifespan(app: FastAPI):
    async_api_client: AsyncApiClient | None = None
    line_bot_api: AsyncMessagingApi | None = None
    configuration = Configuration(access_token=config.line_bot.access_token)
    async_api_client = AsyncApiClient(configuration)
    app.state.linebot = {
        "parser": WebhookParser(config.line_bot.secret),
        "line_bot_api": AsyncMessagingApi(async_api_client),
    }
    http_client = httpx.AsyncClient(base_url=config.agent.base_url, timeout=180.0)
    app.state.client = http_client
    app.state.controller = Bot_Controller(
        agent=config.agent,
        client=http_client,
    )
    app.state.auth_controller = Auth_Controller(
        auth_manager=config.auth_manager,
        client=http_client,
    )
    app.state.bind_controller = Bind_Controller(client=http_client)
    await app.state.auth_controller.login()
    await app.state.controller.health_check()
    print("configured line bot api")
    yield
    await async_api_client.close()
    await http_client.aclose()
    print("Shutting down...")


app = FastAPI(
    title="Clinical Agent Bot",
    version="0.0.1",
    lifespan=lifespan,
)


# router = APIRouter(prefix="/v1/bot", tags=["line"])
@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers["X-Line-Signature"]
    body = await request.body()
    body = body.decode()
    print(f"received: {json.dumps(body)}")

    try:
        # asyncio.create_task(handler.handle(body, signature))
        events = request.app.state.linebot["parser"].parse(body, signature)
    except InvalidSignatureError:
        print("400")
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        match event:
            case MessageEvent(message=TextMessageContent()):
                await handle_message(
                    event,
                    auth_controller=request.app.state.auth_controller,
                    controller=request.app.state.controller,
                    line_bot_api=request.app.state.linebot["line_bot_api"],
                    bind_controller=request.app.state.bind_controller,
                )
            case MessageEvent(message=ImageMessageContent()):
                await handle_image(
                    event, line_bot_api=request.app.state.linebot["line_bot_api"]
                )
            case FollowEvent():
                await handle_follow(
                    event, line_bot_api=request.app.state.linebot["line_bot_api"]
                )
            case _:
                continue
    return "OK"

try:
    from dashboard_server import router as dashboard_router

    app.include_router(dashboard_router)
except ImportError:
    pass

app.mount("/dashboard", StaticFiles(directory="./dashboard/out"), name="frontend")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8888)
