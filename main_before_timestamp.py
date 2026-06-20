import machine
import sys
import time
import uselect

# 1. サーボモーターの設定 (GPIO15)
servo = machine.PWM(machine.Pin(15))
servo.freq(50)

DUTY_MIN = 1638   
DUTY_MAX = 8192   

# 位置管理変数
current_duty = 4915.0
target_duty = 4915.0
servo.duty_u16(int(current_duty))

# ==========================================
# 【完全スロープ化：スピード固定値】
# ==========================================
# 10msの間にサーボが動く「固定の歩幅」
# 階段の角を丸めるのではなく、この歩幅で「完全な直線（スロープ）」を作る
# 動きが遅い場合は「10.0」「15.0」に上げ、カクつきが戻る場合は「5.0」に下げる
SLOPE_SPEED = 10.0  

# シリアル入力を監視する掃除センサー
poll = uselect.poll()
poll.register(sys.stdin, uselect.POLLIN)

print("Pico: Perfect Linear Slope Mode Ready...")

# 2. 受信と駆動のループ
while True:
    latest_line = None
    
    # 【お掃除機能】過去のゴミは常に一瞬で消去
    while poll.poll(0): 
        latest_line = sys.stdin.readline().strip()
    
    if latest_line:
        try:
            val = int(latest_line)
            if val < DUTY_MIN: val = DUTY_MIN
            if val > DUTY_MAX: val = DUTY_MAX
            target_duty = float(val)
        except ValueError:
            pass
            
    # === 【階段を完全に消し去る：定速直線スロープ計算】 ===
    diff = target_duty - current_duty
    
    if abs(diff) > 0.1:
        # 目的地が遠くても近くても、常に「SLOPE_SPEED」という一定の歩幅でまっすぐ進む
        if diff > 0:
            current_duty += SLOPE_SPEED
            # 行き過ぎ防止
            if current_duty > target_duty:
                current_duty = target_duty
        else:
            current_duty -= SLOPE_SPEED
            # 行き過ぎ防止
            if current_duty < target_duty:
                current_duty = target_duty
                
        # 毎ループ、等間隔な坂道データとしてサーボに出力
        servo.duty_u16(int(current_duty))
    else:
        current_duty = target_duty
        servo.duty_u16(int(current_duty))
            
    # 10ms（100Hz）で超高密度な直線を描く
    time.sleep(0.02)

