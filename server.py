import contextlib
import os

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.responses import PlainTextResponse

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from database import init_db
from mcp_ import server

load_dotenv()

# Stateless + json_response — robust behind a proxy like Railway
session_manager = StreamableHTTPSessionManager(
    app=server,
    event_store=None,
    json_response=True,
    stateless=True,
)


async def handle_mcp(scope, receive, send):
    await session_manager.handle_request(scope, receive, send)


async def health(request):
    return PlainTextResponse("ok")


@contextlib.asynccontextmanager
async def lifespan(app):
    init_db()
    async with session_manager.run():
        yield


app = Starlette(
    routes=[
        Route("/health", health),
        Mount("/", app=handle_mcp),
    ],
    lifespan=lifespan,
)