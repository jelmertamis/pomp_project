# pomp_project2.py
import time
import threading
import argparse
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, jsonify

DB_PATH = 'settings.db'
DEFAULT_PULSE = 79.0
DEFAULT_PAUSE = 359.0

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

# — Flask & GPIO init —
app = Flask(__name__)
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
RELAIS_PIN = 17
GPIO.setup(RELAIS_PIN, GPIO.OUT)
GPIO.output(RELAIS_PIN, GPIO.HIGH)

# — SQLite setup —  
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value REAL
    )
''')
conn.commit()

def load_setting(key: str, default: float) -> float:
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    return float(row[0]) if row else default

def save_setting(key: str, value: float):
    c.execute('''
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    ''', (key, value))
    conn.commit()

# — Globale variabelen & synchronisatie —
lock = threading.Lock()
reset_event = threading.Event()

pulse_time = load_setting('pulse', DEFAULT_PULSE)
pause_time = load_setting('pause', DEFAULT_PAUSE)
completed_cycles = 0
state_elapsed = 0.0
pump_status = "Uit"
current_phase_duration = 0.0

# — Achtergrondthread voor pomp‑besturing —
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

# Start de pump_control-thread
threading.Thread(target=pump_control, daemon=True).start()


# — Webroutes —  
@app.route('/', methods=['GET', 'POST'])
def index():
    global pulse_time, pause_time
    if request.method == 'POST':
        try:
            new_p = float(request.form['pulse'])
            new_z = float(request.form['pause'])
            with lock:
                pulse_time = new_p
                pause_time = new_z
            # meteen opslaan in de DB
            save_setting('pulse', pulse_time)
            save_setting('pause', pause_time)
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
            'pulse':    int(pulse_time),
            'pause':    int(pause_time),
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
    return ('', 204)

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
        conn.close()
