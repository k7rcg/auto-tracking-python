import cv2
import time
from ultralytics import YOLO
import serial
import numpy as np

def start_tracking(stop_flag, mode="normal"):
    """
    mode: "normal" または "color_memo"
    """
    try:
        ser = serial.Serial('/dev/ttyACM0', 115200, timeout=0.05, dsrdtr=True, rtscts=True)
        print("Picoとのシリアル通信を開始しました。")
        time.sleep(2)
    except Exception as e:
        print(f"Picoが見つかりません。シリアル送信なしで実行します: {e}")
        ser = None

    model = YOLO("yolov8n.pt")
    cap = cv2.VideoCapture(2)

    if not cap.isOpened():
        print("エラー: 内蔵カメラを開けませんでした。")
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    screen_center_x = frame_width // 2
    screen_center_y = frame_height // 2

    frame_count = 0
    DETECTION_INTERVAL = 5
    current_imgsz = 416
    PAN_MIN, PAN_MAX = 1638, 8192
    TILT_MIN, TILT_MAX = 4650, 5200
    current_pan_duty = 4915
    current_tilt_duty = 4915
    annotated_frame = None
    start_time = time.time()

    # --- カラー追尾用の状態管理変数 ---
    target_hsv = None       # 記憶した服の色 (H, S, V)
    color_status = "NONE"   # NONE -> MEMORIZING -> LOCKED
    
    if mode == "color_memo":
        color_status = "MEMORIZING"

    while cap.isOpened() and not stop_flag():
        success, frame = cap.read()
        if not success:
            break

        frame_count += 1

        if frame_count == 1 or (frame_count % DETECTION_INTERVAL == 0):
            # --- 【修正】モードによって検知対象を切り替える ---
            if mode == "color_memo" or color_status == "LOCKED":
                # カラーモードの時は「人間(0)」だけに絞り込む
                results = model(source=frame, imgsz=current_imgsz, conf=0.20, verbose=False, classes=[0])
            else:
                # 通常モードの時は、以前と同じく「椅子や机など何でも」検知する
                results = model(source=frame, imgsz=current_imgsz, conf=0.20, verbose=False)
                
            annotated_frame = results[0].plot()

            if results[0].boxes is not None and len(results[0].boxes) > 0:
                boxes = results[0].boxes.xyxy.cpu().numpy()
                
                # OpenCVで色の計算をするため、HSV空間に変換
                hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                
                best_target_box = None

                # --- 【A：カラー記憶フェーズ】 ---
                if color_status == "MEMORIZING":
                    # 最初に見つかった一番大きい人を「あなた」として色を記憶する
                    max_height = 0
                    for box in boxes:
                        box_h = box[3] - box[1]
                        if box_h > max_height:
                            max_height = box_h
                            best_target_box = box
                    
                    if best_target_box is not None:
                        # 胸元（バウンディングボックスの中央やや上）の座標を計算
                        x1, y1, x2, y2 = map(int, best_target_box[:4])
                        cx = int((x1 + x2) / 2)
                        cy = int(y1 + (y2 - y1) * 0.3)  # 上から30%の位置（胸元）
                        
                        # 安全な範囲で10x10ピクセルの矩形領域を切り抜く
                        h_start = max(0, cy - 5)
                        h_end = min(frame_height, cy + 5)
                        w_start = max(0, cx - 5)
                        w_end = min(frame_width, cx + 5)
                        
                        roi = hsv_frame[h_start:h_end, w_start:w_end]
                        if roi.size > 0:
                            # HSVそれぞれの平均値を算出して記憶
                            target_hsv = np.mean(roi, axis=(0, 1))
                            color_status = "LOCKED"
                            print(f"★カラー記憶完了! HSV: {target_hsv}")

                # --- 【B：追尾対象の選別フェーズ】 ---
                if color_status == "LOCKED":
                    # 記憶した色に最も近い人を探す
                    min_color_dist = float('inf')
                    for box in boxes:
                        x1, y1, x2, y2 = map(int, box[:4])
                        cx = int((x1 + x2) / 2)
                        cy = int(y1 + (y2 - y1) * 0.3)
                        
                        h_start, h_end = max(0, cy-5), min(frame_height, cy+5)
                        w_start, w_end = max(0, cx-5), min(frame_width, cx+5)
                        
                        roi = hsv_frame[h_start:h_end, w_start:w_end]
                        if roi.size > 0:
                            current_hsv = np.mean(roi, axis=(0, 1))
                            # HSVの距離（色相の違いを重視）を計算
                            dh = min(abs(current_hsv[0] - target_hsv[0]), 180 - abs(current_hsv[0] - target_hsv[0]))
                            ds = current_hsv[1] - target_hsv[1]
                            dv = current_hsv[2] - target_hsv[2]
                            # 色相(H)の重みを大きくして距離を算出
                            dist = np.sqrt((dh * 2.0) ** 2 + ds ** 2 + (dv * 0.5) ** 2)
                            
                            if dist < min_color_dist:
                                min_color_dist = dist
                                best_target_box = box
                else:
                    # 通常モード（従来通り、一番大きく映っている人を追う）
                    max_height = 0
                    for box in boxes:
                        box_h = box[3] - box[1]
                        if box_h > max_height:
                            max_height = box_h
                            best_target_box = box

                # --- 【C：Picoへの送信駆動】 ---
                if best_target_box is not None and ser is not None:
                    target_center_x = int((best_target_box[0] + best_target_box[2]) / 2)
                    error_x = target_center_x - screen_center_x
                    move_pan = -int(error_x * 0.6)
                    current_pan_duty += move_pan
                    
                    target_center_y = int((best_target_box[1] + best_target_box[3]) / 2)
                    error_y = target_center_y - screen_center_y
                    move_tilt = -int(error_y * 0.3)
                    current_tilt_duty += move_tilt
                    
                    current_pan_duty = max(PAN_MIN, min(PAN_MAX, current_pan_duty))
                    current_tilt_duty = max(TILT_MIN, min(TILT_MAX, current_tilt_duty))
                    
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    send_data = f"{elapsed_ms},{current_pan_duty},{current_tilt_duty}\n"
                    ser.write(send_data.encode('utf-8'))

        else:
            if annotated_frame is None:
                annotated_frame = frame

        # --- 【D：カメラ映像への状態テキスト重ね書き】 ---
        # 画面左上に現在のステータスを表示
        if color_status == "MEMORIZING":
            cv2.putText(annotated_frame, "COLOR SCANNING...", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
        elif color_status == "LOCKED":
            cv2.putText(annotated_frame, "COLOR LOCKED ON!", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            # 追尾しているターゲットの胸元に目印のドットを描画（デバッグ用）
            if 'best_target_box' in locals() and best_target_box is not None:
                bx = int((best_target_box[0] + best_target_box[2]) / 2)
                by = int(best_target_box[1] + (best_target_box[3] - best_target_box[1]) * 0.3)
                cv2.circle(annotated_frame, (bx, by), 8, (0, 255, 0), -1)
        else:
            cv2.putText(annotated_frame, "NORMAL TRACKING MODE", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 0), 3)

        cv2.imshow("YOLOv8 Real-Time Tracking", annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    if ser is not None:
        ser.close()
    cap.release()
    cv2.destroyAllWindows()
    print("YOLO追跡システムが停止しました。")

