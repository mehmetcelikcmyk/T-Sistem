"""
Claude API Anahtar Havuzu ve Akıllı Yük Dengeleyici (Load Balancer & Rate Limit Handler)
3 API Key arasında dönüşümlü (Round-Robin) ve hata anında otomatik yedekleme (Failover) sağlar.
"""
import os
import itertools
import threading
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class ClaudeKeyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ClaudeKeyManager, cls).__new__(cls)
                cls._instance._init_keys()
            return cls._instance

    def _init_keys(self):
        # .env dosyasından anahtarları al
        keys_str = os.getenv("ANTHROPIC_API_KEYS", "")
        single_key = os.getenv("ANTHROPIC_API_KEY", "")
        
        raw_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if single_key and single_key not in raw_keys:
            raw_keys.append(single_key.strip())
            
        self.keys: List[str] = raw_keys
        self.index = 0
        self._key_cycle = itertools.cycle(self.keys) if self.keys else None
        print(f"[Claude Key Manager] Aktif Anahtar Havuzu: {len(self.keys)} adet API Key yuklendi.")

    def get_next_key(self) -> Optional[str]:
        """Sıradaki API Key'i döner (Round-Robin Yük Dengeleme)."""
        with self._lock:
            if not self.keys:
                return None
            return next(self._key_cycle)

    def execute_with_failover(self, api_func):
        """
        Fonksiyonu çalıştırır; eğer bir anahtarda Rate Limit / 429 veya hata çıkarsa
        otomatik olarak sıradaki diğer API Key ile dener!
        """
        if not self.keys:
            raise ValueError("Hiçbir Claude API anahtarı bulunamadı.")

        last_error = None
        # Havuzdaki tüm anahtarları sırayla dene
        for attempt in range(len(self.keys)):
            current_key = self.get_next_key()
            try:
                return api_func(current_key)
            except Exception as e:
                err_msg = str(e).encode("ascii", "replace").decode("ascii")
                try:
                    print(f"[Key Failover]: Anahtar {attempt + 1} hata verdi: {err_msg[:60]}... Siradaki anahtara geciliyor.")
                except Exception:
                    pass
                last_error = e

        raise last_error

# Singleton instance
key_manager = ClaudeKeyManager()
