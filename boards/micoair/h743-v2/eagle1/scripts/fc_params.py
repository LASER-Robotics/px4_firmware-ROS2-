#!/usr/bin/env python3
"""Parametros del FC real por USB (MAVLink): respaldar, aplicar, restaurar.

    fc_params.py dump  [--dev /dev/ttyACM0] <salida.params>     todos los parametros (respaldo)
    fc_params.py apply [--dev /dev/ttyACM0] <a.params> [...]   solo escribe lo que difiere
    fc_params.py get   [--dev /dev/ttyACM0] NOMBRE [...]

Formato de archivo: `NOMBRE VALOR` por linea, `#` comenta (el mismo de config/*.params).
Restaurar = `apply` del respaldo. Los cambios de SYS_HITL / HIL_ACT_FUNC* piden reboot (`--reboot`).
⚠️ El puerto tiene que estar libre: cerrar QGC antes (y la planta en MODO=hil).
"""
import argparse
import struct
import sys
import time

from pymavlink import mavutil

_add = mavutil.add_message
def _add_seguro(messages, mtype, msg):   # pymavlink 2.4.49: _instances None si el primer mensaje del tipo no traia instancia (PX4 1.17)
    if mtype in messages and getattr(messages[mtype], "_instances", {}) is None:
        messages[mtype]._instances = {}
    try:
        _add(messages, mtype, msg)
    except TypeError:
        messages[mtype] = msg
mavutil.add_message = _add_seguro


def conectar(dev):
    m = mavutil.mavlink_connection(dev, baud=921600, source_system=254, source_component=190)
    if not m.wait_heartbeat(timeout=10):
        sys.exit(f"sin HEARTBEAT del FC en {dev}")
    return m


def leer_todo(m, timeout=30.0):
    m.mav.param_request_list_send(m.target_system, m.target_component)
    vals, total, t_ult = {}, None, time.time()
    while time.time() - t_ult < 3.0 and time.time() - t_ult < timeout:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1.0)
        if msg is None:
            if total is not None and len(vals) >= total:
                break
            continue
        vals[msg.param_id] = (msg.param_value, msg.param_type)
        total = msg.param_count
        t_ult = time.time()
    if total is None:
        sys.exit("el FC no mando parametros")
    # los que faltaron, de a uno
    if len(vals) < total:
        faltan = total - len(vals)
        print(f"aviso: faltan {faltan} de {total}; reintento por indice", file=sys.stderr)
        for i in range(total):
            m.mav.param_request_read_send(m.target_system, m.target_component, b"", i)
            msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
            if msg:
                vals[msg.param_id] = (msg.param_value, msg.param_type)
    return vals, total


def leer(m, nombre):
    for _ in range(3):
        m.mav.param_request_read_send(m.target_system, m.target_component, nombre.encode(), -1)
        t0 = time.time()
        while time.time() - t0 < 1.5:
            msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=0.5)
            if msg and msg.param_id == nombre:
                return msg.param_value, msg.param_type
    return None


# ⚠️ PX4 manda los INT32 codificados BYTE A BYTE dentro del float (PARAM_ENCODE_BYTEWISE): hay que reinterpretar
# los bits, no convertir. Leidos como float salen NaN o basura.
ENTEROS = (mavutil.mavlink.MAV_PARAM_TYPE_INT32, mavutil.mavlink.MAV_PARAM_TYPE_UINT32,
           mavutil.mavlink.MAV_PARAM_TYPE_INT16, mavutil.mavlink.MAV_PARAM_TYPE_INT8, mavutil.mavlink.MAV_PARAM_TYPE_UINT8)


def a_valor(v, t):
    return struct.unpack("<i", struct.pack("<f", v))[0] if t in ENTEROS else v


def a_float(x, t):
    return struct.unpack("<f", struct.pack("<i", int(round(x))))[0] if t in ENTEROS else float(x)


def fmt(v, t):
    x = a_valor(v, t)
    return str(x) if t in ENTEROS else f"{x:.7g}"


def cargar(rutas):
    out = []
    for r in rutas:
        for ln in open(r):
            ln = ln.split("#", 1)[0].strip()
            if ln:
                k, v = ln.split()[:2]
                out.append((k, float(v)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("orden", choices=["dump", "apply", "get"])
    ap.add_argument("args", nargs="+")
    ap.add_argument("--dev", default="/dev/ttyACM0")
    ap.add_argument("--reboot", action="store_true")
    a = ap.parse_args()
    m = conectar(a.dev)

    if a.orden == "dump":
        vals, total = leer_todo(m)
        with open(a.args[0], "w") as f:
            f.write(f"# respaldo del FC {a.dev}, {time.strftime('%Y-%m-%d %H:%M:%S')}, {len(vals)}/{total} parametros\n")
            for k in sorted(vals):
                f.write(f"{k} {fmt(*vals[k])}\n")
        print(f"{len(vals)}/{total} parametros -> {a.args[0]}")
        if len(vals) < total:
            sys.exit(1)

    elif a.orden == "get":
        for k in a.args:
            r = leer(m, k)
            print(f"{k} {fmt(*r) if r else '(no existe)'}")

    else:
        cambios = 0
        for k, v in cargar(a.args):
            r = leer(m, k)
            if r is None:
                print(f"  {k}: NO EXISTE en este firmware (se salta)")
                continue
            igual = lambda val: abs(a_valor(*val) - v) < 1e-6 * max(1.0, abs(v))
            if igual(r):
                continue
            m.mav.param_set_send(m.target_system, m.target_component, k.encode(), a_float(v, r[1]), r[1])
            time.sleep(0.05)
            nuevo = leer(m, k)
            ok = nuevo is not None and igual(nuevo)
            print(f"  {k}: {fmt(*r)} -> {fmt(*nuevo) if nuevo else '?'} {'OK' if ok else 'FALLO'}")
            cambios += 1
        print(f"{cambios} cambiados")
        if a.reboot:
            # 28/10: con 12 cambios el reboot llego antes de que PX4 grabara y el FC volvio con los valores viejos:
            # guardar explicito y esperar antes de reiniciar
            m.mav.command_long_send(m.target_system, m.target_component,
                                    mavutil.mavlink.MAV_CMD_PREFLIGHT_STORAGE, 0, 1, 0, 0, 0, 0, 0, 0)
            time.sleep(3)
            m.mav.command_long_send(m.target_system, m.target_component,
                                    mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 0, 0)
            print("reboot pedido")


if __name__ == "__main__":
    main()
