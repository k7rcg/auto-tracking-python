import machine
import sys
import time
import uselect

# 1. サーボモーターの設定 (GPIO15)
servo = machine.PWM(machine.Pin(15))
servo.freq(50)

DUTY_MIN = 1638   
DUTY_MAX = 8192   

# 位置・時間管理変数
current_duty = 4915.0
servo.duty_u16(int(current_duty))

# タイムスタンプ追従用の変数
target_duty = 4915.0
start_duty = 4915.0
step_progress = 1.0  # 補完の進捗率（0.0 〜 1.0）
step_increment = 0.1 # 1ループ（10ms）あたりに進む割合

# データバッファ（受信したデータを一時保存するリスト）
data_buffer = []

# シリアル入力の監視
poll = uselect.poll()
poll.register(sys.stdin, uselect.POLLIN)

print("Pico: Timestamp-Driven Buffering Mode Ready...")

# 最後にPCからデータを受け取った時の、PC側のタイムスタンプ保持用
last_pc_time = None

LOOP_INTERVAL = 0.01 # 10msループ（100Hz）

while True:
    loop_start = time.ticks_ms()
    
    # --- 【1. バッファリング機能】届いたデータをすべて配列に溜める ---
    while poll.poll(0): 
        line = sys.stdin.readline().strip()
        if line:
            try:
                # 「タイムスタンプ,デューティ比」の形式を想定 (例: "12500,4915")
                parts = line.split(',')
                if len(parts) == 2:
                    pc_time = int(parts[0])
                    val = int(parts[1])
                    
                    if val < DUTY_MIN: val = DUTY_MIN
                    if val > DUTY_MAX: val = DUTY_MAX
                    
                    # バッファに追加
                    data_buffer.append((pc_time, float(val)))
            except ValueError:
                pass

    # --- 【2. タイムスタンプ追従機能】（修正版） ---
    if step_progress >= 1.0 and len(data_buffer) > 0:
        next_pc_time, next_duty = data_buffer.pop(0)
        
        # 【追加】バッファが溜まりすぎていたら、古いデータを捨てて最新に追いつく
        if len(data_buffer) > 2:
            next_pc_time, next_duty = data_buffer.pop() # 一番新しいデータにスキップ
            data_buffer.clear() # バッファをリセット
        
        if last_pc_time is not None:
            time_diff = next_pc_time - last_pc_time
            if time_diff <= 0: 
                time_diff = 166 # 5フレーム間隔の想定値
                
            # 【重要】本来の時間の「0.8倍（2割引き）」の時間で到着させる
            # これにより遅延を取り戻し、行き過ぎ（オーバーシュート）を防ぐ
            adjusted_time = time_diff * 0.8
            step_increment = LOOP_INTERVAL * 1000 / adjusted_time
        else:
            step_increment = 1.0
            
        start_duty = current_duty
        target_duty = next_duty
        last_pc_time = next_pc_time
        step_progress = 0.0
            
        # 補完の基準点を更新
        start_duty = current_duty
        target_duty = next_duty
        last_pc_time = next_pc_time
        step_progress = 0.0 # 進捗をリセットして、新しいスロープを開始

    # --- 【3. タイムスタンプ型バッファリング補完：線形インターポレーション】 ---
    if step_progress < 1.0:
        # 進捗率を10msぶん進める
        step_progress += step_increment
        if step_progress > 1.0:
            step_progress = 1.0
            
        # ★タイムスタンプの時間幅に完全に追従した、正確な線形補完（Lerp）
        current_duty = start_duty + (target_duty - start_duty) * step_progress
        servo.duty_u16(int(current_duty))
    else:
        # バッファが空で、目的地に到着している場合は停止
        current_duty = target_duty
        servo.duty_u16(int(current_duty))

    # 正確に10ms（0.01秒）を維持するためのウェイト計算
    # (sleep_msだと処理にかかった時間ぶんズレるため、差分を引く)
    elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
    sleep_time = max(0, int(LOOP_INTERVAL * 1000 - elapsed))
    time.sleep_ms(sleep_time)

