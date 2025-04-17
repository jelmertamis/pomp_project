import time
import threading
import argparse
from flask import Flask, render_template, request, redirect, url_for, jsonify

# — GPIO‑fallback voor lokaal testen —
try:
    import RPi.GPIO as GPIO  # type: ignore
except ImportError:
    class DummyGPIO:
        BCM = "BCM"; OUT = "OUT"; HIGH = 1; LOW = 0
        @staticmethod
        def setmode(m):    print(f"[DummyGPIO] setmode({m})")
        @staticmethod
        def setwarnings(f): pass
        @staticmethod
        def setup(p, m):   print(f"[DummyGPIO] setup(pin={p}, mode={m})")
        @staticmethod
        def output(p, v):  print(f"[DummyGPIO] output(pin={p}, value={v})")
        @staticmethod
        def cleanup():     print("[DummyGPIO] cleanup()")
    GPIO = DummyGPIO

# — Flask en GPIO init —
app = Flask(__name__)
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
RELAIS_PIN = 17
GPIO.setup(RELAIS_PIN, GPIO.OUT)
GPIO.output(RELAIS_PIN, GPIO.HIGH)  # start uit

# — Globale variabelen & synchronisatie —
lock = threading.Lock()
reset_event = threading.Event()

pulse_time = 79.0
pause_time = 359.0
completed_cycles = 0
state_elapsed = 0.0
pump_status = "Uit"
current_phase_duration = 0.0

# — Achtergrondthread voor pomp‐besturing —
def pump_control():
    global state_elapsed, pump_status, completed_cycles, current_phase_duration
    while True:
        # — AAN‑fase —
        GPIO.output(RELAIS_PIN, GPIO.LOW)
        with lock:
            pump_status = "Aan"
            current_phase_duration = pulse_time
        start_time = time.time()

        while True:
            if reset_event.is_set():
                # reset mid-fase
                with lock:
                    state_elapsed = 0.0
                    current_phase_duration = pulse_time
                start_time = time.time()
                reset_event.clear()

            elapsed = time.time() - start_time
            with lock:
                state_elapsed = elapsed
                current_phase_duration = pulse_time
            if elapsed >= pulse_time:
                break
            time.sleep(0.1)

        # — UIT‑fase —
        GPIO.output(RELAIS_PIN, GPIO.HIGH)
        with lock:
            pump_status = "Uit"
            current_phase_duration = pause_time
        start_time = time.time()

        while True:
            if reset_event.is_set():
                with lock:
                    state_elapsed = 0.0
                    current_phase_duration = pause_time
                start_time = time.time()
                reset_event.clear()

            elapsed = time.time() - start_time
            with lock:
                state_elapsed = elapsed
                current_phase_duration = pause_time
            if elapsed >= pause_time:
                break
            time.sleep(0.1)

        with lock:
            completed_cycles += 1

# start de pump_control-thread
threading.Thread(target=pump_control, daemon=True).start()


# — Webroutes —  
@app.route('/', methods=['GET', 'POST'])
def index():
    global pulse_time, pause_time
    if request.method == 'POST':
        try:
            with lock:
                pulse_time = float(request.form['pulse'])
                pause_time = float(request.form['pause'])
        except (ValueError, KeyError):
            pass
        return redirect(url_for('index'))

    with lock:
        ctx = {
            'pulse': int(pulse_time),
            'pause': int(pause_time),
            'cycles': completed_cycles,
            'status': pump_status,
            'elapsed': int(state_elapsed),
            'duration': int(current_phase_duration)
        }
    return render_template('index.html', **ctx)

@app.route('/status')
def status():
    with lock:
        return jsonify({
            'pulse':    int(pulse_time),            # setpoint puls
            'pause':    int(pause_time),            # setpoint pauze
            'cycles':   completed_cycles,
            'status':   pump_status,
            'elapsed':  int(state_elapsed),
            'duration': int(current_phase_duration)
        })

@app.route('/reset', methods=['POST'])
def reset():
    global completed_cycles
    with lock:
        completed_cycles = 0
    reset_event.set()
    return ('', 204)  # No Content

# — Applicatie starten —  
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pomp Controller')
    parser.add_argument('--debug', action='store_true',
                        help='Debug + auto‑reload voor lokale tests')
    args = parser.parse_args()

    try:
        app.run(host='0.0.0.0',
                port=5000,
                debug=args.debug,
                use_reloader=args.debug)
    finally:
        GPIO.cleanup()
