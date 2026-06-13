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
# 1. YOLOモデルと動画の読み込み
# ==========================================
model = YOLO("yolov8n.pt")
video_path = "test_video.mp4"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print(f"エラー: {video_path} を開けませんでした。パスや形式を確認してください。")
    exit()

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)

# 画面の中心X座標
screen_center_x = frame_width // 2

# 結果を保存するための動画書き込み準備
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('track_result.mp4', fourcc, fps, (frame_width, frame_height))

print("動画の追跡解析を開始します。しばらくお待ちください...")
start_time = time.time()
frame_count = 0

# ==========================================
# 2. 動的制御のための初期設定パラメータ
# ==========================================
fps_round = round(fps)
interval_near = max(1, fps_round // 2)  # 近く（1秒に2回用）
interval_far = max(1, fps_round // 1)   # 遠く（1秒に1回用）

current_interval = interval_near
current_imgsz = 320
annotated_frame = None

DISTANCE_THRESHOLD_PX = int(frame_height * 0.15) 

# 現在のサーボの想定位置（中央4900からスタート）
current_servo_duty = 4900

# ==========================================
# 2. 動的制御のための初期設定パラメータ（完全版）
# ==========================================
# カチカチ動きを防ぐため、検知間隔  さげるとなめらか
DETECTION_INTERVAL = 5 

current_imgsz = 416
annotated_frame = None

DISTANCE_THRESHOLD_PX = int(frame_height * 0.15) 

# 現在のサーボの想定位置（中央4900からスタート）
current_servo_duty = 4900

# ==========================================
# 3. 動画のループ処理（とにかく枠があれば動かす版）
# ==========================================
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    frame_count += 1

    # 一定フレーム間隔（今回は10のままでも、5でも実験可能です）ごとにYOLOを動かす
    if frame_count == 1 or (frame_count % DETECTION_INTERVAL == 0):
        
        # 背番号(track)ではなく、ただの検出(predict)でも動くように、シンプルなモデル呼び出しにします
        results = model(source=frame, imgsz=current_imgsz, conf=0.20, verbose=False)
        
        annotated_frame = results[0].plot()

        # 【ここを修正】背番号(id)ではなく、単に「枠(boxes)が1つ以上あるか」だけをチェックする
        if results[0].boxes is not None and len(results[0].boxes) > 0:
            
            # 画面内の枠の座標を取得
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
            # ターゲットを中央に捉えるためのサーボ位置（数字）を計算して送信
            # --------------------------------------------------
            if target_box is not None and ser is not None:
                target_center_x = int((target_box[0] + target_box[2]) / 2)  # 中心X座標
                error_x = target_center_x - screen_center_x
                
                # 移動量（感度）の計算
                move_amount = -int(error_x * 0.1)
                current_servo_duty += move_amount
                
                # 安全ガード
                if current_servo_duty < 1638: current_servo_duty = 1638
                if current_servo_duty > 8192: current_servo_duty = 8192
                
                # Picoへ送信
                send_data = f"{current_servo_duty}\n"
                ser.write(send_data.encode('utf-8'))
                print(f"フレーム {frame_count}: ターゲット補足！Picoへ送信 -> {current_servo_duty} (ズレ: {error_x}px)")

        else:
            print(f"フレーム {frame_count}: 画面内に誰もいません...")

    else:
        if annotated_frame is not None:
            out.write(annotated_frame)
            continue
        else:
            annotated_frame = frame

    out.write(annotated_frame)

end_time = time.time()
total_time = end_time - start_time
actual_fps = frame_count / total_time

print("\n--- 解析が完了しました ---")
print(f"処理した合計フレーム数: {frame_count} コマ")
print(f"解析にかかった時間: {total_time:.2f} 秒")
print(f"1秒あたりの処理速度: {actual_fps:.1f} 回 (FPS)")

# 後片付け
if ser is not None:
    ser.close()
cap.release()
out.release()

