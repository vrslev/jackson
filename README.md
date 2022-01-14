# Jackson

A tool for audio networking.
It starts JACK server, JackTrip and Jack client that connects ports according to config.
There's too modes: server and client. Difference is that the first one starts JackTrip in server mode and second one — in client mode.
All configuration is done using config file. Example:

```yaml
server:
  remote_name: MacBook
  address: 192.168.0.12
  port: 4464
  backend: coreaudio
  device: BlackHole16ch_UID
  ports:
    system:capture_1: iMac:send_1
    iMac:receive_1: system:playback_1

client:
  remote_name: iMac
  port: 4464
  backend: coreaudio
  device: BlackHole16ch_UID
  ports:
    JackTrip:receive_1: system:playback_1
    system:capture_1: JackTrip:send_1
```
