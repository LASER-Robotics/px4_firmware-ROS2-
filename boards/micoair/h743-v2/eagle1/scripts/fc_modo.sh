#!/usr/bin/env bash
# Pone el FC real (MicoAir H743, por USB) en un MODO definido por archivo, siempre igual, y lo verifica (desde el HOST).
#
#   fc_modo.sh estado        lee los parametros de los modos y dice en cual esta el FC (solo lectura)
#   fc_modo.sh hil           HIL volando con la RADIO real   -> config/fc/hil_real_livox.params
#                            (apaga el MTF-02P real: en HIL el flujo optico y el telemetro los simula la planta)
#   fc_modo.sh hil_sticks    HIL con los sticks de un log     -> config/fc/hil_real_livox_sticks.params (reproducir_hil.sh)
#   fc_modo.sh real          vuelo real                       -> config/fc/modo_vuelo_real.params
#
# Cada cambio de modo: 1) respaldo completo del FC en ~/flight_logs/mujoco_px4/fc_respaldos/  2) escribe solo lo que
# difiere (fc_params.py apply) y reinicia el FC  3) repite si faltaron parametros (los HIL_ACT_FUNC* recien existen tras
# reiniciar con SYS_HITL 1)  4) VERIFICA parametro por parametro contra el archivo y termina con OK o FALLA.
# Los VALORES viven en los .params (metodo), no en este script: si cambia algo del modo, se cambia el archivo.
# Requisitos: FC por USB, QGC cerrado y la planta parada (el puerto tiene que estar libre). En los modos HIL: HELICES FUERA.
set -uo pipefail
D="$(cd "$(dirname "$(realpath "$0")")/.." && pwd)"
FC="$D/config/fc"; PY="python3 $D/scripts/fc_params.py"
DEV=${FC_DEV:-/dev/ttyACM0}
RESP="$HOME/flight_logs/mujoco_px4/fc_respaldos"
declare -A ARCH=([hil]="$FC/hil_real_livox.params" [hil_sticks]="$FC/hil_real_livox_sticks.params" [real]="$FC/modo_vuelo_real.params")
MODO=${1:-}

parametros() { grep -v '^\s*#' "$1" | awk 'NF>=2{print $1}'; }
valor()      { grep -v '^\s*#' "$1" | awk -v k="$2" '$1==k{print $2}'; }

esperar_fc() {   # tras el reboot el USB desaparece y vuelve
  sleep 4
  for _ in $(seq 1 30); do [ -e "$DEV" ] && { sleep 3; return 0; }; sleep 1; done
  echo "✗ el FC no volvio en $DEV"; return 1
}

puerto_libre() {
  [ -e "$DEV" ] || { echo "✗ no veo el FC en $DEV"; exit 1; }
  if fuser "$DEV" >/dev/null 2>&1; then echo "✗ $DEV esta en uso (QGC o la planta): cerrarlos primero"; exit 1; fi
}

# compara el FC con un archivo; imprime las diferencias y devuelve el numero de diferencias
comparar() {
  local f=$1 dif=0 lect
  lect=$($PY get --dev "$DEV" $(parametros "$f") 2>/dev/null)
  for k in $(parametros "$f"); do
    local esp act
    esp=$(valor "$f" "$k"); act=$(echo "$lect" | awk -v k="$k" '$1==k{print $2}')
    if [ "$act" = "(no" ] || [ -z "$act" ]; then
      echo "  $k: no existe (esperado $esp)"; dif=$((dif + 1)); continue
    fi
    if ! python3 -c "import sys; a,b=float(sys.argv[1]),float(sys.argv[2]); sys.exit(0 if abs(a-b)<=1e-5*max(1,abs(b)) else 1)" "$act" "$esp"; then
      echo "  $k: FC $act, esperado $esp"; dif=$((dif + 1))
    fi
  done
  return $dif
}

# Al volver a 'real': TODOS los parametros contra el ultimo respaldo tomado en modo real (SYS_HITL 0). PX4 cambia solo
# algunos parametros durante el HIL (12/11: GPS_1_CONFIG, CAL_ACC2/GYRO2_ID); si aparece uno nuevo, se lista aca y se
# agrega a modo_vuelo_real.params. Los contadores de vuelo no cuentan.
control_completo() {
  local ref; ref=$(grep -l "^SYS_HITL 0$" $(ls -t "$RESP"/fc_*.params 2>/dev/null | grep -vx "$B") 2>/dev/null | head -1)   # sin el de esta corrida
  [ -n "$ref" ] || { echo "(control completo: no hay un respaldo previo en modo real para comparar)"; return; }
  local ahora="$RESP/fc_$(date +%Y%m%d_%H%M%S)_real_control.params"; sleep 5
  $PY dump --dev "$DEV" "$ahora" >/dev/null || { echo "(control completo: no pude leer el FC)"; return; }
  python3 - "$ref" "$ahora" <<'PYEOF'
import sys
def leer(f):
    d = {}
    for l in open(f):
        if l.startswith('#') or not l.strip(): continue
        k, v = l.split()[:2]; d[k] = v
    return d
ign = {'_HASH_CHECK', 'COM_FLIGHT_UUID', 'LND_FLIGHT_T_LO', 'LND_FLIGHT_T_HI'}
a, b = leer(sys.argv[1]), leer(sys.argv[2])
dif = [k for k in a if k in b and k not in ign and abs(float(a[k]) - float(b[k])) > 1e-5 * max(1, abs(float(a[k])))]
falta = [k for k in a if k not in b and k not in ign]; sobra = [k for k in b if k not in a and k not in ign]
print(f"control completo contra {sys.argv[1].split('/')[-1]}:")
if not (dif or falta or sobra):
    print("  ✓ todos los parametros iguales (salvo los contadores de vuelo)")
else:
    for k in dif: print(f"  ⚠ {k}: antes {a[k]}, ahora {b[k]}")
    if falta: print(f"  ⚠ faltan: {' '.join(falta)}")
    if sobra: print(f"  ⚠ nuevos: {' '.join(sobra)}")
    print("  -> si es un efecto del HIL, agregar el valor de 'antes' a config/fc/modo_vuelo_real.params")
PYEOF
}

case "$MODO" in
  estado)
    puerto_libre
    for m in real hil hil_sticks; do
      if comparar "${ARCH[$m]}" >/dev/null; then echo "FC en modo: $m"; exit 0; fi
    done
    echo "FC en un estado que no coincide con ningun modo. Diferencias con 'real':"; comparar "${ARCH[real]}"; exit 1 ;;
  hil|hil_sticks|real)
    puerto_libre
    F=${ARCH[$MODO]}
    [ "$MODO" != real ] && echo "⚠️  modo $MODO: HELICES FUERA. Con hil_sticks el FC ignora la radio real (KILL incluido)."
    mkdir -p "$RESP"; B="$RESP/fc_$(date +%Y%m%d_%H%M%S)_antes_de_$MODO.params"
    $PY dump --dev "$DEV" "$B" || { echo "✗ no pude respaldar: no cambio nada"; exit 1; }
    echo "respaldo: $B"
    for intento in 1 2 3; do
      if comparar "$F" >/dev/null; then
        echo "✓ FC en modo $MODO (verificado contra $(basename "$F"))"
        [ "$MODO" = real ] && control_completo
        exit 0
      fi
      echo "pasada $intento: aplico $(basename "$F") y reinicio"
      $PY apply --dev "$DEV" --reboot "$F" || true
      esperar_fc || exit 1
    done
    echo "✗ FALLA: el FC no quedo en modo $MODO. Diferencias:"; comparar "$F"
    echo "Para volver al estado anterior: $PY apply --dev $DEV --reboot $B"; exit 1 ;;
  *)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
