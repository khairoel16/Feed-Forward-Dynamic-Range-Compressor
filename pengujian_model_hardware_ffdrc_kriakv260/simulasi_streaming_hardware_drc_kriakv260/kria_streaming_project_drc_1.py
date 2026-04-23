# NAMA FILE : kria_streaming_project_drc_1.py
import numpy as np
import time
import sys
import os
import threading
import traceback
import pyaudio
import librosa
from pynq import Overlay, allocate

# 1. Konfigurasi Lingkungan Audio Linux Kria
os.environ["SDL_AUDIODRIVER"] = "alsa"
os.environ["PULSE_SERVER"] = "none"
os.environ["XDG_RUNTIME_DIR"] = "/run/user/1000"

# 2. File Hardware (Pastikan jalur file benar)
BITSTREAM_FILE = "/home/ubuntu/DRC/design_project_drc_1.bit"
DEFAULT_INPUT_FILE = "/home/ubuntu/wavs/misteryoso16.wav"
INPUT_FILE = DEFAULT_INPUT_FILE

# 3. Konstanta AXI & Streaming
CHUNK_FRAMES = 1024
ONE_Q30 = 1 << 30  # Representasi 1.0 dalam Q1.30 (1073741824)

# 4. Nama IP (Sesuai dengan Address Editor & Block Design Anda)
DMA_NAME  = "axi_dma_0"
IP_ENV    = "drc_envelope_follower_0"
IP_COMP   = "drc_gain_computer_0"
IP_SMOOTH = "drc_gain_smoothing_0"
IP_APPLY  = "drc_makeup_apply_0"
IP_PCM    = "drc_pcm_formatter_0"

# 5. Parameter Global DRC (7 Parameter Kontrol Lengkap)
params = {
    "running": True,
    "threshold": 1.0,   # T (Linear 0.0 - 1.0)
    "rinv": 0.25,        # R_inv (1/Ratio, misal 0.25 = 4:1)
    "env_aa": 0.9995,    # Envelope Follower Attack Alpha
    "env_ar": 0.9999,    # Envelope Follower Release Alpha
    "smooth_aa": 0.995,  # Gain Smoothing Attack Alpha
    "smooth_ar": 0.9995, # Gain Smoothing Release Alpha
    "makeup": 1.0        # Makeup Gain (Linear 0.0 - 2.0)
}

def to_q30(x):
    """Konversi float ke Signed Q1.30 Integer untuk AXI-Lite"""
    val = int(x * ONE_Q30)
    return int(np.clip(val, -2147483648, 2147483647))

def audio_engine_thread(overlay, dma, ips):
    global params, INPUT_FILE
    p = pyaudio.PyAudio()
    stream = None
    
    # Alokasi buffer DMA (Mono 16-bit signed sesuai drc_pcm_formatter)
    buffer_in = allocate(shape=(CHUNK_FRAMES,), dtype=np.int16, cacheable=False)
    buffer_out = allocate(shape=(CHUNK_FRAMES,), dtype=np.int16, cacheable=False)
    
    try:
        print(f"\n[Engine] Loading Mono WAV: {INPUT_FILE}")
        y, sr = librosa.load(INPUT_FILE, sr=None, mono=True)
        audio_int16 = (y * 32767).astype(np.int16)
        
        stream = p.open(format=pyaudio.paInt16, 
                        channels=1, 
                        rate=sr,
                        output=True, 
                        frames_per_buffer=CHUNK_FRAMES)
        
        total_samples = len(audio_int16)
        cursor = 0
        
        print("[Engine] DRC PROCESSING STARTED...")

        while params["running"] and cursor < total_samples:
            # --- UPDATE PARAMETER VIA AXI-LITE (7 PARAMETER) ---
            
            # Modul 1: Envelope Follower
            ips['env'].write(0x00, to_q30(params["env_aa"]))
            ips['env'].write(0x04, to_q30(params["env_ar"]))
            
            # Modul 2: Gain Computer
            ips['comp'].write(0x00, to_q30(params["threshold"]))
            ips['comp'].write(0x04, to_q30(params["rinv"]))
            
            # Modul 3: Gain Smoothing
            ips['smooth'].write(0x00, to_q30(params["smooth_aa"]))
            ips['smooth'].write(0x04, to_q30(params["smooth_ar"]))
            
            # Modul 4: Makeup Apply
            ips['apply'].write(0x00, to_q30(params["makeup"]))

            # --- AXI-STREAM PROCESSING ---
            end = cursor + CHUNK_FRAMES
            chunk = audio_int16[cursor:end]
            n = len(chunk)
            if n == 0: break
            
            buffer_in[:n] = chunk
            if n < CHUNK_FRAMES: buffer_in[n:] = 0
            
            dma.recvchannel.transfer(buffer_out)
            dma.sendchannel.transfer(buffer_in)
            dma.sendchannel.wait()
            dma.recvchannel.wait()
            
            stream.write(buffer_out[:n].tobytes())
            cursor = end

    except Exception as e:
        print(f"\n[Engine] Error: {e}")
        traceback.print_exc()
    finally:
        params["running"] = False
        if stream: stream.close()
        p.terminate()
        buffer_in.freebuffer()
        buffer_out.freebuffer()

def main():
    print("\n=== KRIA KV260: DRC FULL 7-PARAMETER TESTER ===")
    path = input(f"File WAV [{os.path.basename(DEFAULT_INPUT_FILE)}]: ").strip()
    if path: globals()['INPUT_FILE'] = path
    
    try:
        overlay = Overlay(BITSTREAM_FILE)
        dma = getattr(overlay, DMA_NAME)
        
        ips = {
            'env': getattr(overlay, IP_ENV),
            'comp': getattr(overlay, IP_COMP),
            'smooth': getattr(overlay, IP_SMOOTH),
            'apply': getattr(overlay, IP_APPLY)
        }
        print("[System] Hardware Overlay & IP Handles: OK")
    except Exception as e:
        print(f"[System] Init Gagal: {e}")
        return

    # Jalankan Audio Thread
    t = threading.Thread(target=audio_engine_thread, args=(overlay, dma, ips))
    t.daemon = True
    t.start()

    print("\nDAFTAR PERINTAH LENGKAP:")
    print("  t [0-1]   : Threshold")
    print("  r [0-1]   : Ratio Inverse (1/R)")
    print("  m [0-2]   : Makeup Gain")
    print("  ea [0-1]  : Envelope Attack")
    print("  er [0-1]  : Envelope Release")
    print("  sa [0-1]  : Smoothing Attack")
    print("  sr [0-1]  : Smoothing Release")
    print("  q         : Quit")

    try:
        while params["running"]:
            # MODIFIKASI: Menampilkan semua 7 parameter agar terpantau di console secara streaming
            status = (f"\r[T:{params['threshold']:.2f} R:{params['rinv']:.2f} M:{params['makeup']:.2f} "
                      f"EA:{params['env_aa']:.4f} ER:{params['env_ar']:.4f} "
                      f"SA:{params['smooth_aa']:.4f} SR:{params['smooth_ar']:.4f}] > ")
            
            user_in = input(status).strip().lower().split()
            
            if not user_in: continue
            cmd = user_in[0]
            if cmd == 'q':
                params["running"] = False
                break
            
            if len(user_in) < 2: continue

            try:
                val = float(user_in[1])
                if   cmd == 't':  params["threshold"] = np.clip(val, 0.0, 1.0)
                elif cmd == 'r':  params["rinv"]      = np.clip(val, 0.0, 1.0)
                # MODIFIKASI: Makeup Gain rentang 0.0 hingga 2.0
                elif cmd == 'm':  params["makeup"]    = np.clip(val, 0.0, 2.0)
                elif cmd == 'ea': params["env_aa"]    = np.clip(val, 0.0, 1.0)
                elif cmd == 'er': params["env_ar"]    = np.clip(val, 0.0, 1.0)
                elif cmd == 'sa': params["smooth_aa"] = np.clip(val, 0.0, 1.0)
                elif cmd == 'sr': params["smooth_ar"] = np.clip(val, 0.0, 1.0)
                else: print(f"\nCommand '{cmd}' tidak dikenal.")
            except ValueError:
                print("\nError: Masukkan angka.")

    except KeyboardInterrupt:
        params["running"] = False

    t.join()
    print("\nSelesai.")

if __name__ == "__main__":
    main()