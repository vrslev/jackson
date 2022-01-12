from jackson.utils import Program


async def start(*, sync: bool = True, backend: str, device: str, rate: int = 48000):
    cmd: list[str] = ["jackd"]
    if sync:
        cmd.append("--sync")
    cmd += ("-d", backend, "--device", device, "--rate", str(rate))

    await Program(cmd).run_forever()
