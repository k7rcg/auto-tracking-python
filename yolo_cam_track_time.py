import cv2
import time
from ultralytics import YOLO
import serial

# ==========================================
# 0. Picoとのシリアル通信の初期設定
# ==========================================
try:
    ser = serial.Serial('/dev/ttyACM0', 115200, timeout=0.05, dsrdtr=True, rtscts=True)
    print("Picoとのシリアル通信を開始しました。")
    time.sleep(2)  # 通信が安定するまで少し待つ
except Exception as e:
    print(f"Picoが見つかりません。シリアル送信なしで実行します: {e}")
    ser = None

# ==========================================
# 1. YOLOモデルと内蔵カメラの読み込み
# ==========================================
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("エラー: 内蔵カメラを開けませんでした。")
    exit()

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
screen_center_x = frame_width // 2

print("\n==========================================")
print("リアルタイム追跡を開始します...")
print("画面ウィンドウをクリックし、【Qキー】を押すと終了します。")
print("==========================================\n")

frame_count = 0

# ==========================================
# 2. 制御のための初期設定パラメータ（270度・中央ホーミング対応）
# ==========================================
DETECTION_INTERVAL = 5
current_imgsz = 416
current_servo_duty = 4915
DUTY_MIN = 1638
DUTY_MAX = 8192
annotated_frame = None

# ★【追加】タイムスタンプ用の基準時間を記録
start_time = time.time()

# ==========================================
# 3. リアルタイム・カメラのループ処理
# ==========================================
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("カメラ映像の取得に失敗しました。")
        break

    frame_count += 1

    if frame_count == 1 or (frame_count % DETECTION_INTERVAL == 0):
        results = model(source=frame, imgsz=current_imgsz, conf=0.20, verbose=False)
        annotated_frame = results[0].plot()

        if results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            max_height = 0
            target_box = None

            for box in boxes:
                box_h = box[3] - box[1]
                if box_h > max_height:
                    max_height = box_h
                    target_box = box

            if target_box is not None and ser is not None:
                target_center_x = int((target_box[0] + target_box[2]) / 2)
                error_x = target_center_x - screen_center_x
                
                move_amount = -int(error_x * 1.5)
                current_servo_duty += move_amount
                
                if current_servo_duty < DUTY_MIN: current_servo_duty = DUTY_MIN
                if current_servo_duty > DUTY_MAX: current_servo_duty = DUTY_MAX
                
                # --------------------------------------------------
                # ★【修正】タイムスタンプ（ミリ秒）を計算してカンマ区切りで送信
                # --------------------------------------------------
                elapsed_ms = int((time.time() - start_time) * 1000)
                send_data = f"{elapsed_ms},{current_servo_duty}\n"  # 例: "4500,5200\n"
                
                ser.write(send_data.encode('utf-8'))
                print(f"フレーム {frame_count}: Picoへ送信 -> 時刻:{elapsed_ms}ms, 位置:{current_servo_duty}")

        else:
            print(f"フレーム {frame_count}: 画面内に誰もいません...")

    else:
        if annotated_frame is None:
            annotated_frame = frame

    cv2.imshow("YOLOv8 Real-Time Tracking", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("\nユーザーによって終了されました。")
        break

if ser is not None:
    ser.close()
cap.release()
cv2.destroyAllWindows()
print("システムを正常に終了しました。")
