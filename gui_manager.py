import tkinter as tk
from tkinter import messagebox
import threading
import sys
import yolo_cam_track_time_2axis as tracker

class TrackingGUIManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Gimbal Control Center")
        self.root.geometry("450x380")
        self.root.configure(bg="#2c3e50")
        
        self.is_running = False
        self.stop_event = False

        title_label = tk.Label(root, text="AUTOMATIC TRACKING CONTROL PANEL", font=("Helvetica", 16, "bold"), fg="#ecf0f1", bg="#2c3e50")
        title_label.pack(pady=20)

        # --- ① 通常自動追尾スタートボタン ---
        self.start_normal_btn = tk.Button(root, text="▶ START NORMAL MODE", font=("Helvetica", 11, "bold"), bg="#2ecc71", fg="white", width=25, height=2, command=self.click_start_normal)
        self.start_normal_btn.pack(pady=8)

        # --- ② カラー記憶自動追尾スタートボタン（新規追加） ---
        self.start_color_btn = tk.Button(root, text="🎨 START COLOR-LOCK MODE", font=("Helvetica", 11, "bold"), bg="#9b59b6", fg="white", width=25, height=2, command=self.click_start_color)
        self.start_color_btn.pack(pady=8)

        # --- ③ 自動追尾終了ボタン ---
        self.stop_btn = tk.Button(root, text="■ STOP TRACKING", font=("Helvetica", 11, "bold"), bg="#e74c3c", fg="white", width=25, height=2, command=self.click_stop, state=tk.DISABLED)
        self.stop_btn.pack(pady=8)

        # --- ④ ソフト自体を閉じるボタン ---
        close_btn = tk.Button(root, text="EXIT APPLICATION", font=("Helvetica", 10), bg="#95a5a6", fg="white", width=15, command=self.click_close)
        close_btn.pack(pady=20)

        self.root.protocol("WM_DELETE_WINDOW", self.click_close)

    def run_tracker(self, mode):
        print(f"親GUI: {mode} モードで追尾を開始します...")
        self.is_running = True
        self.stop_event = False
        
        # すべてのスタートボタンを無効化
        self.start_normal_btn.config(state=tk.DISABLED, bg="#7f8c8d")
        self.start_color_btn.config(state=tk.DISABLED, bg="#7f8c8d")
        self.stop_btn.config(state=tk.NORMAL, bg="#e74c3c")

        # 引数にmodeを追加してスレッド起動
        self.tracking_thread = threading.Thread(
            target=tracker.start_tracking, 
            args=(lambda: self.stop_event, mode)
        )
        self.tracking_thread.daemon = True
        self.tracking_thread.start()

    def click_start_normal(self):
        if not self.is_running:
            self.run_tracker("normal")

    def click_start_color(self):
        if not self.is_running:
            messagebox.showinfo("カラー記憶のご案内", "スタート後、カメラ正面に立ってください。\n自動的に服の色を読み取り、ロックオンします。")
            self.run_tracker("color_memo")

    def click_stop(self):
        if self.is_running:
            print("親GUI: 追尾停止の信号を送りました...")
            self.stop_event = True
            self.is_running = False
            
            # ボタンの状態を復元
            self.start_normal_btn.config(state=tk.NORMAL, bg="#2ecc71")
            self.start_color_btn.config(state=tk.NORMAL, bg="#9b59b6")
            self.stop_btn.config(state=tk.DISABLED, bg="#7f8c8d")

    def click_close(self):
        if self.is_running:
            self.click_stop()
        print("親GUI: アブリーケションを終了します。")
        self.root.quit()
        sys.exit()

if __name__ == "__main__":
    root = tk.Tk()
    app = TrackingGUIManager(root)
    root.mainloop()

