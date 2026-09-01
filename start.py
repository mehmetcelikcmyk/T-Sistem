#!/usr/bin/env python3
"""
T-Sistem — Tek Komutla Tüm Sistemi Başlat

Çalıştırma:
    python start.py           # Backend + UI birlikte başlar
    python start.py --only-api  # Yalnızca FastAPI backend
    python start.py --only-ui   # Yalnızca Streamlit UI (Mock modda)
"""

import os
import sys
import subprocess
import time
import argparse
from pathlib import Path

# Windows konsol UTF-8 desteği
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent


def start_backend():
    """FastAPI backend'i başlatır (http://localhost:8000)"""
    print("🚀 FastAPI Backend başlatılıyor → http://localhost:8000")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        cwd=str(ROOT),
    )


def start_ui(with_backend: bool = True):
    """Streamlit UI'ı başlatır (http://localhost:8501)"""
    env = os.environ.copy()
    if with_backend:
        env["T_SISTEM_API"] = "http://localhost:8000/api"
        print("🖥️  Streamlit UI başlatılıyor → http://localhost:8501 (Backend: CANLI)")
    else:
        print("🖥️  Streamlit UI başlatılıyor → http://localhost:8501 (Backend: MOCK)")
    return subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "src/ui/app.py",
         "--server.port", "8501", "--server.address", "localhost"],
        cwd=str(ROOT),
        env=env,
    )


def main():
    parser = argparse.ArgumentParser(description="T-Sistem Başlatıcı")
    parser.add_argument("--only-api", action="store_true", help="Yalnızca FastAPI backend başlat")
    parser.add_argument("--only-ui", action="store_true", help="Yalnızca Streamlit UI başlat (mock mod)")
    args = parser.parse_args()

    processes = []

    try:
        if args.only_api:
            p = start_backend()
            processes.append(p)
        elif args.only_ui:
            p = start_ui(with_backend=False)
            processes.append(p)
        else:
            # İkisi birlikte
            api_proc = start_backend()
            processes.append(api_proc)
            print("⏳ Backend'in hazır olması için 3 saniye bekleniyor...")
            time.sleep(3)
            ui_proc = start_ui(with_backend=True)
            processes.append(ui_proc)

        print()
        print("=" * 60)
        print("  ✅ T-Sistem Çalışıyor!")
        if not args.only_ui:
            print("  📚 API Docs     → http://localhost:8000/docs")
        if not args.only_api:
            print("  🖥️  Giriş Portalı → http://localhost:8501")
        print("  Durdurmak için : Ctrl+C")
        print("=" * 60)

        for p in processes:
            p.wait()

    except KeyboardInterrupt:
        print("\n🛑 T-Sistem durduruluyor...")
        for p in processes:
            p.terminate()
        print("✅ Tüm süreçler durduruldu.")


if __name__ == "__main__":
    main()
