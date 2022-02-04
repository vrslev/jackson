import asyncer
import pytest

from tests.conftest import CustomClient, CustomServer, ExitQueue


async def wait_for_success(exit_queue: ExitQueue):
    server_ok = False
    client_ok = False

    while True:
        value = await exit_queue.get()
        if value == "server":
            server_ok = True
        else:
            client_ok = True

        if server_ok and client_ok:
            return 0


@pytest.mark.anyio
async def test_ok(server: CustomServer, client: CustomClient, exit_queue: ExitQueue):
    async with asyncer.create_task_group() as task_group:
        task_group.soonify(server.run)()
        task_group.soonify(client.run)(server)

        await wait_for_success(exit_queue)
        task_group.cancel_scope.cancel()


# class FlakyClient(CustomClient):
#     def __init__(
#         self,
#         settings: ClientSettings,
#         start_jack: bool,
#         exit_queue: ExitQueue,
#         connection_map_queue: ConnectionMapQueue,
#     ) -> None:
#         super().__init__(settings, start_jack, exit_queue, connection_map_queue)
#         self.should_exit = anyio.Event()

#     def patch_connect_ports_on_both_ends(self):
#         super().patch_connect_ports_on_both_ends()
#         assert self.port_connector

#         # pyright: reportPrivateUsage = false
#         prev_func = self.port_connector._connect_ports_on_both_ends

#         async def connect_ports_on_both_ends_override(connection: PortConnection):
#             await prev_func(connection)
#             self.should_exit.set()

#         self.port_connector._connect_ports_on_both_ends = (
#             connect_ports_on_both_ends_override
#         )

#     async def run(self, server: CustomServer):
#         try:
#             async with asyncer.create_task_group() as task_group:
#                 task_group.soonify(super().run)(server)
#                 while not self.should_exit.is_set():
#                     await anyio.sleep(0.00000001)

#                 # task_group.cancel_scope.cancel()
#         except RuntimeError:  # HTTPX complaining about unfinished requests
#             pass


# @pytest.mark.anyio
# async def test_flaky(
#     server: CustomServer,
#     client: CustomClient,
#     client_settings: ClientSettings,
#     exit_queue: ExitQueue,
#     connection_map_queue: ConnectionMapQueue,
# ):
#     flaky_client = FlakyClient(
#         client_settings,
#         start_jack=False,
#         exit_queue=exit_queue,
#         connection_map_queue=connection_map_queue,
#     )

#     async with asyncer.create_task_group() as task_group:
#         task_group.soonify(server.run)()
#         await flaky_client.run(server)

#         task_group.soonify(client.run)(server)

#         await wait_for_success(exit_queue)
#         task_group.cancel_scope.cancel()
