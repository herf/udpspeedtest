#!/usr/bin/env python3
"""Send-only UDP speed test: blast the default gateway, report every 1s, summarize after 30s."""
import argparse, errno, socket, subprocess, sys, time, platform

PORT = 9  # discard port
DURATION = 30

def default_gateway():
    s = platform.system()
    try:
        if s == "Linux":
            out = subprocess.check_output(["ip", "route"], text=True)
            for line in out.splitlines():
                if line.startswith("default"):
                    return line.split()[2]
        elif s == "Darwin":
            out = subprocess.check_output(["route", "-n", "get", "default"], text=True)
            for line in out.splitlines():
                if "gateway:" in line:
                    return line.split()[-1]
        elif s == "Windows":
            out = subprocess.check_output(["ipconfig"], text=True, errors="ignore")
            for line in out.splitlines():
                if "Default Gateway" in line:
                    gw = line.split(":")[-1].strip()
                    if gw and gw[0].isdigit():
                        return gw
    except Exception as e:
        print(f"gateway autodetect failed: {e}", file=sys.stderr)
    return None

def default_iface():
    try:
        out = subprocess.check_output(["route", "-n", "get", "default"], text=True)
        for line in out.splitlines():
            if "interface:" in line:
                return line.split()[-1]
    except Exception:
        pass
    return None

def nic_counters(iface):
    """(Opkts, Obytes) from the <Link row for iface on macOS, else None."""
    try:
        out = subprocess.check_output(["netstat", "-ib"], text=True)
    except Exception:
        return None
    for line in out.splitlines():
        f = line.split()
        if len(f) > 9 and f[0] == iface and f[2].startswith("<Link"):
            return int(f[7]), int(f[9])  # Opkts, Obytes
    return None

def main():
    ap = argparse.ArgumentParser(description="Send-only UDP speed test.")
    ap.add_argument("gateway", nargs="?", help="target (default: auto-detect gateway)")
    ap.add_argument("-s", "--size", type=int, default=1472,
                    help="payload bytes; 1472 = max unfragmented on 1500 MTU, 0 = max pkt/s (default: 1472)")
    ap.add_argument("-i", "--iface", help="macOS: interface for NIC-counter readout (default: auto)")
    args = ap.parse_args()

    gw = args.gateway or default_gateway()
    if not gw:
        sys.exit("Could not find default gateway; pass it as an argument.")
    payload = b"\x00" * args.size
    wire = args.size + 28  # + 20 IP + 8 UDP headers
    dst = (gw, PORT)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mac = platform.system() == "Darwin"
    if mac:
        sock.setblocking(False)  # macOS won't block on full TX; surface ENOBUFS/EAGAIN instead
    iface = (args.iface or default_iface()) if mac else None
    nic0 = nic_counters(iface) if iface else None
    print(f"Blasting {gw}:{PORT}  {args.size}B/pkt  for {DURATION}s"
          f"{'  [macOS: counting drops]' if mac else ''}"
          f"{f'  [NIC {iface}]' if nic0 else ''}\n")

    start = time.monotonic()
    tick = start
    total_pkts = total_bytes = total_drops = 0
    win_pkts = win_bytes = win_drops = 0

    while True:
        now = time.monotonic()
        if now - start >= DURATION:
            break
        try:
            sock.sendto(payload, dst)
            win_pkts += 1
            win_bytes += wire
        except BlockingIOError:              # EAGAIN/EWOULDBLOCK
            win_drops += 1
        except OSError as e:
            if e.errno == errno.ENOBUFS:     # TX backpressure (well-behaved driver)
                win_drops += 1
            else:
                raise

        if now - tick >= 1.0:
            dt = now - tick
            total_pkts += win_pkts
            total_bytes += win_bytes
            total_drops += win_drops
            drop_str = f"  {win_drops/dt:>9,.0f} drop/s" if mac else ""
            print(f"[{now-start:4.0f}s] {win_pkts/dt:>10,.0f} pkt/s  "
                  f"{win_bytes*8/dt/1e6:>8.1f} Mbit/s L3{drop_str}")
            win_pkts = win_bytes = win_drops = 0
            tick = now

    total_pkts += win_pkts
    total_bytes += win_bytes
    total_drops += win_drops
    elapsed = time.monotonic() - start
    print(f"\n--- {gw} stats ---")
    print(f"packets sent : {total_pkts:,}")
    if mac:
        attempts = total_pkts + total_drops
        pct = 100 * total_drops / attempts if attempts else 0
        print(f"drops        : {total_drops:,} of {attempts:,} attempts ({pct:.1f}%)")
    print(f"L3 bytes     : {total_bytes:,} ({total_bytes/1e6:.1f} MB, incl. 28B/pkt IP+UDP hdr)")
    print(f"avg rate     : {total_pkts/elapsed:,.0f} pkt/s, "
          f"{total_bytes*8/elapsed/1e6:.1f} Mbit/s L3 over {elapsed:.1f}s")
    if nic0:
        nic1 = nic_counters(iface)
        if nic1:
            dp, db = nic1[0] - nic0[0], nic1[1] - nic0[1]
            print(f"NIC {iface:<8}: {dp:,} pkt, {db:,} B egressed "
                  f"({db*8/elapsed/1e6:.1f} Mbit/s incl. L2, all traffic) <- ground truth")

if __name__ == "__main__":
    main()
