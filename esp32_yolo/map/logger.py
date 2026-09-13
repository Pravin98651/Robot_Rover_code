import os
import time
import json
import queue
import threading
from datetime import datetime

class MissionLogger:
    def __init__(self, log_dir):
        self.log_dir = log_dir
        self.queue = queue.Queue()
        self.running = False
        self.thread = None
        
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            
        self.log_file = os.path.join(self.log_dir, f"mission_{int(time.time())}.jsonl")
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            
    def log_detection(self, detection):
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": "SURVIVOR_DETECTED",
            "data": detection
        }
        try:
            self.queue.put_nowait(event)
        except queue.Full:
            pass
            
    def _writer_loop(self):
        with open(self.log_file, 'a') as f:
            while self.running or not self.queue.empty():
                try:
                    event = self.queue.get(timeout=1.0)
                    f.write(json.dumps(event) + "\n")
                    f.flush()
                except queue.Empty:
                    pass
                except Exception as e:
                    print(f"[LOGGER] Write error: {e}")
