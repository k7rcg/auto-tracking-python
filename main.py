import machine
import sys
import time

# 1. サーボモーターの設定 (GPIO15)
servo = machine.PWM(machine.Pin(15))
servo.freq(50)

# 現在位置の初期化（ホーミング：中央）
current_duty = 4900
servo.duty_u16(current_duty)

DUTY_MIN = 1638   
DUTY_MAX = 8192   

print("Pico: Ready for slow-motion test...")

# 2. 受信と駆動のループ
while True:
    # ラズパイ5から送られてくる1行（数字）を確実に待つ（一番確実に動いた方式）
    line = sys.stdin.readline().strip()
    
    if line:
        try:
            target_duty = int(line)
            
            if target_duty < DUTY_MIN: target_duty = DUTY_MIN
            if target_duty > DUTY_MAX: target_duty = DUTY_MAX
            
            # --- 【確実なスピード制限処理】 ---
            # 現在の位置から目標の位置まで、少しずつ時間をかけて近づける
            # 「歩幅」を細かくすることで、今の4分の1くらいのゆっくりさにします
            step = 15 if target_duty > current_duty else -15
            
            # 目標位置に到達するまで、じわじわと動かすループ
            for duty in range(current_duty, target_duty, step):
                servo.duty_u16(duty)
                time.sleep(0.01) # 10ミリ秒ごとに少しずつ動かす（ここで遅さをコントロール）
                
            # 最後にぴったり目標位置に合わせる
            current_duty = target_duty
            servo.duty_u16(current_duty)
            print(f"Pico: Smooth moved to {current_duty}")
            
        except ValueError:
            pass
            
    time.sleep(0.01)
