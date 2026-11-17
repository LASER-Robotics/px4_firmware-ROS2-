#!/usr/bin/env python3
"""Monitor de la radio: muestra en vivo los 16 canales que ve el FC y marca el que se movio.

    rc_monitor.py                       por el reenvio de la planta HIL (udp 14550, QGC cerrado)
    rc_monitor.py /dev/ttyACM0          directo al FC por USB (sin planta)

Mover un switch o stick por vez: la linea "MOVIO" dice que canal es y entre que valores anda.
"""
import sys
import time

from pymavlink import mavutil

dev = sys.argv[1] if len(sys.argv) > 1 else "udpin:0.0.0.0:14550"
m = mavutil.mavlink_connection(dev, baud=921600, source_system=254)
m.wait_heartbeat(timeout=10)
m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, 20, 1)
ant = None
rango = {}
t_aviso = 0.0
while True:
    x = m.recv_match(type="RC_CHANNELS", blocking=True, timeout=2)
    if x is None:
        print("sin RC_CHANNELS...")
        continue
    v = [getattr(x, f"chan{i}_raw") for i in range(1, 17)]
    for i, c in enumerate(v):
        lo, hi = rango.get(i, (c, c))
        rango[i] = (min(lo, c), max(hi, c))
    if ant is not None:
        for i, (a, b) in enumerate(zip(ant, v)):
            if abs(a - b) > 150:
                lo, hi = rango[i]
                print(f"\n>>> MOVIO ch{i + 1}: {a} -> {b}   (rango visto {lo}..{hi})")
    ant = v
    if time.time() - t_aviso > 0.2:
        t_aviso = time.time()
        print("\r" + " ".join(f"{i + 1}:{c:4d}" for i, c in enumerate(v)), end="", flush=True)
