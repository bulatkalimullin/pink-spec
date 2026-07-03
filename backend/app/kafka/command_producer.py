"""API-side command publisher."""

from __future__ import annotations

from app.kafka.config import kafka_settings
from app.kafka.producer import KafkaProducerClient
from app.kafka.schemas import SessionCommand


class CommandProducer:
    def __init__(self) -> None:
        self._client = KafkaProducerClient()

    async def start(self) -> None:
        await self._client.start()

    async def stop(self) -> None:
        await self._client.stop()

    async def publish(self, command: SessionCommand) -> None:
        cfg = kafka_settings()
        await self._client.send(
            cfg.commands_topic,
            key=command.session_id,
            value=command.to_json(),
        )

    async def health_check(self) -> dict:
        return await self._client.health_check()


command_producer = CommandProducer()
