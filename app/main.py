import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from icecream import ic
from proton import Event
from proton.handlers import IOHandler, MessagingHandler
from proton.reactor import Container
from pydantic import BaseModel, NonNegativeInt, field_validator


class AsyncioLoopHandler:
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.reactor: Container | None = None
        self._fds: dict[int, tuple] = {}

    def on_reactor_init(self, event):
        self.reactor = event.reactor

    def on_reactor_quiesced(self, event):
        pass

    def on_unhandled(self, name, event):
        event.dispatch(IOHandler())

    def _make_reader(self, sel):
        def _on_read():
            sel.readable()
            self._pump()

        return _on_read

    def _make_writer(self, sel):
        def _on_write():
            sel.writable()
            self._pump()

        return _on_write

    def _make_timer(self, sel):
        def _on_timer():
            sel.expired()
            self._pump()

        return _on_timer

    def _reg(self, sel):
        fd = sel.fileno()
        if fd < 0:
            return
        self._unreg(fd)
        reader = writer = timer = None
        if sel.reading:
            reader = self._make_reader(sel)
            self.loop.add_reader(fd, reader)
        if sel.writing:
            writer = self._make_writer(sel)
            self.loop.add_writer(fd, writer)
        if sel.deadline:
            timer = self.loop.call_at(sel.deadline, self._make_timer(sel))
        self._fds[fd] = (reader, writer, timer)

    def _unreg(self, fd):
        if fd not in self._fds:
            return
        r, w, t = self._fds.pop(fd)
        if r:
            self.loop.remove_reader(fd)
        if w:
            self.loop.remove_writer(fd)
        if t:
            t.cancel()

    def on_selectable_init(self, event):
        self._reg(event.context)

    def on_selectable_updated(self, event):
        self._reg(event.context)

    def on_selectable_final(self, event):
        self._unreg(event.context.fileno())

    def _pump(self):
        if self.reactor is not None:
            self.reactor.process()


class E1CMessage(BaseModel):
    id: UUID
    durable: bool
    priority: NonNegativeInt
    properties: dict[str, str]
    body: str

    @field_validator("body", mode="before")
    def validate_memoryview(cls, v) -> str:
        return bytes(v).decode()


class BrokerHandler(MessagingHandler):
    def on_start(self, event: Event):
        event.container.listen("0.0.0.0:6698")

    def on_message(self, event: Event):
        asyncio.get_running_loop().create_task(
            self.event(E1CMessage.model_validate(event.message, from_attributes=True))
        )

    @staticmethod
    async def event(msg: E1CMessage):
        ic(msg.model_dump())


@asynccontextmanager
async def lifespan(app: FastAPI):
    amqp = Container(BrokerHandler(), global_handler=AsyncioLoopHandler())
    amqp.start()
    amqp.process()

    try:
        yield {}
    finally:
        amqp.stop()


app = FastAPI(
    title="1C ESB Gateway",
    description="Compatible server for 1C Enterprise ESB integration (OIDC + AMQP)",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/auth/oidc/token")
async def token_endpoint():
    return {
        "id_token": None,
        "access_token": "Not implemented",
        "token_type": "Bearer",
    }


@app.get("/sys/esb/metadata/channels")
async def get_metadata():
    return [
        {
            "process": "pyesb",
            "processDescription": "DeadSnake.app",
            "channel": "outgoing",
            "channelDescription": "FlyAway",
            "access": "WRITE_ONLY",
        }
    ]


@app.get("/sys/esb/runtime/channels")
async def get_runtime():
    return {
        "items": [
            {"process": "pyesb", "channel": "outgoing", "destination": "queue"},
        ],
        "port": 6698,
    }
