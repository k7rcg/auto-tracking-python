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

# 0 から 1 に変更したELPカメラの読み込み部分
cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("エラー: 内蔵カメラを開けませんでした。")
    exit()

# === 【調査結果を活かした最終修正：ここを書き換え】 ===
# ① フォーマットをMJPEGに強制指定します
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

# ② 解像度をあえて「1920×1080」に引き上げます
# これにより、カメラ側の内部チップが自動的に「30fpsモード」へ速度を落とします
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
# ==========================================

# カメラの画面サイズを取得
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

# 画面の中心X座標
screen_center_x = frame_width // 2

print("\n==========================================")
print("リアルタイム追跡を開始します...")
print("画面ウィンドウをクリックし、【Qキー】を押すと終了します。")
print("==========================================\n")

frame_count = 0

# ==========================================
# 2. 制御のための初期設定パラメータ（270度・中央ホーミング対応）
# ==========================================
# 5フレームに1回YOLOを動かす
DETECTION_INTERVAL = 5
current_imgsz = 416

# 現在のサーボの想定位置（270度の中央 4915 からスタート）
current_servo_duty = 4915

# 安全ガードの制限値（Pico側と完全に一致させる）
DUTY_MIN = 1638
DUTY_MAX = 8192

# スキップ用フレームの初期化
annotated_frame = None

# ==========================================
# 3. リアルタイム・カメラのループ処理
# ==========================================
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("カメラ映像の取得に失敗しました。")
        break

    frame_count += 1

    # 指定したフレーム間隔ごとにYOLOの検知を実行
    if frame_count == 1 or (frame_count % DETECTION_INTERVAL == 0):
        
        # 枠だけのシンプルな検出処理
        results = model(source=frame, imgsz=current_imgsz, conf=0.20, verbose=False)
        
        # YOLOの検出枠（青い枠など）を描き込んだ画像を保持
        annotated_frame = results[0].plot()

        # 枠が1つ以上あるかチェック
        if results[0].boxes is not None and len(results[0].boxes) > 0:
            
            boxes = results[0].boxes.xyxy.cpu().numpy()
            max_height = 0
            target_box = None

            # 一番大きく映っている（一番高い）枠をターゲットにする
            for box in boxes:
                box_h = box[3] - box[1]  # 高さを正確に計算
                if box_h > max_height:
                    max_height = box_h
                    target_box = box

            # --------------------------------------------------
            # ターゲットを中央に捉えるためのサーボ位置を計算して送信
            # --------------------------------------------------
            if target_box is not None and ser is not None:
                target_center_x = int((target_box[0] + target_box[2]) / 2)  # 中心X座標
                error_x = target_center_x - screen_center_x
                
                # 移動量（感度）の計算を 0.3 に強化して大きく動かします
                move_amount = -int(error_x * 1.5)
                current_servo_duty += move_amount
                
                # 270度用の安全ガード
                if current_servo_duty < DUTY_MIN: current_servo_duty = DUTY_MIN
                if current_servo_duty > DUTY_MAX: current_servo_duty = DUTY_MAX
                
                # Picoへ送信
                send_data = f"{current_servo_duty}\n"
                ser.write(send_data.encode('utf-8'))
                print(f"フレーム {frame_count}: ターゲット補足！Picoへ送信 -> {current_servo_duty} (ズレ: {error_x}px)")

        else:
            print(f"フレーム {frame_count}: 画面内に誰もいません...")

    else:
        # YOLOをお休みするフレームでは、直前の枠付き画像を表示して動画の滑らかさを維持
        if annotated_frame is None:
            annotated_frame = frame

    # パソコンの画面に現在のリアルタイム映像をウィンドウ表示する
    cv2.imshow("YOLOv8 Real-Time Tracking", annotated_frame)

    # キーボードの「Q」が押されたら安全にループを終了する
    if cv2.waitKey(1) & 0xFF == ord('q'):
        print("\nユーザーによって終了されました。")
        break

# 後片付け（ポートを綺麗に閉じる）
if ser is not None:
    ser.close()
cap.release()
cv2.destroyAllWindows()  # 表示ウィンドウを閉じる
print("システムを正常に終了しました。")

