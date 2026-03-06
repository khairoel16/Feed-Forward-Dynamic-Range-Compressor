#!/usr/bin/env python3
"""
DRC step-by-step (STREAMING + console params) — FULL FIXED (Q1.30)
MODIFIKASI: Menambahkan 4 Subplot Real-Time untuk Visualisasi.
Logika DRC Fixed-Point (Q1.30) tetap inline dan TIDAK BERUBAH.
"""

import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wavfile
import threading
import time
import os
import sys
import matplotlib.pyplot as plt
import queue
from tkinter import Tk
from tkinter.filedialog import askopenfilename

# --------------------------------
# FIXED-POINT CONFIGURATION
# --------------------------------
FIXED_BITS = 30
ONE = 1 << FIXED_BITS
ROUND_OFFSET = 1 << 14
MAX_INT16 = 32767
MIN_INT16 = -32768

# --------------------------------
# GLOBAL STREAMING CONFIG
# --------------------------------
BLOCKSIZE = 1024
fs = None
play_index = 0
processing = False
stop_flag = False

# BUFFER UNTUK PLOTTING
MAX_PLOT_SAMPLES = 48000
DOWNSAMPLE_PLOT = 10
input_buf_fixed = np.zeros(MAX_PLOT_SAMPLES, dtype=np.int32)
output_buf_fixed = np.zeros(MAX_PLOT_SAMPLES, dtype=np.int32)
envelope_buf_fixed = np.zeros(MAX_PLOT_SAMPLES, dtype=np.int32)
buf_ptr = 0
buf_lock = threading.Lock()
metrics_q = queue.Queue(maxsize=10)

# Parameters
params = {
    "threshold": "0.25",
    "ratio": "4",
    "attack": "0.995",
    "release": "0.9995",
    "makeup": "1.0"
}

# Parsed fixed-point parameter copies
T_fixed = 0
M_fixed = ONE
R_inv_fixed = ONE
alphaA_fixed = 0
alphaR_fixed = 0
one_minus_alphaA_fixed = 0
one_minus_alphaR_fixed = 0

# Persistent states (fixed)
envelope_state_fixed = np.int32(0)
g_prev_fixed = np.int32(ONE)

# --------------------------------
# LUT64 (Q1.30) — initial guess table for reciprocal NR
# --------------------------------
_LUT64 = [
    0x7FFFFFFF,0x7C000000,0x78000000,0x74000000,0x70000000,0x6C000000,0x68000000,0x64000000,
    0x60000000,0x5C000000,0x58000000,0x54000000,0x50000000,0x4C000000,0x48000000,0x44000000,
    0x42000000,0x40000000,0x3E000000,0x3C000000,0x3A000000,0x38000000,0x36000000,0x34000000,
    0x32000000,0x30000000,0x2E000000,0x2C000000,0x2A000000,0x28000000,0x26000000,0x24000000,
    0x22000000,0x20000000,0x1E000000,0x1C000000,0x1A000000,0x18000000,0x16000000,0x14000000,
    0x13000000,0x12000000,0x11000000,0x10000000,0x0F000000,0x0E000000,0x0D000000,0x0C000000,
    0x0B800000,0x0B000000,0x0A800000,0x0A000000,0x09800000,0x09000000,0x08800000,0x08000000,
    0x07800000,0x07000000,0x06800000,0x06000000,0x05800000,0x05000000,0x04800000,0x04000000
]

# --------------------------------
# Helper: Fixed-point -> float (HANYA UNTUK PLOTTING)
# --------------------------------

def fixed_to_float(fixed_val):
    is_scalar = isinstance(fixed_val, (int, np.int32, float))
    fixed_array = np.asarray(fixed_val, dtype=np.float64)
    result_float = fixed_array / float(ONE)
    if is_scalar and result_float.size == 1:
        return result_float.item()
    return result_float

def fixed_to_db(fixed_val):
    val_float = fixed_to_float(fixed_val)
    val = np.maximum(np.abs(val_float), 1e-12)
    return 20.0 * np.log10(val)

def parse_ratio_to_rinv_float(s):
    try:
        if '/' in s:
            n_str, d_str = s.split('/', 1)
            n = float(n_str.strip()); d = float(d_str.strip())
            if n == 0: return 1.0
            return d / n
        else:
            n = float(s)
            if n == 0: return 1.0
            return 1.0 / n
    except:
        return 1.0

# --------------------------------
# Helper: parse parameter string -> Q1.30
# --------------------------------
def parse_decimal_string_to_fixed_inline(s, q=FIXED_BITS):
    s = str(s).strip()
    if not s: return 0
    sign = 1
    if s[0] == '-':
        sign = -1; s = s[1:]
    if '/' in s:
        p_str, d_str = s.split('/', 1)
        p = int(p_str.strip()); d = int(d_str.strip())
        if d == 0: return 0
        return sign * ((p * (1 << q)) // d)
    if '.' in s:
        int_part, frac_part = s.split('.', 1)
        int_val = int(int_part) if int_part != '' else 0
        frac_str = frac_part.rstrip()
        if frac_str == '':
            frac_val = 0; denom = 1
        else:
            frac_val = int(frac_str); denom = 10 ** len(frac_str)
        fixed = (int_val << q) + ((frac_val * (1 << q)) // denom)
        return sign * int(fixed)
    v = int(s)
    return sign * (v << q)

# --------------------------------
# Update parsed fixed-point parameters from 'params' strings
# --------------------------------
def update_parsed_params_from_strings():
    global T_fixed, M_fixed, R_inv_fixed, alphaA_fixed, alphaR_fixed, one_minus_alphaA_fixed, one_minus_alphaR_fixed
    T_fixed = parse_decimal_string_to_fixed_inline(params['threshold'])
    M_fixed = parse_decimal_string_to_fixed_inline(params['makeup'])
    alphaA_fixed = parse_decimal_string_to_fixed_inline(params['attack'])
    alphaR_fixed = parse_decimal_string_to_fixed_inline(params['release'])
    one_minus_alphaA_fixed = ONE - alphaA_fixed
    one_minus_alphaR_fixed = ONE - alphaR_fixed
    s = str(params['ratio']).strip()
    if '/' in s:
        n_str, d_str = s.split('/', 1)
        n = int(n_str.strip()); d = int(d_str.strip())
        if n == 0: R_inv_fixed = ONE
        else: R_inv_fixed = (d << FIXED_BITS) // n
    else:
        n = int(s)
        if n == 0: R_inv_fixed = ONE
        else: R_inv_fixed = (1 << FIXED_BITS) // n

update_parsed_params_from_strings()

# --------------------------------
# audio data holder
# --------------------------------
audio_data_int32 = None

# ---------------------------------------------------
# Load WAV: From argv OR file explorer if none given
# ---------------------------------------------------

wav_path = None

def load_wav(path):
    """Load WAV file and convert to internal Q1.30 int32 array."""
    global audio_data_int32, fs
    try:
        fs_read, raw = wavfile.read(path)
        if raw.dtype == np.int16:
            data = raw.astype(np.int32) << 15
        elif raw.dtype == np.int32:
            data = raw.astype(np.int32)
        else:
            print("Input WAV unsupported (must be int16 or int32). Using silence.")
            return
        if data.ndim > 1:
            data = data.mean(axis=1).astype(np.int32)
        audio_data_int32 = data
        fs = fs_read
        print(f"Loaded WAV: {os.path.basename(path)} samples={len(data)} fs={fs}")
    except Exception as e:
        print("Failed loading WAV:", e)


if len(sys.argv) > 1:
    wav_path = sys.argv[1]
else:
    try:
        Tk().withdraw()
        wav_path = askopenfilename(title="Pilih file WAV", filetypes=[("WAV files", "*.wav")])
    except Exception as e:
        print("File dialog error:", e)
        wav_path = None

if wav_path and os.path.exists(wav_path):
    load_wav(wav_path)
else:
    print("WAV not selected or not found, streaming silence.")

if fs is None:
    fs = 48000

# --------------------------------
# Audio callback: contains inline DRC per-sample implementation
# --------------------------------

def audio_callback(outdata, frames, time_info, status):
    """Sounddevice callback: produce `frames` samples in outdata (int16)."""
    global play_index, audio_data_int32, processing, envelope_state_fixed, g_prev_fixed, buf_ptr
    
    if not processing:
        outdata[:] = 0
        return

    # --- prepare input block in Q1.30 ---
    if audio_data_int32 is None:
        block_fixed = np.zeros(frames, dtype=np.int32)
    else:
        end = play_index + frames
        if end <= len(audio_data_int32):
            block_fixed = audio_data_int32[play_index:end].copy()
            play_index = end
        else:
            valid = max(0, len(audio_data_int32) - play_index)
            block_fixed = np.zeros(frames, dtype=np.int32)
            if valid > 0:
                block_fixed[:valid] = audio_data_int32[play_index:play_index+valid]
            remaining = frames - valid
            if remaining > 0 and audio_data_int32 is not None:
                block_fixed[valid:] = audio_data_int32[:remaining]
                play_index = remaining
            else:
                play_index = end

    # snapshot parsed params
    Tfix = int(T_fixed)
    Mfix = int(M_fixed)
    Rinv = int(R_inv_fixed)
    aA = int(alphaA_fixed)
    aR = int(alphaR_fixed)
    oA = int(one_minus_alphaA_fixed)
    oR = int(one_minus_alphaR_fixed)

    # restore states
    env = int(envelope_state_fixed)
    gprev = int(g_prev_fixed)

    # Buffers sementara untuk data plotting
    out_block = np.empty(frames, dtype=np.int32)
    env_slice = np.empty(frames, dtype=np.int32)

    # --- per-sample processing ---
    for i in range(frames):
        # 0) load
        x_fixed = int(block_fixed[i])
        ax_fixed = x_fixed if x_fixed >= 0 else -x_fixed

        # 1) envelope follower (linear): env = alpha * env + (1-alpha) * |x|
        if ax_fixed > env:
            t1 = (aA * env) >> FIXED_BITS
            t2 = (oA * ax_fixed) >> FIXED_BITS
            env = t1 + t2
        else:
            t1 = (aR * env) >> FIXED_BITS
            t2 = (oR * ax_fixed) >> FIXED_BITS
            env = t1 + t2
        
        env_slice[i] = env # SIMPAN UNTUK PLOTTING

        # guard tiny/zero envelope (avoid divide-by-zero)
        if env <= 0:
            env = 1

        # 2) gain computer (hard-knee linear)
        if env <= Tfix:
            # below threshold: unity gain
            g_target = ONE
        else:
            # numerator: T + (env - T)/R -> compute in Q1.30
            diff = env - Tfix
            scaled = (diff * Rinv) >> FIXED_BITS
            num = Tfix + scaled

            # compute inv_env = 1 / env using LUT + NR
            x_val = env
            if x_val <= 0:
                inv_env = ONE
            else:
                xi = int(x_val)
                # leading-zero-count (LZC) for normalization (32-bit view)
                bl = xi.bit_length()
                lzc = 32 - bl if bl > 0 else 32
                if lzc < 0: lzc = 0
                if lzc > 31: lzc = 31

                # normalize: shift left to align MSBs
                x_norm = xi << lzc

                # LUT index: top 6 bits of x_norm (bits 31:26)
                lut_index = (x_norm >> 26) & 0x3F
                y = int(_LUT64[lut_index]) # initial guess (Q1.30)

                # Newton–Raphson iterations: y <- y * (2 - x_norm * y)
                # using Q1.30 arithmetic (all shifts >> FIXED_BITS)
                for _ in range(3):
                    xy = (x_norm * y) >> FIXED_BITS
                    term = (2 << FIXED_BITS) - xy
                    y = (y * term) >> FIXED_BITS

                # denormalize: x_norm = x << lzc => 1/x = (1/x_norm) << lzc
                inv_env = y << lzc

            # g_target = num * inv_env
            g_target = (num * inv_env) >> FIXED_BITS

        # 3) gain smoothing (attack/release on gain)
        if g_target < gprev:
            ta = aA; toa = oA
        else:
            ta = aR; toa = oR
        t1 = (ta * gprev) >> FIXED_BITS
        t2 = (toa * g_target) >> FIXED_BITS
        gprev = t1 + t2

        # 4) makeup
        gfinal = (gprev * Mfix) >> FIXED_BITS

        # 5) apply gain
        y = (x_fixed * gfinal) >> FIXED_BITS
        out_block[i] = np.int32(y)

    # persist states back to globals
    envelope_state_fixed = np.int32(env)
    g_prev_fixed = np.int32(gprev)

    # --- UPDATE PLOTTING BUFFERS ---
    L = len(out_block)
    with buf_lock:
        ptr = buf_ptr
        if ptr + L <= MAX_PLOT_SAMPLES:
            input_buf_fixed[ptr:ptr+L] = block_fixed
            output_buf_fixed[ptr:ptr+L] = out_block
            envelope_buf_fixed[ptr:ptr+L] = env_slice
            buf_ptr += L
            if buf_ptr >= MAX_PLOT_SAMPLES: buf_ptr = 0
        else:
            part1 = MAX_PLOT_SAMPLES - ptr
            input_buf_fixed[ptr:] = block_fixed[:part1]
            output_buf_fixed[ptr:] = out_block[:part1]
            envelope_buf_fixed[ptr:] = env_slice[:part1]
            
            input_buf_fixed[:L-part1] = block_fixed[part1:]
            output_buf_fixed[:L-part1] = out_block[part1:]
            envelope_buf_fixed[:L-part1] = env_slice[part1:]
            buf_ptr = (ptr + L) % MAX_PLOT_SAMPLES
    
    # Kirim metrik
    try:
        gr_db = max(0.0, -fixed_to_db(g_prev_fixed))
        env_db = fixed_to_db(envelope_state_fixed)
        metrics_q.put_nowait({
            "gain_reduction_db": gr_db,
            "env_input_db": env_db,
        })
    except queue.Full:
        pass
    
    # --- Konversi output ke int16 (Q0.15) ---
    rounded = out_block.astype(np.int64) + ROUND_OFFSET
    shifted = (rounded >> 15).astype(np.int32)
    shifted = np.clip(shifted, MIN_INT16, MAX_INT16).astype(np.int16)

    try:
        outdata[:] = shifted.reshape(-1, 1)
    except Exception:
        outdata[:, 0] = shifted

# --------------------------------
# Parameter input thread (console)
# --------------------------------

def parameter_input_thread():
    global processing, stop_flag, params
    print("======== DRC STREAMING CONTROL (INT-ONLY PARAMETERS) ========")
    print("T <val> -> Threshold linear (e.g. 0.25)")
    print("R <val> -> Ratio (e.g. 4 or 3/2)")
    print("A <val> -> Attack alpha per-sample (e.g. 0.995)")
    print("E <val> -> Release alpha per-sample (e.g. 0.9995)")
    print("M <val> -> Makeup linear (e.g. 1.0)")
    print("ENTER kosong untuk stop")
    print("=============================================================")

    while True:
        s = input().strip()
        if s == "":
            stop_flag = True
            processing = False
            break
        parts = s.split()
        if len(parts) < 2:
            print("Format salah. Contoh: 'R 4' atau 'R 3/2'")
            continue
        key = parts[0].upper()
        val = parts[1]
        if key == "T":
            params['threshold'] = val
        elif key == "R":
            params['ratio'] = val
        elif key == "A":
            params['attack'] = val
        elif key == "E":
            params['release'] = val
        elif key == "M":
            params['makeup'] = val
        else:
            print("Key tidak dikenal.")
            continue

        print("Updated (strings):", params)
        update_parsed_params_from_strings()

# --------------------------------
# Plot Loop (4 Grafik)
# --------------------------------
def run_plot_loop():
    plt.ion()
    fig = plt.figure(figsize=(14, 12)) 

    # --- SETUP SUBPLOTS ---
    ax1 = fig.add_subplot(4,1,1) # Waveform Linier
    ax2 = fig.add_subplot(4,1,2) # Dynamic Gain Curve (dB)
    ax3 = fig.add_subplot(4,1,3) # Envelope Follower Linier
    ax4 = fig.add_subplot(4,1,4) # Level History (Input/Output Peak dB)
    
    # --- 1. Waveform (Linier) ---
    line_in, = ax1.plot([],[],color="gold", label="Input")
    line_out, = ax1.plot([],[],color="red", label="Output")
    ax1.set_title("1. Input & Output Waveform (Linier)")
    ax1.set_ylim(-1.05,1.05)
    ax1.set_ylabel("Amplitude (Linier)")
    ax1.legend(loc="upper left") 
    gr_text = ax1.text(0.99, 0.95, '', transform=ax1.transAxes, ha='right', va='top', bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))
    
    # --- 2. Static curve (dB) ---
    ax2.set_title("2. Dynamic Gain Curve (Hard Knee)")
    xs_curve = np.linspace(-60, 0, 500)
    curve_line, = ax2.plot(xs_curve, xs_curve, color="blue", label="Curve")
    line_input_diag, = ax2.plot(xs_curve, xs_curve, color="green", linestyle='--', label="Input Line (dB)")
    dot_input, = ax2.plot([], [], marker='o', color='gold', label="Current Input (dB)")
    dot_output, = ax2.plot([], [], marker='o', color='red', label="Predicted Output (dB)")
    ax2.set_xlim(-60, 0)
    ax2.set_ylim(-60, 12)
    ax2.grid(True)
    ax2.set_ylabel("Output Level (dB)")
    ax2.set_xlabel("Input Envelope Level (dB)") 
    ax2.legend(loc="upper left")

    # --- 3. Envelope follower (Linier) ---
    ax3.set_title("3. Envelope Follower (Attack/Release) (Linier)")
    ax3.set_ylim(0,1.05)
    ax3.set_ylabel("Amplitude (Linier)")
    line_abs, = ax3.plot([],[],color="gold", label="|x| (Absolute Input)")
    line_env, = ax3.plot([],[],color="red", label="Envelope State")
    line_thresh_lin, = ax3.plot([0, MAX_PLOT_SAMPLES], [0, 0], color='black', linestyle='-.', linewidth=2, label="Threshold (Linier)") 
    ax3.legend(loc="upper left")
    ax3.set_xlabel(f"Sampel Audio (1 Unit = {DOWNSAMPLE_PLOT} Sampel)") 
    
    # --- 4. Level History (Input/Output dB) ---
    ax4.set_title("4. Level History (Input/Output Peak dB)")
    ax4.set_ylim(-60, 5) 
    ax4.set_ylabel("Level (dBFS)")
    ax4.set_xlabel(f"Sampel Audio (Waktu)") 
    line_db_in, = ax4.plot([],[],color="gold", label="Input dB")
    line_db_out, = ax4.plot([],[],color="red", label="Output dB")
    line_thresh_db, = ax4.plot([0, MAX_PLOT_SAMPLES], [-20, -20], color='black', linestyle='-.', linewidth=2, label="Threshold (dB)")
    ax4.legend(loc="upper left")

    plt.setp(ax3.get_xticklabels(), visible=False)
    plt.tight_layout()

    xs = np.arange(MAX_PLOT_SAMPLES//DOWNSAMPLE_PLOT)

    while not stop_flag:
        with buf_lock:
            ptr = buf_ptr
            def rot(a): return np.concatenate((a[ptr:], a[:ptr]))
            
            in_b_fixed = rot(input_buf_fixed)
            out_b_fixed = rot(output_buf_fixed)
            env_b_fixed = rot(envelope_buf_fixed)
            abs_b_fixed = np.abs(in_b_fixed)

        # --- KONVERSI KE FLOAT UNTUK PLOTTING ---
        p = params.copy()
        T_fixed_local = parse_decimal_string_to_fixed_inline(p["threshold"])
        M_fixed_local = parse_decimal_string_to_fixed_inline(p["makeup"])
        
        T_db = fixed_to_db(T_fixed_local)
        R_inv = parse_ratio_to_rinv_float(p["ratio"])
        M_db = fixed_to_db(M_fixed_local)
        
        w_in = fixed_to_float(in_b_fixed[::DOWNSAMPLE_PLOT][-len(xs):])
        w_out = fixed_to_float(out_b_fixed[::DOWNSAMPLE_PLOT][-len(xs):])
        ea = fixed_to_float(abs_b_fixed[::DOWNSAMPLE_PLOT][-len(xs):])
        ev = fixed_to_float(env_b_fixed[::DOWNSAMPLE_PLOT][-len(xs):])

        # 1. Waveform (ax1)
        line_in.set_data(xs, w_in)
        line_out.set_data(xs, w_out)
        ax1.set_xlim(0,len(xs))

        # 2. Dynamic curve (ax2)
        curve = np.where(xs_curve < T_db, xs_curve, T_db + (xs_curve - T_db) * R_inv) + M_db
        curve_line.set_ydata(curve)

        # 3. Envelope plot (ax3)
        line_abs.set_data(xs, ea)
        line_env.set_data(xs, ev)
        ax3.set_xlim(0, len(xs))

        # Update Threshold Garis
        T_lin = fixed_to_float(T_fixed_local)
        line_thresh_lin.set_ydata([T_lin, T_lin]) 
        line_thresh_db.set_ydata([T_db, T_db]) 

        # 4. Level History (ax4)
        db_in = fixed_to_db(in_b_fixed[::DOWNSAMPLE_PLOT][-len(xs):])
        db_out = fixed_to_db(out_b_fixed[::DOWNSAMPLE_PLOT][-len(xs):])
        line_db_in.set_data(xs, db_in)
        line_db_out.set_data(xs, db_out)
        ax4.set_xlim(0, len(xs))
        
        # Gain reduction meter & Moving Dots (UPDATE dari queue)
        gr = 0.0
        env_db = None
        try:
            while True:
                m = metrics_q.get_nowait()
                gr = m["gain_reduction_db"]
                env_db = m.get("env_input_db")
        except queue.Empty:
            pass
            
        # Update Annotation Gain Reduction
        gr_text.set_text(f"Gain Reduction: {gr:.2f} dB") 

        # Update Moving Dots (ax2)
        if env_db is not None:
            x_dot = np.clip(env_db, -60.0, 0.0)
            if x_dot >= T_db:
                mapped_out_db = T_db + (x_dot - T_db) * R_inv + M_db
            else:
                mapped_out_db = x_dot + M_db
            
            dot_input.set_data([x_dot], [x_dot]) 
            dot_output.set_data([x_dot], [mapped_out_db])
        else:
            dot_input.set_data([], [])
            dot_output.set_data([], [])

        fig.canvas.draw()
        fig.canvas.flush_events()
        time.sleep(0.1)

    plt.close(fig)

# --------------------------------
# Main: start stream + parameter thread + plotting thread
# --------------------------------

def main():
    global processing, stop_flag, play_index, envelope_state_fixed, g_prev_fixed
    
    if not os.path.exists(wav_path) if wav_path else True and audio_data_int32 is None:
        print("WAV file needed to run streaming. Exiting.")
        return

    processing = True
    stop_flag = False
    play_index = 0
    envelope_state_fixed = np.int32(0)
    g_prev_fixed = np.int32(ONE)
    
    try:
        # Start Audio Stream
        stream = sd.OutputStream(samplerate=fs, channels=1, blocksize=BLOCKSIZE, dtype='int16', callback=audio_callback)
        stream.start()
    except Exception as e:
        print("Failed to start audio stream:", e)
        processing = False
        return

    # Start Console Parameter Thread
    thr_console = threading.Thread(target=parameter_input_thread, daemon=False)
    thr_console.start()

    # Start Plotting Thread
    thr_plot = threading.Thread(target=run_plot_loop, daemon=False)
    thr_plot.start()

    try:
        while thr_console.is_alive() and not stop_flag:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    stop_flag = True
    processing = False
    if thr_console.is_alive():
        thr_console.join()
    if thr_plot.is_alive():
        thr_plot.join()

    try:
        stream.stop(); stream.close()
    except Exception:
        pass

    print("Exiting.")

if __name__ == "__main__":
    main()