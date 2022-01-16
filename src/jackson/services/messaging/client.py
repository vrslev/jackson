import httpx

# from jackson.services.messaging.models import InitResponse


# class MessagingClient:
#     def __init__(self, base_url: str) -> None:
#         self.client = httpx.Client(base_url=base_url)

#     def init(self):
#         response = self.client.get("/init")
#         return InitResponse(**response.json())


client = httpx.Client()


def init():
    ...


async def connect(source: str, destination: str):
    ...
