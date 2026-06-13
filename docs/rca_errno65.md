# Root Cause Analysis: LocalSend Multicast `[Errno 65] No route to host`

## Issue Summary
During the pipeline's transition to the `RELAYED_TO_PHONE` state, the `LocalSendService` violently crashed with `OSError: [Errno 65] No route to host`. This crash cascaded up to `bulk_post.py`, failing the entire cycle for the current reel and preventing the fallback logic (Firebase Storage) from executing.

## Environment
- **OS**: macOS (Darwin Kernel)
- **Component**: `src/utils/localsend_service.py`
- **Protocol**: UDP Multicast (IGMP), IPv4 (`224.0.0.167`)

## Root Cause
The `LocalSendService` uses UDP Multicast to automatically discover devices on the local network that are running the LocalSend app. To send or receive multicast packets, the Python socket must join a multicast group using the `setsockopt` system call:

```python
mreq = struct.pack("4sl", socket.inet_aton(self.MULTICAST_GROUP), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
```

macOS networking is strictly governed by its routing table (`netstat -nr`). If the macOS routing table does not possess an explicit default route for the `224.0.0.0/4` multicast subnet, the kernel does not know which physical network interface (e.g., `en0` for Wi-Fi) to bind the IGMP request to. 

Because it cannot resolve an interface for the multicast route, the macOS kernel immediately rejects the `setsockopt` system call with a POSIX `EHOSTUNREACH` error. Python surfaces this as `[Errno 65] No route to host`. 

Since this system call was not wrapped in an exception handler, the error bubbled up and crashed the pipeline.

## Resolution
The fix was to wrap the entire multicast configuration and transmission block inside a `try/except` block targeting `OSError`.

### Applied Fix
```python
        try:
            mreq = struct.pack("4sl", socket.inet_aton(self.MULTICAST_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    
            announce = json.dumps({...}).encode()
            sock.sendto(announce, (self.MULTICAST_GROUP, port))
        except OSError as e:
            logger.error(f"Multicast configuration/send failed: {e}. Network might not support UDP multicast.")
            sock.close()
            return None
```

### Impact
By intercepting the `[Errno 65]`, the `LocalSendService.discover()` method now gracefully returns `None`. 
The `push()` method cleanly handles this `None` return by falling back to the explicitly configured Unicast IP address (`LOCALSEND_TARGET_IP` from `.env`).

If the Unicast IP also fails (e.g., the target device is disconnected from Wi-Fi), the script now cleanly triggers the `FirebaseRelayService` progressive streaming fallback without crashing the pipeline daemon.
