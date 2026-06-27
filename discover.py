#!/usr/bin/env python3
"""Find Kid PC Monitor agents on the local network.

A small convenience for the parent: scan the local /24 subnet for hosts serving
the agent's status API, then print each one's URL so you can bookmark it. Unlike
the old design, this is not part of the running system — it's a one-off helper.
Once you know a kid PC's address you just open ``http://<ip>:<port>`` directly.

Usage:
    python discover.py            # scan using the default/config port
    python discover.py --port N   # scan a specific port
"""
import argparse
import concurrent.futures
import json
import socket
import urllib.request

from kidmon import config


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def probe(ip, port, timeout=0.6):
    """Return the status dict if ip:port serves the agent API, else None."""
    url = f"http://{ip}:{port}/api/status"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            if "monitored" in data:  # looks like our agent
                return data
    except Exception:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description="Find Kid PC Monitor agents.")
    parser.add_argument("--port", type=int, default=config.get_web_port(),
                        help="agent web port to probe (default: from config)")
    args = parser.parse_args()

    base = ".".join(local_ip().split(".")[:3])
    print(f"Scanning {base}.0/24 on port {args.port}…")

    found = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        futures = {pool.submit(probe, f"{base}.{i}", args.port): i
                   for i in range(1, 255)}
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            data = fut.result()
            if data:
                ip = f"{base}.{i}"
                found.append((ip, data))

    if not found:
        print("No agents found.")
        return
    print(f"\nFound {len(found)} agent(s):")
    for ip, data in sorted(found):
        user = data.get("user", "?")
        print(f"  http://{ip}:{args.port}   ({user})")


if __name__ == "__main__":
    main()
