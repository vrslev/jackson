from jackson.utils import run_forever


async def start(*, sync: bool = True, backend: str, device: str, rate: int = 48000):
    cmd: list[str] = ["jackd"]
    if sync:
        cmd.append("--sync")
    cmd += ("-d", backend, "--device", device, "--rate", str(rate))

    await run_forever(cmd)
